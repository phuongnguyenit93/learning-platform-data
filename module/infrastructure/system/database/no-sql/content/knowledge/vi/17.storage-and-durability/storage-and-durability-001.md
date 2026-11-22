# Phân biệt dữ liệu logic, cấu trúc chỉ mục và định dạng lưu trữ vật lý

Khi làm việc với NoSQL, lập trình viên thường thấy một document JSON, một key–value hay một hàng có các cột và dễ cho rằng đó là cách cơ sở dữ liệu lưu dữ liệu xuống ổ đĩa. Thực tế, **thứ ứng dụng nhìn thấy** khác với **cấu trúc được dùng để tìm nhanh**, và cũng khác với **cách storage engine mã hóa, ghi, nén và phục hồi dữ liệu**.

Ba tầng cần phân biệt:

1. **Dữ liệu logic (logical data):** thực thể, thuộc tính, quan hệ, khóa, trạng thái và bất biến mà nghiệp vụ định nghĩa.
2. **Cấu trúc chỉ mục (index/access structure):** ánh xạ hoặc cấu trúc phụ giúp truy vấn theo khóa, khoảng giá trị, thành viên mảng, từ khóa, vị trí, vector hoặc quan hệ.
3. **Định dạng lưu trữ vật lý (physical storage):** byte, record encoding, page, block, file, segment, SSTable, journal, cache, compression và các cơ chế phục hồi mà storage engine quản lý.

Vì chủ đề nằm trong chương **Lưu trữ và độ bền**, ta còn phải hỏi: khi API trả thành công thì dữ liệu đã bền đến đâu, chỉ mục có thay thế được bản gốc không, xóa một document có xóa hết byte trong backup chưa, và vì sao replication không đồng nghĩa backup?

Bài dùng MongoDB, Cassandra/ScyllaDB, Redis, các hệ tìm kiếm dựa trên Lucene và DynamoDB để minh họa. Đặc điểm thực tế phụ thuộc **sản phẩm, phiên bản, topology, storage engine và cấu hình**. Không suy diễn chi tiết vật lý của dịch vụ managed nếu tài liệu nhà cung cấp không công bố.

## 1. Nhìn cùng một sản phẩm qua ba tầng

Giả sử ứng dụng bán hàng quản lý sản phẩm:

~~~json
{
  "_id": "p100",
  "tenantId": "t01",
  "sku": "MOUSE-01",
  "name": "Wireless Mouse",
  "status": "ACTIVE",
  "priceMinor": 2999,
  "currency": "USD",
  "tags": ["wireless", "mouse"],
  "attributes": {
    "color": "black",
    "warrantyMonths": 24
  }
}
~~~

| Tầng | Câu hỏi | Minh họa |
|---|---|---|
| Dữ liệu logic | Product nào, field nghĩa gì, bất biến nào phải đúng? | Product `p100`, giá 2.999 đơn vị nhỏ nhất, thuộc tenant `t01` |
| Chỉ mục | Từ khóa tìm kiếm nào dẫn đến product? | `(tenantId,sku) -> p100`; tag `wireless -> p100` |
| Vật lý | Byte nằm đâu và được phục hồi thế nào? | Mã hóa BSON/binary, index pages, journal, cache, file nén |

Ứng dụng có thể gọi:

~~~javascript
db.products.find({
  tenantId: "t01",
  status: "ACTIVE",
  tags: "wireless"
});
~~~

Kết quả logic có thể không đổi dù database thêm/chuyển chỉ mục hoặc storage engine viết lại file qua compaction. Ngược lại, đổi encoding vật lý không được tự đổi giá từ 29,99 USD thành 2999 USD. Đó là ranh giới giữa **hợp đồng nghiệp vụ** và **chi tiết triển khai**.

## 2. Sơ đồ khái niệm từ ứng dụng đến ổ lưu trữ

~~~mermaid
flowchart TD
    A["API: Product, Order, Event"] --> B["Mô hình logic và truy vấn"]
    B --> C["Query planner / access path"]
    C --> D["Chỉ mục: tree, hash, postings, LSM"]
    C --> E["Record hoặc projection cần đọc"]
    D --> F["Storage engine"]
    E --> F
    F --> G["Cache, page, block, file, segment"]
    F --> H["Journal / WAL / commit log"]
    G --> I["Disk / managed storage"]
    H --> I
    F --> J["Replication và recovery"]
~~~

Sơ đồ chỉ diễn tả các thành phần có thể có, **không cam kết thứ tự xử lý của mọi engine**. Có hệ lưu records trong cây, có hệ dùng memtable/SSTable, có hệ chủ yếu giữ state trong RAM và ghi snapshot/AOF, có dịch vụ che giấu toàn bộ byte layout. Các engine khác nhau có thể tối ưu cùng query logic bằng đường đi hoàn toàn khác.

Một điểm then chốt: **index và dữ liệu gốc có thể cùng thuộc storage engine nhưng khác nhiệm vụ**. Mất index có thể xây lại từ nguồn có thẩm quyền, còn mất nguồn không thể mặc nhiên khôi phục đầy đủ chỉ bằng index.

## 3. Dữ liệu logic không chỉ là JSON document

Mô hình logic trả lời: *ứng dụng có thực thể nào, các trường có ý nghĩa gì, và trạng thái hợp lệ là gì?*

| Mô hình NoSQL | Đơn vị logic | Ví dụ |
|---|---|---|
| Key–value | Key, value, có thể có expiry | `session:u42 -> {...}` |
| Document | Document có ID, nested fields, arrays | `Product {_id,variants[]}` |
| Wide-column | Partition key, clustering columns, column values | `events_by_device(deviceId,time)` |
| Graph | Vertices, edges, properties, direction | `Account -[:USES]-> Device` |
| Time-series | Tags, timestamp, measurement | `temperature(device,t,value)` |
| Search | Document, text field và contract tìm kiếm | `name,description,category` |
| Vector | Embedding, metric tương tự và metadata | `embedding[768],tenantId` |

Ví dụ:

- `priceMinor=2999` chỉ có nghĩa đúng khi biết đơn vị tiền và `currency`.
- `status="DELETED"` có thể là soft delete, không nhất thiết đã xóa record vật lý.
- `expiresAt` định nghĩa hết hạn nghiệp vụ; TTL cleanup có thể diễn ra trễ.
- `tenantId` là phạm vi dữ liệu; chỉ mục trên tenant không thay thế authorization.
- Array `variants[]` có thể có quy tắc “hai điều kiện cùng phần tử”, khác với hai điều kiện được khớp bởi hai phần tử bất kỳ.

Dù database chấp nhận schema linh hoạt, ứng dụng vẫn có **schema logic**: tên, kiểu, ý nghĩa, constraint và vòng đời dữ liệu.

