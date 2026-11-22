# Nén dữ liệu, nén index và đánh đổi CPU với dung lượng trong MongoDB

MongoDB lưu dữ liệu dưới dạng BSON và thường sử dụng storage engine **WiredTiger**. Trong WiredTiger, nén giúp giảm số byte phải lưu và trao đổi với thiết bị lưu trữ, nhưng quá trình nén và giải nén cần CPU. Riêng index thường sử dụng **prefix compression** để tận dụng các phần đầu khóa lặp lại. Vì vậy, chọn cấu hình nén không chỉ là chọn file database nhỏ hơn: nó ảnh hưởng tới số lần đọc đĩa, mức dùng CPU, kích thước working set, tốc độ ghi, độ trễ truy vấn và chi phí hạ tầng.

Bài học này giải thích cơ chế từ góc nhìn kiến trúc, hướng dẫn đo bằng lệnh MongoDB và đưa ra quy trình chọn cấu hình phù hợp với workload. Các ví dụ hướng tới MongoDB dùng WiredTiger; tên tham số, cơ chế mặc định và chỉ số chi tiết cần được đối chiếu với **phiên bản MongoDB đang triển khai** trước khi áp dụng production.

## 1. Phân biệt những loại “nén” khác nhau

Từ *compression* trong MongoDB có thể chỉ những cơ chế ở các tầng hoàn toàn khác nhau. Không phân biệt chúng sẽ dẫn đến quyết định sai: bật nén đường truyền không tự làm collection nhỏ hơn trên đĩa, và giảm kích thước collection không có nghĩa index cũng giảm theo cùng tỷ lệ.

| Tầng | Đối tượng | Cơ chế điển hình | Mục tiêu | Đánh đổi chính |
|---|---|---|---|---|
| Document/BSON | Field và giá trị của document | Thiết kế cấu trúc, kiểu dữ liệu hợp lý; có thể nén ở ứng dụng | Giảm lượng dữ liệu logic trước lưu trữ | Khó truy vấn field nếu nén cả payload ở ứng dụng |
| Collection trên đĩa | Các block/page dữ liệu WiredTiger ghi ra storage | Block compression: `snappy`, `zlib`, `zstd` hoặc `none` | Giảm footprint và I/O lưu trữ | CPU nén/giải nén, biến động latency |
| Index | Các khóa được sắp thứ tự trong cấu trúc index | Prefix compression cho các khóa có tiền tố chung | Giảm dung lượng index | Chi phí xử lý key/page; lợi ích tùy phân bố khóa |
| Journal | Dữ liệu ghi phục vụ khôi phục sau sự cố | Journal compression theo cấu hình engine | Giảm lưu lượng/footprint ghi journal | CPU trên đường ghi và yêu cầu durability |
| Mạng | Gói tin giữa client và server | Wire protocol compression khi hai phía hỗ trợ/thỏa thuận | Giảm byte truyền qua mạng | CPU hai đầu, hiệu quả tùy payload |
| Backup | Dữ liệu xuất/snapshot/backup | Compression của công cụ hoặc dịch vụ backup | Giảm dung lượng lưu bản sao và truyền tải | CPU backup/restore, thời gian khôi phục |

**Trọng tâm của bài:** block compression cho collection và prefix compression cho index. Các tầng còn lại cần được nhận diện để tránh đo nhầm.

### Điều gì không phải là nén dữ liệu?

- **Projection** chỉ trả về những field cần thiết từ query: giảm dữ liệu trả về và thường giảm chi phí xử lý; không trực tiếp nén file lưu trữ.
- **Index** giúp tránh đọc các document không cần thiết; tạo index thường làm **tăng** tổng dung lượng database dù truy vấn nhanh hơn.
- **TTL** xóa dữ liệu sau thời hạn: giúp kiểm soát retention và dung lượng dữ liệu sống, không phải thuật toán nén.
- **Sharding** chia dữ liệu qua nhiều shard, không tự làm tổng dữ liệu logic nhỏ hơn.
- **Replication** tạo bản sao dữ liệu để tăng tính sẵn sàng; nó thường làm tổng dung lượng toàn cụm tăng theo số bản sao.

## 2. WiredTiger xử lý dữ liệu trong bộ nhớ và trên đĩa như thế nào?

Hãy theo dõi vòng đời đơn giản hóa của một document:

~~~mermaid
flowchart LR
    App["Ứng dụng / MongoDB driver"] --> BSON["Document BSON"]
    BSON --> Cache["WiredTiger cache: trang dữ liệu được xử lý trong bộ nhớ"]
    Cache -->|"reconcile / ghi page"| Compressor["Block compressor"]
    Compressor --> Disk["Block đã nén trên storage"]
    Disk -->|"đọc block"| Decompress["Giải nén"]
    Decompress --> Cache
    Cache --> Result["Thực thi truy vấn / kết quả"]
~~~

Sơ đồ lược bỏ nhiều thành phần của đường ghi, checkpoint, eviction và journal nhưng cho thấy điểm cốt lõi:

1. Ứng dụng gửi/nhận document BSON; engine quản lý các page và cấu trúc lưu trữ.
2. WiredTiger duy trì các page và dữ liệu cần thiết trong cache để truy cập nhanh.
3. Khi ghi các page ra thiết bị lưu trữ, block compressor có thể giảm số byte trên đĩa.
4. Khi cần đọc page chưa có trong cache, engine đọc block đã lưu và giải nén để sử dụng.
5. Một thao tác đọc trúng cache có thể tránh phải đọc và giải nén block từ disk.

Điểm cần nhớ: **dung lượng đã nén trên đĩa không đồng nghĩa lượng RAM cần dùng cho working set**. Page, document và cấu trúc quản lý trong cache vẫn có chi phí bộ nhớ; cache eviction, dữ liệu đang được xử lý và các lớp cache hệ điều hành làm bức tranh phức tạp hơn một phép chia tỷ lệ nén.