## 4. Mô hình logic, index và physical layout là ba quyết định khác nhau

Một Product có thể cần ba đường truy cập:

1. Lấy chi tiết theo `_id`.
2. Lọc theo `tenantId + status + tag`.
3. Tìm theo từ khóa trong tên/mô tả.

Một thiết kế có thể giữ **Product document là nguồn chuẩn**, tạo compound/multikey indexes cho lọc và đồng bộ một search projection có inverted index cho full-text. Storage engine quyết định page, cache, journal, compression và cách lưu dữ liệu theo cấu hình.

~~~text
Yêu cầu nghiệp vụ
    ↓
Mô hình logic / bất biến / schema
    ↓
Mẫu truy cập / index / projection
    ↓
Storage engine, RAM, file, log
    ↓
Đo correctness, latency, durability và cost
~~~

Một câu truy vấn trả đúng nhưng không có index phù hợp vẫn có thể chậm. Một index rất nhanh không thể sửa một bất biến nghiệp vụ sai. Một storage engine ghi bền tốt không tự đảm bảo search projection nhìn thấy thay đổi ngay lập tức.

## 5. Serialization không phải toàn bộ định dạng vật lý

Ứng dụng gửi:

~~~json
{"_id":"p100","priceMinor":2999,"status":"ACTIVE"}
~~~

Đây là JSON biểu diễn dữ liệu. Nhưng JSON truyền qua mạng hoặc debug không có nghĩa file trên đĩa chứa chính chuỗi JSON này.

| Lớp biểu diễn | Mục đích | Ví dụ |
|---|---|---|
| API/driver serialization | Trao đổi dữ liệu | JSON, BSON, Protobuf, RESP |
| Record encoding | Mã hóa giá trị/metadata theo engine | BSON, binary row/value encoding |
| Physical storage | Tổ chức file, page, segment và log | B-tree pages, SSTables, RDB/AOF, Lucene segments |

MongoDB sử dụng BSON cho document nhưng file WiredTiger không phải “mỗi document một file JSON”. Redis lưu key–value theo cấu trúc bộ nhớ phù hợp rồi có thể ghi RDB/AOF. Cassandra dùng memtable/commit log/SSTable. Search engine có thể phân rã một JSON document thành postings, stored fields và doc values.

**Kích thước JSON không phải kích thước RAM hay disk.** Byte sử dụng có thể khác vì kiểu số, metadata, compression, padding/fragmentation, index entries, cache, replica và snapshot. Khi so sánh, phải nói rõ đo kích thước ở tầng nào.

## 6. Chỉ mục logic là ánh xạ khóa tìm kiếm sang bản ghi

Một index theo `tenantId,sku` có thể được hình dung:

~~~text
("t01","MOUSE-01") -> p100
("t01","KB-01")    -> p101
("t02","MOUSE-01") -> p202
~~~

Ở tầng triển khai, giá trị index có thể dẫn đến record ID, primary key, vị trí segment hoặc cấu trúc khác; **không phải mọi index trỏ tới byte offset cố định trên đĩa**. Index giúp:

- Lookup bằng key chính xác.
- Range query và ordered scan.
- Membership trong array/set.
- Full-text qua term/posting.
- Geospatial, graph hoặc vector search chuyên biệt.

Index phụ thường chỉ chứa các field được index và thông tin tham chiếu; khi trả field không có trong index, engine có thể **FETCH record gốc**. Query được cover bởi index khi các điều kiện cần thiết và projection đáp ứng khả năng của engine.

Một unique index có thể bảo vệ uniqueness ở phạm vi tương ứng, nhưng không tự bảo vệ điều kiện như “tồn kho không âm” hoặc “Reservation chỉ xác nhận một lần”. Cần conditional writes/transaction ở tầng logic.

## 7. B-tree/B+tree: cấu trúc có thứ tự

Họ B-tree/B+tree và các biến thể cân bằng giữ khóa có thứ tự, thường qua những node/page có nhiều nhánh. Có thể hình dung:

~~~text
                [30 | 60]
               /    |     \
          [10,20] [40,50] [70,80]
~~~

Hình chỉ minh họa thứ tự, không biểu diễn byte layout hay node type chính xác của một engine.

Cấu trúc có thứ tự hữu ích cho:

- Equality: `sku="MOUSE-01"`.
- Range: `priceMinor BETWEEN 2000 AND 5000`.
- Sort và pagination khi key order thích hợp.
- Seek tới vị trí một cursor rồi đọc tiếp.

Một engine có thể dùng cấu trúc cây cho cả record chính và index phụ, nhưng hai cấu trúc có nhiệm vụ khác nhau. Một truy vấn theo index phụ có thể cần thêm bước đọc bản ghi. Cập nhật field được index đòi hỏi duy trì index, khiến write có chi phí cao hơn dù read nhanh hơn.

Không nên nói “B-tree” nghĩa là mọi document JSON luôn nằm kề nhau theo thứ tự trên SSD: caching, page split, record identifiers, compression và quản lý file làm câu chuyện vật lý phức tạp hơn.

## 8. Hash index và hash lookup

Một cấu trúc hash dùng giá trị băm của key để tìm bucket/entry:

~~~text
hash("session:u42") -> entry -> session value
hash("session:u43") -> entry -> session value
~~~

Điều này phù hợp với **exact-key lookup**. Một hash table thông thường không duy trì thứ tự khóa nên không tự hỗ trợ range/sort như một ordered tree. Redis và nhiều hệ key–value có thể dùng cấu trúc băm ở RAM nhưng lại dùng **cơ chế persistence khác** cho ổ đĩa.

Một thao tác `GET` rất nhanh không chứng minh value đã được ghi bền, key nằm trong một file riêng hay việc quét range có thể tối ưu. “Cấu trúc lookup trong RAM” và “định dạng lưu trữ bền vững” là hai tầng khác nhau.

## 9. Inverted index: lưu mối quan hệ từ đến tài liệu

Với dữ liệu tìm kiếm:

~~~text
p100: "wireless mouse"
p101: "wireless keyboard"
p102: "gaming mouse"

Postings:
  wireless -> {p100,p101}
  mouse    -> {p100,p102}
  keyboard -> {p101}
  gaming   -> {p102}
~~~

Query `wireless AND mouse` có thể kết hợp posting lists rồi xếp hạng. Một search engine thực tế còn có positions, term statistics, doc values, stored fields và các cơ chế codec/index khác.

**Inverted index không mặc định chứa đủ nguồn document để khôi phục nghiệp vụ.** Nếu index bị xóa nhưng còn Product source, có thể xây lại. Nếu nguồn Product mất và chỉ còn postings, các field như giá, trạng thái hoặc ghi chú có thể không còn. Một số search system cho phép lưu _source/stored fields, nhưng phải xác minh cấu hình, nội dung và giới hạn trước khi coi đó là bản phục hồi.