### Page, block và locality

WiredTiger tổ chức dữ liệu theo B-tree và quản lý page; block nén trên disk là đơn vị của cơ chế lưu trữ, không nhất thiết tương ứng một document. Một page có thể chứa nhiều document hoặc key; mức độ lặp của dữ liệu **trong phạm vi các khối được nén** ảnh hưởng đến hiệu quả.

Ví dụ, nhiều document cùng có trường `tenantId: "tenant-a"`, `status: "ACTIVE"` và dữ liệu văn bản lặp có thể tạo cơ hội nén tốt. Ngược lại, payload đã được nén, dữ liệu mã hóa hoặc chuỗi ngẫu nhiên thường còn ít mẫu lặp có ích.

**Không suy luận rằng “một document dài sẽ được nén tốt”**. Nội dung lặp trong block, kích thước page, thứ tự ghi, phân bố dữ liệu và lựa chọn thuật toán đều có tác động.

## 3. Block compression của collection

WiredTiger hỗ trợ các compressor phổ biến:

| Cấu hình | Đặc điểm thực hành | Khi nào cân nhắc |
|---|---|---|
| `snappy` | Hướng tới tốc độ nén/giải nén, tỷ lệ thường vừa phải | Workload nhạy latency và muốn giảm I/O với chi phí CPU tương đối thấp |
| `zstd` | Thường cho tỷ lệ nén tốt với tốc độ cạnh tranh; CPU phụ thuộc dữ liệu và mức triển khai | Dataset lớn, storage/I/O đắt, CPU còn dư; cần đo trên workload thật |
| `zlib` | Thuật toán nén truyền thống, có thể đạt tỷ lệ tốt nhưng thường tốn CPU hơn | Bài toán ưu tiên dung lượng và chấp nhận chi phí xử lý |
| `none` | Không dùng block compression ở tầng collection | Thử nghiệm so sánh hoặc workload có dữ liệu khó nén/CPU bị giới hạn |

Nhiều triển khai WiredTiger dùng `snappy` làm mặc định cho collection. Tuy nhiên, **không mặc định kết luận cluster đang chạy dùng compressor nào** chỉ vì biết tên storage engine: các deployment có thể được cấu hình khác, và collection tạo ở thời điểm khác nhau có thể mang cấu hình khác nhau.

### 3.1. Vì sao ít byte trên đĩa có thể cải thiện hiệu năng?

Giả sử truy vấn phải đọc 100 MiB dữ liệu logic từ các block chưa nằm trong cache:

- Không nén: có thể phải chuyển lượng byte lớn hơn từ thiết bị lưu trữ vào bộ nhớ.
- Nén: có thể chỉ phải chuyển một phần số byte đó rồi dùng CPU để giải nén.

Khi đĩa hoặc mạng lưu trữ là nút thắt, giảm byte vật lý có thể giảm thời gian chờ I/O đáng kể. Với workload nhiều lần truy cập dữ liệu nóng đã nằm trong cache, hiệu quả từ giảm số byte trên disk có thể nhỏ hơn nhiều. Nếu CPU đang gần bão hòa, chi phí giải nén có thể trở thành nút thắt mới.

Một mô hình tư duy đơn giản:

~~~text
Thời gian xử lý dữ liệu khi cache miss
    chịu ảnh hưởng bởi:
    thời gian chờ và đọc block từ storage
    + chi phí giải nén / dựng page
    + chi phí xử lý truy vấn

Khả năng phục vụ toàn hệ thống
    bị chặn bởi tài nguyên nào bão hòa trước:
    CPU, I/O, RAM/cache, mạng, lock/contention,
    hoặc cơ chế đồng thời của workload.
~~~

Các bước thực thi có thể song song/chồng lấp, nên đây là mô hình định tính, **không phải công thức cộng tuyệt đối để dự đoán latency**.

### 3.2. Ví dụ số minh họa

Giả định một phép quét phải đọc dữ liệu logic tương đương 100 GiB, tốc độ đọc đĩa hiệu dụng giữ cố định ở 200 MiB/s và bỏ qua mọi overhead:

| Phương án giả định | Dữ liệu đọc từ disk | Thời gian I/O thuần tối thiểu trong mô hình |
|---|---:|---:|
| Không nén | 100 GiB | 512 giây |
| Nén còn 62% | 62 GiB | Khoảng 317 giây |
| Nén còn 45% | 45 GiB | Khoảng 230 giây |

**Các tỷ lệ trên là giả định để minh họa phép tính, không phải kết quả đo Snappy/Zstd/Zlib.** Thời gian thực tế có thể thấp hoặc cao hơn rất nhiều do cache, đọc ngẫu nhiên, CPU giải nén, kích thước page, tính song song, truy vấn và cơ chế thiết bị lưu trữ. Nếu phương án nén còn 45% làm CPU bão hòa, nó vẫn có thể cho throughput hoặc p99 latency kém hơn phương án còn 62%.

## 4. Nén index bằng prefix compression

Index của WiredTiger thường là cấu trúc B-tree chứa các entry có thứ tự theo key. Với compound index, key kết hợp từ nhiều field. Trong những entry nằm gần nhau theo thứ tự sắp xếp, nhiều byte đầu khóa có thể giống nhau.

**Prefix compression** tận dụng phần đầu lặp lại giữa các khóa kề nhau để tránh lưu nguyên vẹn các prefix trùng lặp nhiều lần. Cần phân biệt với block compression:

- Block compression tìm mẫu có thể nén trong nội dung block của collection.
- Prefix compression tận dụng **tính có thứ tự và prefix chung của index key**, đặc biệt hữu ích khi nhiều entry cùng chia sẻ giá trị ở các thành phần đầu của compound key.
- Index prefix compression không có nghĩa MongoDB chỉ lưu một bản của mỗi key hoặc loại bỏ tính duy nhất của entry; engine vẫn phải phân biệt đầy đủ từng khóa và tham chiếu đến document.

### 4.1. Minh họa index nhiều khóa

Giả sử collection `orders` có các document:

~~~javascript
{
  _id: "order-1001",
  tenantId: "tenant-001",
  status: "PAID",
  createdAt: ISODate("2026-02-01T09:00:00Z")
}
{
  _id: "order-1002",
  tenantId: "tenant-001",
  status: "PAID",
  createdAt: ISODate("2026-02-01T09:05:00Z")
}
{
  _id: "order-1003",
  tenantId: "tenant-001",
  status: "PAID",
  createdAt: ISODate("2026-02-01T09:10:00Z")
}
~~~

Index:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
})
~~~

Các key gần nhau có phần đầu cùng biểu diễn `tenant-001` và `PAID`, nên có thể có cơ hội nén prefix. Hình dung logic (không phải định dạng byte thực của WiredTiger):

~~~text
Khóa đầy đủ 1: [tenant-001 | PAID | 2026-02-01 09:10]
Khóa đầy đủ 2: [tenant-001 | PAID | 2026-02-01 09:05]
Khóa đầy đủ 3: [tenant-001 | PAID | 2026-02-01 09:00]

Biểu diễn ý tưởng:
  [tenant-001 | PAID | 09:10]
  [phần đầu giống khóa trước | 09:05]
  [phần đầu giống khóa trước | 09:00]
~~~

Trong ví dụ, prefix lặp là cơ hội nén **về byte đã mã hóa của key**; thuật toán thực tế xử lý định dạng, page boundary và metadata theo cách riêng. Không nên suy diễn rằng mọi key sẽ tiết kiệm đúng số ký tự đã lược bỏ trong hình.

### 4.2. Trường hợp nén index hiệu quả hoặc hạn chế

| Hình dạng key/data | Cơ hội prefix compression | Lý do |
|---|---|---|
| Nhiều đơn cùng `tenantId` và `status` | Thường tốt | Nhiều khóa gần nhau có phần đầu giống nhau |
| Key là chuỗi có prefix có ý nghĩa | Có thể tốt | Các key kề nhau có phần đầu lặp |
| Key bắt đầu bằng giá trị ngẫu nhiên, phân bố rộng | Có thể hạn chế | Ít prefix chung giữa khóa kề nhau |
| Index nhiều field nhưng giá trị đầu thay đổi liên tục | Phụ thuộc dữ liệu | Những khóa gần nhau không nhất thiết có prefix dài |
| Index nhỏ, toàn bộ nằm trong cache | Lợi ích I/O có thể nhỏ | Chi phí query có thể nằm ở CPU hoặc nơi khác |

Một số câu cần tránh hiểu sai:

1. **Không đảo thứ tự field trong compound index chỉ để tăng nén.** Thứ tự index trước hết phải phục vụ filter, sort, range, cardinality và hiệu năng truy vấn.
2. **Không lẫn index prefix compression với query prefix search.** Một query bắt đầu bằng regex/chuỗi tiền tố là bài toán lập kế hoạch truy vấn khác.
3. **Không suy ra index đã được nén bao nhiêu phần trăm chỉ từ `totalIndexSize`.** Cần cấu hình so sánh phù hợp và kiểm soát cùng dữ liệu.
4. **Không cho rằng index càng ít dung lượng càng tốt.** Một compound index lớn hơn nhưng đúng truy vấn có thể tiết kiệm nhiều CPU và I/O hơn một index nhỏ không hữu ích.

### 4.3. Vai trò của index đối với RAM

Giảm footprint index có thể làm giảm I/O và giúp nhiều thành phần cấu trúc index nằm trong working set. Nhưng RAM sử dụng còn phụ thuộc số trang đang active, định dạng page trong cache, số lượng index, pattern truy cập và cấu hình WiredTiger cache. **Đừng lấy tổng dung lượng index sau nén trên disk làm dự báo trực tiếp cho cache requirement.**

## 5. Cấu hình compression trong MongoDB

Trong triển khai dùng WiredTiger, các tham số máy chủ thường gặp gồm:

~~~yaml
# Ví dụ cấu hình minh họa, chỉ dùng sau khi kiểm tra phiên bản.
storage:
  wiredTiger:
    collectionConfig:
      blockCompressor: zstd
    indexConfig:
      prefixCompression: true
~~~

- `storage.wiredTiger.collectionConfig.blockCompressor`: chọn compressor mặc định của collection do WiredTiger tạo theo cấu hình áp dụng.
- `storage.wiredTiger.indexConfig.prefixCompression`: điều khiển prefix compression của index theo phạm vi cấu hình áp dụng.

Tùy phiên bản, MongoDB còn hỗ trợ thiết lập thuộc tính storage engine khi tạo collection/index. Các lựa chọn và cú pháp chi tiết cần tham khảo tài liệu **đúng phiên bản**.

**Lưu ý vòng đời cấu hình:** Thay đổi default ở cấp server không bảo đảm mọi block/index đã tồn tại được viết lại tức thì bằng thuật toán mới. Khi thử nghiệm hoặc lập kế hoạch chuyển compressor, phải xác định chính xác nó áp dụng cho **đối tượng tạo mới**, dữ liệu đã được ghi, các page được viết lại, và liệu cần một quy trình rebuild/migrate có kiểm soát hay không. Tránh giả định chỉ sửa YAML rồi khởi động lại là đã đổi toàn bộ footprint lịch sử.

### Những điều không nên làm trực tiếp trong production

- Không thay compressor đồng thời với thay schema, index và topology rồi coi chênh lệch latency là do compression.
- Không rebuild collection/index hàng loạt mà chưa dự báo dung lượng trống, I/O, tải của node và thời gian thao tác.
- Không làm benchmark nặng trên primary đang phục vụ traffic thật để đánh giá “trước/sau”.
- Không dùng kích thước file sau khi xóa nhiều document làm bằng chứng compressor hoạt động kém; disk reuse, fragmentation và cấu trúc page có thể giữ vùng đã cấp phát.
- Không chọn `none` chỉ vì thấy CPU cao; phải đo CPU đang dành cho hoạt động nào.