## 10. Multikey index: một record logic tạo nhiều index entries

Document:

~~~json
{"_id":"p100","tags":["wireless","mouse","bluetooth"]}
~~~

Index trên `tags` trong MongoDB có thể trở thành **multikey**, vì một document đóng góp các khóa theo các phần tử mảng:

~~~text
bluetooth -> p100
mouse     -> p100
wireless  -> p100
~~~

Truy vấn:

~~~javascript
db.products.createIndex({ tenantId: 1, tags: 1 });

db.products.find({
  tenantId: "t01",
  tags: "wireless"
});
~~~

Một index như vậy giúp membership lookup nhưng làm tăng số index entries và chi phí khi thêm/xóa phần tử. Với mảng object, chỉ mục không thay thế ngữ nghĩa query: nếu cần **cùng một variant** màu đen và có stock≥3 thì dùng `$elemMatch`, không dùng hai dotted conditions độc lập có thể khớp hai phần tử khác nhau.

Đây là ví dụ rõ ràng: một document logic có thể sinh nhiều entries ở tầng index, và mỗi entry có cách lưu vật lý riêng do engine quản lý.

## 11. LSM-tree: dữ liệu được ghi theo nhiều lớp

Một nhóm storage engine khác dùng cách tiếp cận **Log-Structured Merge-tree (LSM-tree)** hoặc biến thể. Thay vì bắt buộc cập nhật một vị trí trong file dữ liệu ngay lập tức, luồng thường gặp là:

1. Nhận mutation và ghi thông tin phục hồi theo chính sách **commit log/WAL**.
2. Đưa thay đổi vào cấu trúc trong RAM như **memtable**.
3. Khi đủ điều kiện, flush memtable thành file có thứ tự và thường bất biến, như **SSTable**.
4. Khi đọc, kết hợp dữ liệu từ memtable và các SSTables liên quan theo quy tắc version/timestamp.
5. **Compaction** hợp nhất file/phiên bản và thu hồi dữ liệu không còn cần theo policy.

~~~text
             WRITE
               |
        Commit log / WAL
               |
            Memtable
               |
             FLUSH
               v
       Immutable SSTables
          /    |    \
         L0   L1    L2       (chỉ minh họa)
               |
           COMPACTION
               |
       Merged / rewritten files
~~~

Không phải mọi LSM engine chia level theo cùng quy tắc. Có các chiến lược size-tiered, leveled, universal hoặc chính sách khác. **Thứ tự log, memtable, flush và ACK là chi tiết theo hợp đồng sản phẩm**, không phải tiêu chuẩn chung có thể suy từ hình.

### 11.1. Một key có thể còn nhiều phiên bản vật lý

Giả sử:

~~~text
T1: product:p100.status = ACTIVE
T2: product:p100.status = INACTIVE
T3: DELETE product:p100
~~~

Tại một thời điểm, bản cũ, bản mới và marker xóa có thể nằm ở nhiều SSTables/memtables khác nhau. Reader phải xác định kết quả **logic** hợp lệ theo version/timestamp, trong khi các file vật lý cũ có thể tồn tại cho tới khi compaction và retention cho phép dọn.

Điều này lý giải vì sao `UPDATE` hoặc `DELETE` thành công không đồng nghĩa byte cũ bị ghi đè ngay tại chỗ.

## 12. Page, block, segment, SSTable và file là khái niệm vật lý

| Đơn vị/cấu trúc | Vai trò thường gặp | Không đồng nghĩa |
|---|---|---|
| **Page** | Đơn vị quản lý cây, cache hoặc I/O | Một document duy nhất |
| **Block** | Đơn vị nén/mã hóa/đọc-ghi theo engine | Một response JSON |
| **Segment** | Một thế hệ dữ liệu/index, thường gần như bất biến | Một tenant |
| **SSTable** | File sorted/immutable thuộc LSM | Một bảng CQL duy nhất |
| **Data file** | Trang/record/metadata của engine | Một file JSON có thể sửa tay |
| **Index file** | Khóa/pointers/postings hoặc cấu trúc phụ | Toàn bộ dữ liệu gốc |
| **Log/journal** | Dữ liệu recovery theo policy | Backup dài hạn |
| **Manifest/metadata** | Mô tả file, schema/engine state | Bản ghi nghiệp vụ |

Một document lớn có thể trải trên nhiều phần lưu trữ tùy engine; nhiều document nhỏ có thể cùng nằm trong một page hoặc block. Compression khiến số byte disk khác logical size; các file tạm khi compaction/merge còn làm dung lượng tức thời tăng.

Các file storage engine không nên bị chỉnh sửa thủ công. Cần dùng API, công cụ backup/restore và quy trình vận hành tương ứng để tránh phá metadata và quan hệ giữa index/data.

## 13. WAL, journal và commit log bảo vệ điều gì?

Một câu hỏi cốt lõi của chương **Lưu trữ và độ bền**: *nếu dữ liệu đã được ứng dụng nhận là ghi thành công nhưng data page chưa flush, mất điện có làm mất nó không?*

Một phương pháp phổ biến là **write-ahead logging**: engine ghi thông tin cần cho crash recovery vào log theo quy tắc ordering và sync. Khi restart, hệ có thể replay các thay đổi đã được ghi bền theo hợp đồng.

~~~text
API gửi ghi
   |
Validate / conditional update / transaction
   |
Thay đổi trạng thái trong RAM, ghi recovery log
   |
Điểm trả ACK theo write concern / sync policy
   |
Data pages/SSTables được flush hoặc checkpoint sau
   |
Log cũ được dọn theo retention/checkpoint
~~~

Đây là sơ đồ khái niệm. **Không phải mọi ACK đều chờ fsync**; một số cấu hình ACK trước khi log thực sự bền trên lưu trữ có thể sống qua mất điện. Cần xác định cấu hình của sản phẩm, write concern, replica policy và giới hạn của thiết bị lưu trữ.

### 13.1. WAL không phải business event log

| WAL/journal | Event sourcing / event log nghiệp vụ |
|---|---|
| Mục tiêu chính: crash recovery của storage engine | Mục tiêu: tái hiện thay đổi nghiệp vụ/projection |
| Format do engine quản lý | Schema sự kiện như `OrderCreated`, `PaymentCaptured` |
| Retention có thể gắn checkpoint/compaction | Retention theo yêu cầu nghiệp vụ |
| Có thể ghi physical/logical mutations | Ghi điều xảy ra ở miền nghiệp vụ |
| Không tự là nguồn audit lâu dài | Có thể làm nguồn chuẩn khi kiến trúc quy định |