## 6. Cách đo dung lượng và hiệu quả compression

Cần thu **dung lượng logic**, **dung lượng vật lý đã cấp phát**, **dung lượng index**, **tài nguyên máy** và **độ trễ truy vấn**. Một con số duy nhất không giải thích đầy đủ lợi ích nén.

### 6.1. Các trường thống kê thông dụng

~~~javascript
use mongo_learning

const s = db.orders.stats()
printjson({
  count: s.count,
  size: s.size,
  avgObjSize: s.avgObjSize,
  storageSize: s.storageSize,
  totalIndexSize: s.totalIndexSize,
  indexSizes: s.indexSizes,
  totalSize: s.totalSize
})
~~~

Ý nghĩa thường gặp:

| Trường | Cách đọc |
|---|---|
| `count` | Số document trong collection |
| `size` | Dung lượng logic của document được thống kê, không đồng nhất với byte lưu trên disk |
| `avgObjSize` | Kích thước logic trung bình/document |
| `storageSize` | Footprint storage được cấp phát cho collection; chịu ảnh hưởng compression và quản lý không gian |
| `totalIndexSize` | Tổng footprint các index theo phép thống kê của engine |
| `indexSizes` | Footprint theo từng index (khi có trong output) |
| `totalSize` | Tổng footprint collection và index theo cách tính của thống kê |

Một tỷ lệ để **tham khảo**:

~~~text
approximate_collection_ratio = storageSize / size

Nếu size = 2.000 MiB và storageSize = 800 MiB:
  ratio = 0,40  (~60% ít hơn kích thước logic)
~~~

Đây **không phải tỷ lệ nén thuần túy của thuật toán**. `storageSize` có thể phản ánh page overhead, cấp phát chưa dùng, không gian tái sử dụng và khác biệt thời điểm quan sát. Cũng cần lưu ý `size` không bao gồm toàn bộ chi phí index và journal. Khi `size` quá nhỏ, tỷ lệ có thể không có ý nghĩa; không nên chia cho 0 hoặc kết luận từ collection vài document.

### 6.2. Phân biệt logic size và BSON size

Muốn xem kích thước BSON của từng document trong một mẫu:

~~~javascript
db.orders.aggregate([
  { $sample: { size: 50 } },
  {
    $project: {
      _id: 0,
      bsonBytes: { $bsonSize: "$$ROOT" }
    }
  },
  {
    $group: {
      _id: null,
      avgBsonBytes: { $avg: "$bsonBytes" },
      maxBsonBytes: { $max: "$bsonBytes" }
    }
  }
])
~~~

Ví dụ chỉ có dữ liệu nếu collection đã tồn tại và có document. `$bsonSize` đo BSON tại tầng document, **không đo số byte của document sau WiredTiger block compression**. Mẫu cũng không thay thế thống kê toàn population nếu dữ liệu có nhiều nhóm rất khác nhau.

### 6.3. Quan sát index và tài nguyên máy

~~~javascript
db.orders.getIndexes()

// Cách quan sát mức sử dụng index (access count), không phải tỷ lệ nén.
db.orders.aggregate([
  { $indexStats: {} }
])

// Thống kê tổng quan server/WiredTiger; trường chi tiết tùy phiên bản.
const status = db.serverStatus()
printjson(status.wiredTiger && status.wiredTiger.cache)
~~~

`$indexStats` cho số lượt sử dụng index trong khoảng quan sát của hệ thống, không cho biết index có “nén tốt” hay không. Các metric cache và block I/O trong `serverStatus` cũng phải được đối chiếu với định nghĩa phiên bản cụ thể. Một số lệnh cần quyền quan sát/monitor phù hợp.

Ở phía hạ tầng, tối thiểu cần:

- CPU utilization theo **core**, mức bão hòa CPU và thời gian xử lý request.
- Disk read/write throughput, IOPS, latency và queue depth.
- WiredTiger cache usage, read/eviction pressure và cache miss hoặc dấu hiệu đọc storage.
- p50/p95/p99 của query và cập nhật; throughput thực tế.
- Kích thước dữ liệu/index, dung lượng đĩa còn trống và tốc độ tăng.
- Tình trạng replication, backup và những tác vụ nền làm nhiễu số liệu.

## 7. Thí nghiệm: dữ liệu dễ nén và khó nén

Thí nghiệm sau dùng **môi trường học tập riêng**. Tạo cùng dataset trên hai hoặc nhiều instance MongoDB độc lập với compressor khác nhau, nhưng cùng phiên bản, tài nguyên, topology và query. Chỉ cần một số mẫu nhỏ để hiểu hành vi; benchmark tin cậy cần tập dữ liệu đủ lớn và đại diện.

### 7.1. Tạo dữ liệu chứa cấu trúc lặp

Trong mongosh của một instance lab:

~~~javascript
use mongo_compression_lab

const coll = db.events
const repetitive = "event-source=checkout;tenant=alpha;".repeat(30)

let batch = []
for (let i = 0; i < 10000; i++) {
  batch.push({
    _id: i,
    tenantId: "tenant-" + String(i % 5).padStart(3, "0"),
    status: i % 3 === 0 ? "PAID" : "CREATED",
    kind: "CHECKOUT",
    createdAt: new Date(Date.UTC(2026, 0, 1, 0, 0, i)),
    sequence: i,
    payload: repetitive
  })

  if (batch.length === 500) {
    coll.insertMany(batch)
    batch = []
  }
}

coll.createIndex({ tenantId: 1, status: 1, createdAt: -1 })

const s = coll.stats()
printjson({
  count: s.count,
  logicalBytes: s.size,
  storageBytes: s.storageSize,
  indexBytes: s.totalIndexSize,
  indexSizes: s.indexSizes
})
~~~