Một WAL không thay thế backup; một Kafka topic chứa event nghiệp vụ không tự bảo vệ toàn bộ page/index/log trạng thái của database.

## 14. Flush, checkpoint, fsync và compaction khác nhau

- **Cache/buffer:** giữ data/index pages hoặc record trong RAM.
- **Flush:** chuyển dữ liệu từ cấu trúc/bộ đệm sang một tầng lưu trữ tiếp theo.
- **Checkpoint:** ghi/đánh dấu trạng thái engine có thể phục hồi nhất quán theo cách triển khai.
- **fsync hoặc durable sync:** yêu cầu đồng bộ ghi xuống mức lưu trữ có bảo đảm tương ứng; kết quả cuối còn tùy hệ điều hành, phần cứng và cloud provider.
- **Compaction:** gộp/viết lại file hoặc segment, làm sạch phiên bản/tombstone đủ điều kiện và tối ưu cấu trúc.
- **Index rebuild:** tái tạo cấu trúc chỉ mục từ nguồn dữ liệu có thẩm quyền theo quy trình.

Flush có thể xảy ra trước hoặc sau một phần compaction khác; compaction còn tiếp tục khi API đã ACK từ lâu. Không được gộp “đã flush” với “đã bền qua mọi lỗi”. Cần nói rõ flush vào tầng nào, data/log đã sync chưa, replica nào đã xác nhận, và lỗi cần sống sót là mất process, mất node, mất zone hay cả region.

## 15. MongoDB: document BSON, index và WiredTiger

Ứng dụng nhìn thấy document qua MongoDB driver. Với storage engine **WiredTiger**, dữ liệu và index được quản lý bởi các cấu trúc cây/page, cache, journal/checkpoint và cơ chế nén theo cấu hình.

Ví dụ:

~~~javascript
db.products.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true, name: "uq_tenant_sku" }
);

db.products.find({
  tenantId: "t01",
  sku: "MOUSE-01"
}).explain("executionStats");
~~~

Một plan có thể dùng `IXSCAN` để tìm record references rồi `FETCH` document chính. Với query đủ điều kiện cho **covered index**, engine có thể trả các field mà không phải lấy toàn bộ document, nhưng không phải mọi query có index đều được cover.

MongoDB không lưu mỗi document như một file JSON riêng. Record encoding, file/page, compression và journal thuộc storage engine, không phải hợp đồng JSON API.

### 15.1. Mức độ bền của ACK

Trong replica set, write concern như `w:1` hoặc `w:"majority"` cùng tùy chọn journaling `j` và cấu hình liên quan tác động mức ghi được công nhận thành công. Không nên nói:

- “Primary đã ACK thì chắc chắn không mất ghi nếu failover”.
- “Majority ACK nghĩa là mọi replica đều đã có bản ghi”.
- “Bật journal là mọi write luôn sống qua mọi kiểu mất vùng”.

Bảo đảm thực tế phụ thuộc tổ hợp write concern, journaling, cấu hình majority, topology và failure model. Đọc tài liệu đúng phiên bản và dùng phép thử phục hồi phù hợp mục tiêu RPO.

## 16. Cassandra/ScyllaDB: partition logic và SSTables vật lý

Một bảng CQL:

~~~sql
CREATE TABLE events_by_device_day (
    device_id text,
    day date,
    occurred_at timestamp,
    event_id uuid,
    metric_value double,
    PRIMARY KEY ((device_id, day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Ý nghĩa logic: mỗi partition chứa sự kiện của device trong một ngày; clustering columns hỗ trợ đọc theo thời gian trong phạm vi partition. Query:

~~~sql
SELECT occurred_at, event_id, metric_value
FROM events_by_device_day
WHERE device_id = 'd42'
  AND day = '2026-11-14'
LIMIT 20;
~~~

Đường vật lý thường liên quan commit log, memtable, SSTables, cache, compaction và các cấu trúc phụ. CQL row không có nghĩa một row nằm trong một file riêng.

~~~text
Mutation -> Commit log + Memtable -> Flush -> SSTables
                  |                             |
                  +----------- Read ------------+
                                                |
                                           Compaction
~~~

Partition key giúp định vị dữ liệu theo mô hình phân phối của cluster nhưng **một partition không đồng nghĩa một SSTable**. Nhiều partition có thể cùng nằm trong một file; một partition có thể có dữ liệu qua nhiều SSTables trước compaction.

### 16.1. Bloom filter không phải nguồn dữ liệu

Một số LSM engines dùng **Bloom filter** để giảm đọc file không chứa key. Bloom filter có thể có false positive (“có thể chứa” dù không có); một Bloom filter hợp lệ không được gây false negative khi trả lời key mà nó đã được xây dựng để đại diện.

Nó là **cấu trúc phụ trợ đọc**, không chứa đủ dữ liệu để khôi phục một hàng. Tối ưu Bloom filter memory/I/O phải dựa vào workload và metric, không chỉ dựa vào việc bật một tính năng.

### 16.2. Secondary index và storage engine không thể suy từ SQL

Cassandra/ScyllaDB có các cơ chế secondary index theo sản phẩm/phiên bản khác nhau. Không nên suy “có CREATE INDEX thì nó là một cây B-tree giống MongoDB” hoặc “có index thì mọi query theo mọi cột đều nhanh”. Phân vùng, kiểu index, điều kiện filter và compaction quyết định chi phí thực tế.

## 17. Redis: logic key–value, RAM encoding và RDB/AOF

Redis cung cấp những kiểu dữ liệu logic:

~~~redis
SET session:u42 "{\"state\":\"ACTIVE\"}" EX 600
HSET product:p100 name "Wireless Mouse" status "ACTIVE"
SADD tag:wireless p100 p101
ZADD leaderboard 100 u42
~~~

Ở RAM, Redis có các cấu trúc và **internal encodings** tối ưu theo kiểu/size; encoding có thể thay đổi qua phiên bản. Nó không đồng nghĩa mỗi key có một file vật lý tương ứng.

Redis có các cơ chế persistence được cấu hình như:

| Cơ chế | Vai trò | Rủi ro cần kiểm tra |
|---|---|---|
| **RDB** | Snapshot trạng thái tại thời điểm được tạo | Có thể mất các thay đổi sau snapshot gần nhất nếu chưa có cơ chế khác |
| **AOF** | Ghi log thao tác để replay/recovery theo policy | Fsync policy, trạng thái file và cửa sổ mất dữ liệu |
| **Replication** | Duy trì bản sao trên node khác | Replica lag, failover và ACK không đồng nghĩa durable ở mọi node |
| **Eviction** | Loại key để giảm áp lực RAM theo policy | Key có thể mất dù TTL chưa hết |

Một lệnh `INCR`/script có thể atomic trong phạm vi Redis server, nhưng đó **không tự bảo đảm durability sau node/region failure**. Redis là lựa chọn phù hợp cho nhiều dạng cache có thể tái tạo; nếu dùng làm nguồn giao dịch quan trọng, cần chứng minh persistence, replication và recovery đáp ứng RPO/RTO.

### 17.1. Quan sát Redis ở các tầng khác nhau

~~~redis
TYPE product:p100
MEMORY USAGE product:p100
OBJECT ENCODING product:p100
INFO memory
INFO persistence
~~~

`TYPE` nói về kiểu logic. `MEMORY USAGE` nói về chi phí RAM theo Redis; nó **không phải byte kích thước JSON hoặc file RDB/AOF**. `OBJECT ENCODING` cho một encoding thực tế tại thời điểm gọi và có thể bị hạn chế bởi ACL/managed service.

## 18. DynamoDB: hợp đồng API và index, không suy đoán file nội bộ

DynamoDB là dịch vụ managed cung cấp logical item, primary key, `GetItem`, `Query`, `UpdateItem`, GSI/LSI và các tính năng consistency/transaction, backup hoặc PITR theo hợp đồng.

~~~json
{
  "PK": "TENANT#t01",
  "SK": "PRODUCT#p100",
  "name": "Wireless Mouse",
  "status": "ACTIVE",
  "tags": ["wireless", "mouse"]
}
~~~

Một GSI có thể phục vụ query theo trạng thái hoặc danh mục. Nhưng **GSI không phải lời xác nhận rằng người dùng có thể quan sát một B-tree file hay SSTable cụ thể bên dưới dịch vụ**.

Phân biệt:

- Partition key của API là một khóa logic để phân phối/truy cập, không phải tên file.
- GSI/LSI có phạm vi consistency, khả năng cập nhật và chi phí riêng.
- FilterExpression có thể lọc sau bước đọc theo key/index, không tự biến một attribute bất kỳ thành index lookup.
- Backup/PITR của dịch vụ phải được đánh giá theo cửa sổ giữ, restore và RPO/RTO, không đoán từ việc không quản lý ổ đĩa.

Với managed database, hợp đồng **có thể kiểm chứng** mới là căn cứ thiết kế: key/query semantics, consistency, transaction scope, durability, backup và quotas.

## 19. Lucene/search engine: segment và inverted index

Một document tìm kiếm:

~~~json
{
  "productId": "p100",
  "name": "Wireless Mouse",
  "description": "Bluetooth optical device",
  "priceMinor": 2999
}
~~~

Một search engine có thể lưu:

- **Inverted postings:** term → document IDs/positions.
- **Stored fields/source:** field được giữ lại để trả response theo cấu hình.
- **Doc values:** cấu trúc cột phục vụ sort/aggregation ở những loại field thích hợp.
- **Segments:** đơn vị index gần như bất biến, được hợp nhất qua segment merge.
- **Recovery log/translog:** hỗ trợ phục hồi theo hệ và cấu hình.

Thay đổi một search document có thể tạo các version/segment entries mới và đánh dấu bản cũ không còn hợp lệ, thay vì sửa đúng một file tại vị trí cũ. Delete và update có thể phải đợi merge/retention để thu hồi không gian.

### 19.1. Refresh, durability và replication khác nhau

- **Search visibility/refresh:** query đã thấy document mới chưa?
- **Durability:** sau mất điện, write đã ACK có phục hồi không?
- **Replication:** khi shard/node hỏng, replica đã theo kịp đến đâu?

Một index refresh không tự là fsync; một replica ACK không tự đồng nghĩa search query trên mọi node đã refresh. Không gộp ba thuộc tính thành câu “đã index thành công” nếu nghiệp vụ cần độ mới chính xác.

## 20. Index không tự thay được source of truth

Ví dụ Product có:

~~~javascript
{
  _id: "p100",
  name: "Wireless Mouse",
  tenantId: "t01",
  priceMinor: 2999,
  notes: "internal",
  tags: ["wireless","mouse"]
}
~~~

Index `{tenantId:1,tags:1}` thường không chứa đầy đủ `name`, `priceMinor` và `notes`. Nếu chỉ còn index entries, ứng dụng không thể tự suy rằng khôi phục được cả document.

| Thành phần | Thường là nguồn có thẩm quyền? | Có thể rebuild từ |
|---|---|---|
| Product transaction record | Có thể có, theo thiết kế | Backup, bản sao hoặc event log thích hợp |
| Secondary index | Không | Product data |
| Search projection | Thường không | Product source + pipeline |
| Cache Product | Thường không | Database/source |
| Analytics aggregate | Thường không | Raw events/source nếu còn |
| Event stream khi dùng event sourcing | Có thể có | Event backup/retention theo kiến trúc |

Nếu source hỏng, index nhanh cũng không thay thế được **backup và khả năng restore**. Nếu index hỏng nhưng source còn đầy đủ, có thể xây lại theo một quy trình có thể giám sát và replay.

## 21. Từ API update tới dữ liệu có thể phục hồi

Một lệnh cập nhật logic:

~~~javascript
db.products.updateOne(
  {
    _id: "p100",
    tenantId: "t01",
    version: 7
  },
  {
    $set: { status: "INACTIVE" },
    $inc: { version: 1 }
  }
);
~~~

Hãy tách tám câu hỏi:

1. **Logic:** record có đúng `version=7` và chuyển trạng thái có được phép không?
2. **Index:** những index chứa `status` hoặc `version` có cần cập nhật không?
3. **RAM:** trang/record/memtable/cache nào được thay đổi?
4. **Recovery:** thông tin nào được ghi vào WAL/journal/commit log?
5. **ACK:** điều kiện write concern/sync nào khiến client nhận thành công?
6. **Replica:** node/region nào đã nhận hoặc ghi bền theo yêu cầu?
7. **Physical files:** phần dữ liệu nào được flush, checkpoint/compact về sau?
8. **Backup:** snapshot/PITR nào chứa kết quả nếu toàn cụm bị hỏng?

Kết quả `matchedCount=1` phản ánh **thao tác ghi logic theo hợp đồng driver**, không tự khẳng định mọi data page đã tới SSD hoặc mọi replica đều có bản sao. Mức bền phải xét các cấu hình ghi và failure model.

### 21.1. Cửa sổ crash

~~~text
T1: Client gửi update
T2: Engine tiếp nhận/thực hiện thay đổi
T3: Recovery log đạt mốc bền theo policy
T4: Client nhận ACK
T5: Data pages/SSTables được checkpoint/flush
T6: Replica và backup đạt các mốc riêng
~~~

Hình chỉ đánh dấu những câu hỏi cần kiểm tra, **không mô tả thứ tự cố định của mọi engine**. Có cấu hình ACK trước sync, có cấu hình chờ journal/replica, có các bước chạy song song. Khi thử mất điện tại T2/T4/T5, phải kết luận dựa trên hợp đồng thực tế, không dựa vào sơ đồ.

## 22. Durability, replication, consistency và availability

| Thuộc tính | Câu hỏi | Ngộ nhận |
|---|---|---|
| Durability | Write đã ACK sống qua loại crash nào? | ACK nghĩa mọi file đã fsync |
| Replication | Bao nhiêu bản sao và ACK đến đâu? | Có 3 replica nghĩa không mất dữ liệu |
| Consistency | Read ở node khác thấy phiên bản nào? | Có replica nghĩa đọc mới ở mọi nơi |
| Availability | Khi một node hoặc liên kết lỗi, hệ còn phục vụ không? | Durable đồng nghĩa luôn online |

Một hệ có local WAL bền vẫn có thể ngừng phục vụ khi node mất. Một hệ có replica nhưng xác nhận write trước khi dữ liệu được nhân bản tới số node cần thiết có thể mất một số ghi khi failover. Một search projection có thể chạy tốt nhưng trả kết quả cũ do refresh lag.

Mục tiêu vận hành cần nêu:

- **RPO:** mức mất dữ liệu tối đa chấp nhận được sau sự cố.
- **RTO:** thời gian khôi phục dịch vụ tối đa chấp nhận.
- **Read freshness:** độ mới/mức consistency từng API cần.
- **Write acceptance:** các điều kiện log/replica trước khi ACK.
- **Failure model:** mất process, node, zone, region, corruption, thao tác xóa nhầm.

Không có một cấu hình nhanh nhất phù hợp mọi mục tiêu. Độ trễ write, mức sẵn sàng khi phân vùng mạng, dung lượng và chi phí có đánh đổi.

## 23. Snapshot, backup và PITR không phải replication

**Replica** chủ yếu phục vụ bản sao/failover trong điều kiện thiết kế. Một lệnh DELETE nhầm có thể được sao chép tới tất cả replica, nên replica không thay thế backup.

| Cơ chế | Hữu ích trước | Không tự giải quyết |
|---|---|---|
| WAL/journal | Một số crash trước data-page flush | Mất tất cả storage hoặc phục hồi lịch sử lâu dài |
| Replication | Lỗi node, tăng khả năng phục vụ theo topology | Xóa nhầm được nhân bản |
| Snapshot | Trạng thái tại thời điểm T | Thay đổi sau T nếu không có log |
| Backup độc lập | Restore sau corruption/operator error theo retention | RTO thấp nếu chưa diễn tập |
| PITR | Khôi phục về điểm trong cửa sổ có log | Các mốc ngoài retention |
| Rebuild index | Tái lập index khi source còn tốt | Mất nguồn dữ liệu chính |

Một snapshot trên cụm nhiều shard không nhất thiết tạo trạng thái nghiệp vụ nhất quán giữa mọi shard nếu chưa có giao thức backup phù hợp. Sau restore, search/cache/analytics projections có thể cần rebuild/replay; không nên giả định chúng tự cùng mốc với source.

Phải **diễn tập restore**, bao gồm kiểm tra bản ghi, xây lại index, quyền và khóa mã hóa, phiên bản schema, RPO thực tế và thời gian phục vụ trở lại. Chỉ thấy “backup job success” chưa đủ chứng minh đáp ứng RTO.

## 24. DELETE logic và byte vật lý có vòng đời khác nhau

Một lệnh:

~~~javascript
db.products.deleteOne({
  _id: "p100",
  tenantId: "t01"
});
~~~

có thể khiến Product không còn hiển thị trong query logic được công nhận. Nhưng byte cũ có thể vẫn xuất hiện trong page/segment, journal, replica, snapshot hoặc backup tùy thời hạn.

Trong LSM, DELETE có thể ghi **tombstone** để các phiên bản cũ ở SSTable khác không được đọc lại. Compaction về sau thu hồi chúng khi an toàn. Trong page-oriented engine, dung lượng có thể được đánh dấu tái sử dụng thay vì file nhỏ đi ngay. Trong search index, merge có thể là bước thu hồi dung lượng sau khi document cũ bị đánh dấu không còn live.

~~~text
T0: Product còn tồn tại
T1: DELETE đã commit; query không còn trả Product theo hợp đồng
T2: Cache/search projection cập nhật việc xóa
T3: Compaction/merge tái sử dụng hoặc thu hồi file space
T4: Snapshot/backup cũ hết retention
~~~

Các mốc T1–T4 có thể cách nhau đáng kể. Không nên dùng phản hồi DELETE thành công để khẳng định tất cả bản sao vật lý biến mất.

### 24.1. Tombstone và replica cũ

Nếu một replica còn bản ghi cũ, chỉ thị xóa cần được giữ theo cơ chế repair/replication/retention để tránh nguy cơ dữ liệu cũ xuất hiện trở lại. Vì vậy compaction/tombstone cleanup phải tuân theo semantics hệ, không chỉ là thao tác “giải phóng disk” tùy ý.

## 25. TTL có ba lớp ý nghĩa

Giả sử session có `expiresAt = 10:00 UTC`:

1. **Nghiệp vụ:** từ 10:00, session không còn hợp lệ để dùng.
2. **Logic database:** record trở thành hết hạn/đủ điều kiện dọn theo hợp đồng TTL của engine.
3. **Vật lý:** page/SSTable/log/backup chứa byte cũ được thu hồi về sau theo chính sách.

Ví dụ MongoDB:

~~~javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
~~~

TTL cleanup không phải timer bảo đảm xóa đúng microsecond. Hệ xác thực vẫn phải kiểm tra deadline; Reservation hết hạn không được chỉ xóa record rồi giả định pool tự hoàn quota ở document khác. Cần state transition và thao tác bù trừ theo cơ chế nhất quán phù hợp.

Redis, DynamoDB, Cassandra có TTL semantics và background reclamation khác nhau; phải xác nhận phiên bản/cấu hình thay vì gộp chung chữ TTL.

### 25.1. Xóa thông tin nhạy cảm

Nếu cần xóa dữ liệu theo hợp đồng/quy định áp dụng, phải tính đến nguồn chính, index, cache, search projection, replica, log, backup/snapshot và quản lý khóa mã hóa. Một lệnh DELETE không phải bằng chứng xóa sạch byte ngay ở mọi tầng; quy trình phải có phạm vi/retention/bằng chứng thực thi rõ ràng.

## 26. Dung lượng logic, index, RAM và disk không bằng nhau

Document JSON kích thước 2 KiB không chứng minh chi phí trên SSD của document đó là 2 KiB.

| Đại lượng | Ý nghĩa |
|---|---|
| Serialized size | Số byte của JSON/BSON hoặc định dạng trao đổi |
| Logical record size | Giá trị ứng dụng/engine ghi nhận trước một số dạng nén |
| Index size | Entries, page, postings, segment phụ |
| Cache/resident memory | RAM giữ data/index/metadata |
| Physical disk | Data files, compression, fragmentation, log/temp files |
| Replicated storage | Dung lượng ở các node/region |
| Backup/snapshot | Bản dữ liệu phục hồi theo retention |
| Network payload | Request/response và overhead giao thức |

Một cách suy nghĩ tổng quát:

\[
\text{Storage footprint} \approx
\text{data}+\text{index}+\text{log/metadata/temp}
+\text{replica/backup}
\]

Đây không phải công thức cộng mọi số liệu dashboard trực tiếp, vì có metric đã bao gồm thành phần khác. Compression có thể làm disk nhỏ hơn serialized data; nhiều index hoặc multikey có thể làm index rất lớn. Một lần compaction/merge có thể cần **free space tạm thời** để ghi file mới trước khi bỏ file cũ.

## 27. Read, write và space amplification

- **Write amplification:** một thay đổi logic làm engine ghi nhiều byte/thao tác hơn vì journal, index, flush và compaction.
- **Read amplification:** một truy vấn logic phải kiểm tra nhiều pages, index entries, SSTables hoặc remote requests.
- **Space amplification:** phải giữ thêm byte vì version cũ, tombstone, index, metadata, fragmentation và compaction.

~~~text
Một logical update:
  -> ghi recovery log
  -> sửa page/memtable
  -> sửa secondary indexes
  -> về sau flush/checkpoint
  -> về sau compaction/merge
  -> replicate và backup theo policy
~~~

Một metric “write amplification” đo tại disk của một node không giống tổng byte replication qua cả cụm; cần ghi rõ phạm vi đo.

Thêm index có thể giảm read p95 nhưng tăng write p99 do phải duy trì index entries. LSM compaction có thể gây thêm I/O ở nền, đôi khi tăng tail latency nếu thiếu disk headroom. Không đánh giá công nghệ chỉ bằng một câu GET trong cache nóng.

## 28. Đọc bằng index vẫn có thể cần đọc record gốc

Query:

~~~javascript
db.products.find(
  {
    tenantId: "t01",
    status: "ACTIVE",
    tags: "wireless"
  },
  {
    name: 1,
    priceMinor: 1
  }
).limit(20);
~~~

Luồng khái niệm:

~~~text
Query planner
   |
Index seek / scan
   |
Index keys từ RAM hoặc disk
   |
Candidate record IDs
   |
FETCH document gốc nếu cần
   |
Residual filter, sort, projection
   |
Response qua network
~~~

Có query được index cover, có query vẫn phải FETCH, có query không chọn index vì điều kiện quá ít chọn lọc. Cache lạnh và cache nóng tạo physical I/O khác nhau dù query logic giống hệt.

Cần xem query plan và metric:

- Index nào được chọn, key bounds ra sao?
- Keys examined, documents examined và nReturned.
- Có FETCH hoặc SORT riêng không?
- Cache hit/miss, disk I/O, remote shard fan-out.
- p50/p95/p99 ở tải và phân bố thực tế.

**Có index không có nghĩa mọi trường kết quả nằm trong index hoặc lúc nào cũng ở RAM.**

## 29. Quan sát từng tầng trong môi trường thực hành

### 29.1. MongoDB

~~~javascript
// Tầng logic.
db.products.findOne({ _id: "p100" });

// Index đã khai báo.
db.products.getIndexes();

// Đường truy cập.
db.products.find({
  tenantId: "t01",
  status: "ACTIVE",
  tags: "wireless"
}).explain("executionStats");

// Thống kê data/index/storage.
db.products.stats({ scale: 1024 });
~~~

Các chỉ số `size`, `storageSize`, `totalIndexSize` phản ánh những khía cạnh khác nhau. `size` thường liên quan logical data size, `storageSize` phản ánh storage allocated theo engine và `totalIndexSize` cho index size; xem định nghĩa chi tiết của đúng phiên bản, không coi chúng là ba phép đo cùng một thứ.

### 29.2. Redis

~~~redis
TYPE product:p100
MEMORY USAGE product:p100
OBJECT ENCODING product:p100
INFO memory
INFO persistence
~~~

`TYPE` cho kiểu logic, `MEMORY USAGE` cho chi phí RAM, `OBJECT ENCODING` cho encoding nội bộ. `INFO persistence` phản ánh trạng thái persistence, không tự chứng minh một request riêng đã ghi bền theo failure model. Managed service/ACL có thể giới hạn lệnh quan sát.

### 29.3. Cassandra/ScyllaDB

~~~sql
SELECT occurred_at, event_id, metric_value
FROM events_by_device_day
WHERE device_id = 'd42'
  AND day = '2026-11-14'
LIMIT 20;
~~~

Có thể quan sát SSTable count, compaction backlog, read/write latency, tombstone scanning và disk usage qua server metrics hoặc công cụ như `nodetool` trong môi trường phù hợp. Không nên tìm “file vật lý của row d42”, vì một partition có thể nằm qua nhiều SSTables.

## 30. Thực nghiệm với cùng dữ liệu logic và nhiều chỉ mục

Một dataset **giả định để thiết kế bài thực hành**:

- 1 triệu Product documents, trung bình 5 tags, 1% có trên 100 tags.
- 50 tenant, một tenant lớn chiếm 40% dữ liệu.
- 90% GET theo ID, 8% filter tenant/status/tags, 2% range giá.
- Một số product thay đổi tags/status thường xuyên.

Thực hiện:

1. Định nghĩa kết quả logic của các query trước khi đo.
2. Chạy query khi chưa có index phụ phù hợp; ghi plan và độ trễ.
3. Tạo index ghép/multikey theo access pattern; đo read và write cùng workload.
4. Ghi logical data size, index size, physical/storage metrics và cache memory.
5. Với LSM/search, quan sát thêm sau flush/compaction/merge.
6. Xóa một nhóm record; so logical count với physical space trước/sau cleanup.
7. Thử restart/crash/failover trong môi trường thử nghiệm, đối chiếu write ACK policy.
8. Diễn tập backup/restore và đo RPO/RTO.
9. Ghi version, topology, data seed, index, persistence policy, concurrency và metric để có thể tái hiện.

Không dùng một lần `du -sh` hoặc `countDocuments` làm căn cứ duy nhất. Một phép đo disk size không chứng minh đúng logic; một phép đo query latency không chứng minh độ bền.

## 31. Các hiểu nhầm thường gặp

| Hiểu nhầm | Sự thật |
|---|---|
| Document JSON là một file JSON trên ổ | Engine có encoding, page và file layout riêng |
| Index là bản backup đầy đủ | Index thường không chứa đủ source |
| Index entry luôn trỏ tới byte offset cố định | Có record ID, page, posting, segment tùy engine |
| B-tree nghĩa toàn bộ record nằm theo thứ tự trên SSD | Còn cache, page layout và nhiều index |
| LSM chỉ có một SSTable hiện hành | Memtable và nhiều SSTables/versions có thể cùng tồn tại |
| WAL là business event log | WAL phục vụ recovery, event log phục vụ nghiệp vụ |
| ACK nghĩa fsync và tất cả replica đã nhận | Phụ thuộc write concern, sync policy và topology |
| Có replica thì khỏi cần backup | Xóa nhầm/corruption có thể lan qua replica |
| DELETE lập tức xóa mọi byte | Tombstone, merge, snapshot/backup có thời hạn |
| TTL là timer nghiệp vụ chính xác | Background cleanup có thể trễ |
| Compaction miễn phí | Có I/O, CPU, temp space và tác động tail latency |
| Index size bằng logical data size | Index entries, encoding và compression khác |
| Bloom filter chứa dữ liệu để khôi phục | Chỉ trợ giúp kiểm tra khả năng membership |
| Search refresh là fsync | Visibility khác durability |
| Managed database có thể đoán internal file layout | Chỉ dựa vào hợp đồng/tài liệu đã công bố |
| Index bảo đảm p99 nhanh | Phải xét selectivity, plan, cache và workload |

## 32. Bài tập và câu hỏi tự kiểm tra

### Bài A — Phân loại ba tầng

Cho: Product JSON, index `{tenantId:1,tags:1}`, WAL file, BSON encoding, SSTable, B-tree page, Redis hash, RDB snapshot, Lucene postings và bản backup ở region khác.

1. Phân loại từng mục thành dữ liệu logic, index/access structure, physical representation hoặc durability/backup.
2. Vì sao BSON record encoding không mô tả toàn bộ WiredTiger file layout?
3. Nếu mất index tags nhưng còn Product source, có thể phục hồi thế nào?
4. Nếu chỉ còn postings mà mất Product source, có thể thiếu những field nào?
5. Redis hash có thể vừa là kiểu logic vừa có internal encoding vật lý như thế nào?

### Bài B — Ghi và xóa

1. Vẽ đường đi từ API UPDATE qua RAM, index, recovery log và ACK theo engine được chọn.
2. Mô tả cửa sổ mất dữ liệu khi process/node crash ngay sau ACK ở một cấu hình cụ thể.
3. Gọi DELETE rồi thấy count giảm; có suy ra byte trong file giảm ngay không?
4. Vì sao tombstone cần được giữ đủ lâu so với replica repair?
5. Nếu xóa nhầm, vì sao replication không thay thế được PITR?

### Bài C — So sánh công nghệ

1. Phân biệt document BSON/index B-tree và WiredTiger pages ở MongoDB.
2. Phân biệt partition logic, memtable, SSTables và compaction ở Cassandra.
3. RDB và AOF của Redis xử lý hai cách lưu bền nào?
4. DynamoDB GSI công bố đường truy cập nào nhưng không công bố điều gì về file?
5. Inverted postings, search refresh và segment merge khác nhau ra sao?

### Bài D — Thiết kế benchmark và recovery drill

1. Đo query theo tag trước/sau compound/multikey index.
2. Ghi keys/docs examined, p95/p99, write latency, index/storage size.
3. Dùng cache nóng/lạnh và giải thích khác biệt I/O.
4. Thử restore source rồi xây lại search projection theo replay.
5. Đặt mục tiêu RPO/RTO cho hệ Order và một cache dễ tái tạo; so sánh cấu hình.

### Tự kiểm tra

1. Ba tầng khác nhau về trách nhiệm gì?
2. Vì sao JSON không đồng nghĩa file trên SSD?
3. Hash index và ordered-tree index khác nhau ở range query như thế nào?
4. Multikey làm một document có nhiều index entries ra sao?
5. Vì sao một LSM key có thể còn nhiều physical versions?
6. WAL khác event sourcing và backup ở đâu?
7. Flush, fsync, checkpoint, compaction có thay thế nhau được không?
8. MongoDB index có luôn đủ field để trả query mà không FETCH không?
9. Cassandra partition key có nghĩa mỗi partition một file không?
10. Redis có lệnh atomic thì đã đủ durability qua failover chưa?
11. Search refresh có đồng nghĩa một write đã ghi bền không?
12. Replica và PITR bảo vệ những lỗi khác nhau nào?
13. DELETE logic và physical reclamation có thể cách nhau bao lâu/vì sao?
14. TTL có thay thế quy tắc hết hạn nghiệp vụ không?
15. Kích thước JSON và index/disk/RAM khác nhau thế nào?
16. Khi thêm index, write amplification thường thay đổi ra sao?
17. Bloom filter có thể dùng để khôi phục bản ghi không?
18. Query plan cần xem những chỉ số nào ngoài latency?
19. Vì sao phải thử restore, không chỉ kiểm tra backup job?
20. Điều kiện nào cần biết trước khi gọi một write “durable”?

## 33. Tổng kết: thiết kế theo logic, truy cập bằng chỉ mục, bảo vệ ở tầng vật lý

**Dữ liệu logic** định nghĩa Product, Order, Event và bất biến mà ứng dụng cần bảo vệ. **Chỉ mục** giúp tìm theo khóa, khoảng giá trị, mảng, từ khóa hoặc quan hệ với chi phí chấp nhận được. **Định dạng lưu trữ vật lý** quyết định cách record/index được mã hóa, phân trang, nén, ghi log, compact, sao chép và phục hồi.

Một document JSON không nhất thiết là file JSON; một index nhanh không tự thay thế backup; một write được ACK vẫn phải được đánh giá theo write concern, sync policy và replica. DELETE/TTL làm thay đổi khả năng nhìn thấy dữ liệu logic theo hợp đồng, không chứng minh tất cả bản sao byte đã biến mất ngay.

Cách làm có hệ thống: **xác định nguồn dữ liệu có thẩm quyền → mô tả bất biến và query → chọn index/access path → hiểu engine và mức ACK/retention → đo read/write amplification cùng p95/p99 → diễn tập RPO/RTO và đối soát**. Khi tách đúng ba tầng, hệ NoSQL có thể vừa trả kết quả nghiệp vụ đúng, vừa vận hành hiệu quả, vừa có khả năng phục hồi trước lỗi thực tế.