**Chỉ chạy một lần với collection rỗng.** Nếu chạy lại cùng `_id`, insert sẽ gặp lỗi duplicate key; đó là hành vi đúng. Không tự xóa database chứa dữ liệu không thuộc lab.

Payload lặp trên tạo điều kiện thuận lợi cho compression. Tỷ lệ thực tế còn phụ thuộc các block và thiết lập của instance, nên không dự đoán trước con số phải nhìn thấy.

### 7.2. Dữ liệu khó nén trông như thế nào?

Một dataset có thể khó nén hơn khi chứa:

- Chuỗi token sinh ngẫu nhiên có độ hỗn loạn cao.
- Bytes đã được nén (JPEG, ZIP, MP4, GZIP...) theo thuật toán riêng.
- Payload mã hóa ở ứng dụng, ciphertext có entropy cao.
- Dữ liệu binary không đồng nhất, ít chuỗi mẫu lặp giữa các document.

Không thể so sánh bằng cách chỉ dùng một chuỗi tăng dần ngắn rồi gọi đó là “ngẫu nhiên”. Dữ liệu ngẫu nhiên phải được tạo bằng bộ sinh thích hợp hoặc được lấy từ workload đại diện; benchmark công bằng cần kiểm soát cả **kích thước logic** và **kiểu truy cập**, không chỉ số lượng document.

### 7.3. Đo trước và sau dưới cùng workload

Ví dụ query có filter và sort:

~~~javascript
db.events.find({
  tenantId: "tenant-001",
  status: "PAID",
  createdAt: { $gte: ISODate("2026-01-01T00:00:00Z") }
}).sort({ createdAt: -1 }).limit(100).explain("executionStats")
~~~

Đo nhiều lượt:

1. **Warm-up:** chạy query đủ để thấy hành vi cache ổn định hoặc phân loại rõ lượt cold-cache/warm-cache.
2. **Read-heavy:** point lookup, range query và một số aggregation đại diện.
3. **Write-heavy:** insert/update có cùng tốc độ, kích thước batch, index và mức concurrency.
4. **Mixed workload:** tỷ lệ đọc/ghi gần với production, không chỉ chạy quét tuần tự.
5. **Scale:** tăng dữ liệu vượt working set để quan sát cache miss và storage I/O.

Nếu so sánh một instance dùng `snappy` với một instance dùng `zstd`, tất cả biến khác cần càng giống nhau càng tốt: document logic, số index, JVM/application, connection pool, hạ tầng, thời điểm kiểm tra, filesystem, replica set, journal, cache và phương án đọc/ghi.

## 8. Bảng quyết định giữa CPU, disk và latency

### 8.1. Trường hợp workload thường gặp

| Workload | Điểm nghẽn có thể gặp | Quyết định cần kiểm chứng |
|---|---|---|
| Nhiều truy vấn range, dữ liệu lớn hơn RAM | Disk throughput, IOPS, cache miss | Compressor cho tỷ lệ tốt hơn có thể giảm I/O; đo CPU giải nén và p95/p99 |
| Read-heavy, index fits in memory | CPU xử lý query, network, contention | Đổi block compressor có thể ít tác dụng; ưu tiên query/index/projection |
| Ghi liên tục, CPU cao | CPU cho ghi, cập nhật index, compression | Compressor nhanh hơn có thể giảm CPU; theo dõi disk write và durability |
| Dataset rất lớn, storage đắt | Dung lượng disk, backup, I/O | Thử compressor tiết kiệm byte hơn; tính toàn bộ chi phí vận hành |
| Dữ liệu multimedia đã nén | Mức nén thêm thấp | Thử `none` hoặc compressor nhanh trong lab; cân nhắc vị trí lưu blob |
| Multi-tenant có prefix index lặp | Dung lượng index, cache pressure | Giữ prefix compression, đo index size và độ trễ thực tế |
| Workload rất nhạy p99 | Biến động CPU, page fault, I/O | Đo tail latency ở mức tải đỉnh; không chọn theo dung lượng trung bình |

### 8.2. Cách đọc một kết quả benchmark

Giả sử hai cấu hình A và B cho kết quả **giả định**:

| Chỉ số | A | B |
|---|---:|---:|
| Footprint collection | 300 GiB | 210 GiB |
| CPU ở tải đỉnh | 55% | 88% |
| Disk read throughput | 220 MiB/s | 150 MiB/s |
| p95 query latency | 45 ms | 48 ms |
| p99 query latency | 90 ms | 160 ms |

B tiết kiệm được 90 GiB collection và giảm byte đọc, nhưng CPU tiến gần bão hòa và p99 tăng. Với dịch vụ cần p99 dưới 100 ms, B chưa đạt yêu cầu dù footprint tốt hơn. Nếu workload chủ yếu chạy batch ngoài giờ và storage là chi phí lớn, B có thể đáng thử. **Không thể kết luận chỉ từ tỷ lệ nén**; phải xét SLO, khả năng mở rộng, hiệu suất ghi, backup/restore và chi phí phần cứng.

### 8.3. Chi phí tổng thể cần tính

Một cấu hình nén tốt về kinh tế cân bằng ít nhất:

~~~text
Tổng chi phí gần đúng:
  lưu trữ dữ liệu chính
  + lưu trữ index
  + bản sao replica set
  + backup và retention
  + CPU/máy chủ cần để giữ throughput
  + I/O hoặc dung lượng lưu trữ mạng
  + rủi ro không đạt SLO / thời gian khôi phục
~~~

Ví dụ tiết kiệm 25% storage trên mỗi node trong replica set có thể đáng kể ở quy mô lớn. Nhưng nếu phải nâng cấp CPU cho mọi node để giữ throughput, tổng chi phí có thể tăng. Bài toán không phải chỉ chọn thuật toán có **compression ratio** cao nhất.

## 9. Những yếu tố khiến số liệu compression dễ gây hiểu nhầm

### 9.1. Dataset quá nhỏ

Collection vài document bị chi phối bởi page overhead, metadata và cấp phát storage. Tỷ lệ `storageSize / size` có thể lớn hơn 1; không phải lúc nào cũng là lỗi.

### 9.2. Đã xóa nhiều document

Khi xóa, WiredTiger có thể tái sử dụng vùng lưu trữ bên trong file thay vì ngay lập tức trả tất cả byte về hệ điều hành. Vì vậy, nhìn file trên disk chưa nhỏ lại không chứng minh compressor vô hiệu. Muốn đánh giá footprint sau xóa phải hiểu free space, compaction và chính sách quản trị từng phiên bản.

### 9.3. Cache nóng che giấu chi phí I/O

Nếu query lặp lại trên dữ liệu đã nằm trong cache, storage compressor có thể ít ảnh hưởng tới latency. Benchmark phải phân biệt cache-hot và cache-cold mà không thực hiện thao tác phá cache tùy tiện trên production.

### 9.4. Workload khác nhau giữa các lần đo

Index mới, query mới, khác tỷ lệ read/write, khác số connection hoặc thay đổi bộ dữ liệu có thể làm kết quả biến động nhiều hơn thay compressor. Tránh kết luận nhân quả khi chưa kiểm soát các yếu tố này.

### 9.5. Tính toán bỏ quên index hoặc replica

`storageSize` collection không phản ánh tổng chi phí của database. Cần cộng index, journal/backup theo nhu cầu, replica, log và các yêu cầu dự phòng dung lượng. Nén document tốt không đồng nghĩa tổng footprint của hệ thống giảm tương ứng.

### 9.6. Nén trước ở ứng dụng

Ứng dụng có thể tự nén một field binary rồi lưu vào MongoDB. Điều này có thể làm giảm BSON payload nhưng cũng làm field không còn truy vấn/đánh index nội dung theo cách thông thường; cần cơ chế phiên bản hóa, kiểm tra integrity và giải nén. Dữ liệu đã nén một lần thường ít lợi ích khi tiếp tục block compression.

### 9.7. Mã hóa và dữ liệu ngẫu nhiên

Ciphertext được thiết kế để khó nhận diện mẫu lặp. Vì vậy, nén bên ngoài sau khi mã hóa thường kém hiệu quả; quyết định nén/mã hóa cần xét cơ chế bảo mật, khả năng query và dữ liệu nhạy cảm, không tự sáng tạo đường xử lý có nguy cơ lộ thông tin.

## 10. Prefix compression, index design và write amplification

Giảm footprint index có thể giúp lưu trữ nhiều index/page trên cùng dung lượng storage. Tuy nhiên, **mỗi index vẫn phải được cập nhật khi document thay đổi ở field liên quan**. Tạo quá nhiều index có thể:

- Tăng số thao tác ghi, CPU và I/O do cập nhật nhiều cấu trúc B-tree.
- Tăng yêu cầu cache và thời gian bảo trì/rebuild.
- Tăng chi phí backup và replication do workload ghi và kích thước dữ liệu bổ trợ.
- Ảnh hưởng throughput khi import hoặc update nhiều document.

Prefix compression làm một số index rẻ hơn về dung lượng, **không làm chi phí duy trì index bằng 0**. Do đó, bộ index phải được chọn theo access pattern và kết quả `explain()`, không thêm index chỉ vì chúng có thể được nén.

Ví dụ hai query khác nhau:

~~~javascript
// Query A: lịch sử đơn theo một tenant và status.
db.orders.find({
  tenantId: "tenant-001",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(20)

// Query B: tìm mọi đơn theo productId trong mảng items.
db.orders.find({ "items.productId": "p-101" }).limit(20)
~~~

Index `{tenantId: 1, status: 1, createdAt: -1}` có thể phù hợp Query A nhưng không tự tối ưu Query B. Với Query B cần phân tích riêng về multikey index, khả năng selectivity và business requirement. Đừng chọn thứ tự key chỉ theo độ dài prefix dùng để nén.

### Index compression có ảnh hưởng tính đúng đắn không?

Nén storage/index là cơ chế biểu diễn vật lý dữ liệu. Ở tầng logic, điều kiện query, thứ tự sort, unique constraint và khóa truy cập vẫn phải được áp dụng theo semantics của MongoDB. Một cấu hình index hợp lệ không được phép “trộn” hai khóa khác nhau chỉ vì có prefix chung. Nếu thấy kết quả query sai, cần kiểm tra schema, type, collation, filter, indexes và ứng dụng, thay vì suy đoán prefix compression tự làm mất dữ liệu.

## 11. Vận hành compression trong replica set và sharded cluster

Một MongoDB production hiếm khi chỉ có một process. Khi đổi thuật toán nén cần xét toàn topology:

1. **Replica set:** Mỗi node có storage và tài nguyên riêng; cấu hình/vòng đời tạo collection có thể khác nhau theo lịch sử. Dữ liệu logic replicated không có nghĩa byte nén trên disk phải bằng nhau.
2. **Secondary:** Việc nhận và áp dụng write qua replication vẫn tạo tải I/O/CPU riêng; theo dõi replication lag sau thay đổi storage.
3. **Failover:** Khi primary đổi, node mới phải chịu tải đọc/ghi phù hợp; benchmark chỉ trên primary hiện tại chưa đủ cho dự phòng năng lực.
4. **Sharding:** Phân bố dữ liệu theo shard key có thể tạo các shard với độ compressibility khác nhau; đo theo shard và tổng cluster.
5. **Backup/restore:** Logical restore có thể viết lại dữ liệu ở cấu hình compressor mới; thời gian restore và footprint cần được kiểm chứng. Phương án backup khác nhau có semantics khác nhau.
6. **Rolling operation:** Nếu định thay đổi cấu hình trên nhiều node, cần kế hoạch tương thích phiên bản, áp dụng có kiểm soát và giám sát tính sẵn sàng, không thay đồng loạt.

Một node có CPU thấp không chứng minh toàn cluster còn dư CPU. Khi shard A mang phần lớn traffic hoặc primary vừa chuyển sang node yếu hơn, chi phí compression có thể biểu hiện khác dự báo.

## 12. Quy trình lựa chọn compressor có thể áp dụng

### Bước 1 — Xác định vấn đề cần giải

Ghi rõ **giới hạn** hiện tại: dung lượng disk, IOPS, throughput, mức dùng CPU hay p99 latency. Nếu không có giới hạn cụ thể, thay compressor có thể tăng rủi ro mà không đem lại lợi ích.

### Bước 2 — Lập bản đồ dữ liệu

Ghi các collection lớn nhất, loại field, tỷ lệ payload lặp, dữ liệu binary đã nén/mã hóa, tốc độ tăng, số index và tỷ lệ working set so với RAM. Phân biệt dữ liệu nóng với dữ liệu lịch sử.

### Bước 3 — Định nghĩa workload đại diện

Chọn các loại query thật và tỷ lệ request: point lookup, range query, aggregation, insert/update/delete, background index build và backup. Ghi concurrency, batch size, read/write concern và cache state.

### Bước 4 — Tạo các môi trường thử nghiệm

Giữ nguyên phiên bản MongoDB, dữ liệu logic, topology, số index, cấu hình máy, driver và cài đặt query. Thay đúng biến compressor trong từng lần so sánh. Nếu thử prefix compression index, so sánh index được tạo trong cùng điều kiện và khối lượng dữ liệu.

### Bước 5 — Thu bộ metric đầy đủ

Lưu footprint collection/index, CPU, I/O, cache pressure, throughput, p95/p99, write latency, replication lag và kết quả restore nếu đây là một thay đổi production. Chạy nhiều lượt ở các mức tải, ghi lại khoảng dao động.

### Bước 6 — Quyết định theo SLO và khả năng phục hồi

Nếu một compressor tiết kiệm storage nhưng làm p99 vượt SLO hoặc tăng replication lag quá mục tiêu, không áp dụng chỉ vì số byte nhỏ. Nêu rõ trade-off được chấp nhận bằng dữ liệu, phạm vi triển khai và phương án rollback.

### Bước 7 — Triển khai theo giai đoạn, quan sát

Dùng quy trình thay đổi cấu hình phù hợp topology; giám sát footprint, CPU, I/O, lỗi, replication và latency. Trước mỗi bước mở rộng phạm vi, xác minh kết quả thực tế và khả năng quay về cấu hình/cấu trúc cũ khi cần.

## 13. Tình huống chẩn đoán thực tế

### Tình huống A — Collection nhỏ trên đĩa nhưng API chậm hơn

**Triệu chứng:** Sau khi chọn compressor cho tỷ lệ tốt hơn, `storageSize` giảm nhưng p99 tăng.

**Đường điều tra:**

1. Đối chiếu CPU usage, mức bão hòa và các chỉ số cache miss/I/O trước–sau.
2. Kiểm tra request volume, query plan, index và concurrency có giữ nguyên không.
3. Phân biệt query cần đọc từ disk với query cache-hot.
4. Xem tail latency có tăng tương quan với CPU saturation hay không.
5. So sánh với cấu hình trước ở workload tương đương.

**Bài học:** Nén giảm I/O nhưng có thể chuyển điểm nghẽn sang CPU, đặc biệt ở tải cao.

### Tình huống B — Có index nhưng tổng database vẫn lớn

**Triệu chứng:** Dữ liệu logic không tăng nhiều, `totalIndexSize` tăng mạnh.

**Đường điều tra:** Kiểm kê index đang có, workload `$indexStats`, index chưa dùng, compound index gần trùng chức năng, multikey index trên array và xu hướng số document. Không xóa index chỉ vì ít lượt truy cập trong một khoảng quan sát ngắn: báo cáo theo mùa, truy vấn quản trị và job hiếm chạy cũng cần được xét.

**Bài học:** Compression của index không thay thế công việc thiết kế và quản trị tập index.

### Tình huống C — Disk vẫn đầy sau khi xóa dữ liệu cũ

**Triệu chứng:** `count` và `size` giảm nhưng file storage không nhỏ tương ứng.

**Đường điều tra:** Phân biệt logical size, allocated storage, free space có thể tái sử dụng, retention và tác động các operation nền. Nếu cần lấy lại dung lượng cho filesystem, phải nghiên cứu công cụ và giới hạn compaction/resync phù hợp phiên bản và topology, dự báo thêm dung lượng tạm và tác động hiệu năng.

**Bài học:** Cơ chế cấp phát/tái sử dụng không gian khác với tỷ lệ nén.

### Tình huống D — Compression tốt trong lab, kém khi chạy thật

**Triệu chứng:** Dataset mẫu có tỷ lệ rất cao nhưng production chỉ tiết kiệm ít.

**Đường điều tra:** So sánh entropy/payload, số index, document sizes, loại dữ liệu binary, phân bố tenant, thời điểm tạo collection và tỷ lệ data-hot/data-cold. Đặc biệt xem sample có chứa chuỗi lặp nhân tạo hoặc khác hẳn dữ liệu thật không.

**Bài học:** Compression ratio là thuộc tính của **data + thuật toán + storage layout**, không phải hằng số cố định của compressor.

## 14. Bài thực hành tích hợp

**Bối cảnh:** Một nền tảng sự kiện lưu 500 triệu event, mỗi event có `tenantId`, `deviceId`, `eventType`, `createdAt`, `payload`. Truy vấn thường dùng là lấy 100 event gần nhất của một tenant/device; nghiệp vụ batch tổng hợp event theo ngày. Dữ liệu sau sáu tháng chủ yếu được đọc ít, nhưng phải lưu hai năm. Máy hiện tại đôi lúc chạm giới hạn I/O, còn CPU ban ngày dao động cao.

### Yêu cầu

1. Thiết kế 2–3 lựa chọn data/index theo các query cụ thể; giải thích vì sao không tạo index cho mọi field.
2. Phân loại field `payload` nào có thể lặp, field nào đã nén/mã hóa và ảnh hưởng tới block compression.
3. Đề xuất thí nghiệm so sánh `snappy`, `zstd` và `none` trên dữ liệu đại diện; giữ nguyên query/index/topology giữa các lần.
4. Thu `size`, `storageSize`, `totalIndexSize`, CPU, throughput, p95/p99, disk IOPS và replication lag.
5. So sánh query cache-hot với query trên dữ liệu lịch sử ít truy cập; giải thích sự khác biệt.
6. Viết cách ra quyết định khi phương án tiết kiệm 30% storage nhưng làm p99 vượt SLO.
7. Đề xuất chiến lược retention/archival và backup riêng; giải thích tại sao chúng không phải thuật toán nén.
8. Phác thảo kế hoạch thay đổi trên replica set hoặc sharded cluster có khả năng rollback và theo dõi capacity.

### Mẫu bảng kết quả đo

| Thử nghiệm | Collection GiB | Index GiB | CPU peak | Disk read MiB/s | p95/p99 ms | Ops/s | Ghi chú |
|---|---:|---:|---:|---:|---|---:|---|
| Snappy | … | … | … | … | … / … | … | Dữ liệu/query/điều kiện |
| Zstd | … | … | … | … | … / … | … | Dữ liệu/query/điều kiện |
| None | … | … | … | … | … / … | … | Dữ liệu/query/điều kiện |

Người học cần **tự điền số đã đo**, không dùng bảng giả định của phần 8 làm kết quả benchmark.

## 15. Câu hỏi ôn tập và đáp án định hướng

**1. Nén collection và nén index khác nhau ở điểm nào?**

Block compression nén dữ liệu collection khi lưu ra block trên đĩa. Index prefix compression tận dụng các byte đầu giống nhau của những key index kề nhau trong cấu trúc đã sắp thứ tự. Hai cơ chế khác tầng và tỷ lệ tiết kiệm không suy ra trực tiếp từ nhau.

**2. Vì sao giảm 40% `storageSize` mà RAM sử dụng không giảm 40%?**

`storageSize` phản ánh footprint storage của collection; cache còn chứa page, cấu trúc xử lý và working set, không giữ chính xác toàn bộ dữ liệu theo tỷ lệ byte nén trên disk.

**3. Compressor cho tỷ lệ nén cao nhất có phải lựa chọn tốt nhất?**

Không mặc định. CPU, disk I/O, cache misses, p99, throughput, replication lag, RPO/RTO và chi phí mới quyết định cấu hình phù hợp với hệ thống.

**4. Đảo thứ tự compound index để tăng prefix chung có luôn nên làm?**

Không. Thứ tự key trước hết phải đáp ứng filter/sort/range và access pattern. Thay thứ tự có thể làm truy vấn mất khả năng dùng index hiệu quả.

**5. `$bsonSize` có đo số byte trên disk sau nén không?**

Không. Nó đo kích thước BSON của document ở tầng logic, không phân bổ chính xác block bytes đã nén cho riêng document.

**6. Vì sao sau khi xóa dữ liệu, file chưa nhỏ tương ứng?**

WiredTiger có thể tái sử dụng vùng storage đã cấp phát; footprint file và lượng dữ liệu sống không biến đổi tuyến tính. Cần hiểu free space và cơ chế compaction/resync trước khi xử lý.

**7. Dữ liệu đã mã hóa hoặc JPEG có nén tốt thêm bằng WiredTiger không?**

Thường ít cơ hội vì nội dung đã có entropy cao hoặc đã được thuật toán khác nén. Kết quả cụ thể vẫn cần đo trên workload thật.

**8. Có thể kết luận index nén tốt bằng cách nhìn một lần vào `indexSizes` không?**

Không. Cần phép so sánh có kiểm soát cùng dataset, cấu trúc index và môi trường. `indexSizes` là footprint hiện tại, không phải compression ratio tự thân.

**9. Khi nào nén mạnh hơn có thể tăng throughput?**

Khi workload bị giới hạn bởi I/O và CPU còn đủ khả năng nén/giải nén, giảm byte vật lý có thể tăng tốc xử lý toàn hệ thống.

**10. Tại sao phải test cả primary và secondary?**

Vì compression tạo tải CPU/I/O trên từng node và failover có thể chuyển vai trò ghi sang node khác; replica lag và dự phòng năng lực cũng phải đạt mục tiêu.

## 16. Kết luận kiến trúc

Ba nguyên tắc cần mang sang những bài học về hiệu năng và vận hành MongoDB:

1. **Hiểu đúng tầng nén:** WiredTiger block compression phục vụ collection, prefix compression phục vụ index, còn network/journal/backup compression là những cơ chế riêng.
2. **Đo toàn bộ hệ thống:** dung lượng ít hơn chưa chắc tốt hơn; cần CPU, cache, I/O, throughput và latency thực tế, nhất là p95/p99 ở tải đỉnh.
3. **Quyết định theo workload và vòng đời dữ liệu:** thuật toán, index, data model, chiến lược backup, topology và khả năng rollback đều ảnh hưởng chi phí dài hạn.

Khi kết quả thí nghiệm cho thấy một cấu hình giảm storage mà vẫn giữ được SLO, độ bền và khả năng phục hồi, đó mới là bằng chứng có giá trị để triển khai rộng hơn. Mục tiêu của compression không phải con số tỷ lệ nén đẹp nhất, mà là **lưu trữ và truy xuất dữ liệu ổn định với chi phí tài nguyên hợp lý**.
