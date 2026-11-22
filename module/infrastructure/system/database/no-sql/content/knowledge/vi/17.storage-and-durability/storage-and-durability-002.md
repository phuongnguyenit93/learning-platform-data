# Hash table, B-tree và LSM-tree trong các thiết kế lưu trữ

Trong cơ sở dữ liệu NoSQL, việc tổ chức dữ liệu ở tầng ứng dụng — document, key–value, wide-column hay graph — **không đồng nghĩa với cách dữ liệu thực sự được cất giữ và tìm kiếm trong bộ nhớ, trên SSD hoặc trên đĩa**. Hai DBMS cùng cung cấp thao tác `GET key`, `PUT key value` nhưng có thể sử dụng các cấu trúc nội bộ rất khác nhau. Một hệ tìm dữ liệu qua hash table trong RAM; một hệ tìm qua cây B-tree được tổ chức theo các trang; một hệ nhận ghi vào memtable rồi hợp nhất các tệp sắp xếp theo mô hình LSM-tree.

Ba họ cấu trúc đặc biệt quan trọng là:

- **Hash table**: ánh xạ khóa qua hàm băm để định vị bucket/vị trí, thường hiệu quả cho truy cập đúng khóa.
- **B-tree/B+tree**: cây tìm kiếm cân bằng, lưu khóa theo thứ tự, phù hợp với truy vấn theo khóa và theo khoảng.
- **LSM-tree** (*Log-Structured Merge-tree*): tối ưu đường ghi bằng ghi tuần tự, memtable và các tệp dữ liệu đã sắp xếp, sau đó dùng compaction để tổ chức lại dữ liệu.

Chúng đều có thể phục vụ cơ sở dữ liệu, nhưng khác nhau về **đọc theo khóa, quét theo khoảng, ghi cập nhật, chi phí nền, độ khuếch đại đọc/ghi, dung lượng và phục hồi sau lỗi**.

Điểm quan trọng của chương *Lưu trữ và độ bền* là: **cấu trúc chỉ mục/lưu trữ quyết định cách tìm và sửa dữ liệu; còn độ bền (*durability*) phụ thuộc thêm vào cơ chế ghi log, đồng bộ xuống thiết bị, checkpoint, phục hồi và cấu hình của toàn hệ thống**. Chỉ nói “dùng B-tree” hoặc “dùng LSM” chưa chứng minh rằng dữ liệu đã commit sẽ sống sót sau mất điện.

## 1. Trước tiên, phân biệt mô hình dữ liệu, chỉ mục và storage engine

Xét một document:

~~~json
{
  "orderId": "O1007",
  "customerId": "C42",
  "status": "PAID",
  "createdAt": "2026-11-14T09:30:00Z",
  "totalMinor": 125000,
  "currency": "VND"
}
~~~

Một ứng dụng có thể đặt câu hỏi:

~~~text
GET orderId = O1007
FIND orders WHERE customerId = C42 ORDER BY createdAt DESC
UPDATE orderId = O1007 SET status = SHIPPED
~~~

Ở đây có ba lớp:

~~~text
Lớp nghiệp vụ / API
  Document Order, GET/UPDATE/FIND
                 │
                 ▼
Lớp đường truy cập
  Khóa chính; chỉ mục customerId + createdAt
                 │
                 ▼
Lớp storage engine
  Hash table, B-tree/B+tree hoặc LSM-like structures
                 │
                 ▼
RAM, SSD/đĩa, bộ đệm trang, WAL, tệp dữ liệu
~~~

**Không có ánh xạ một–một bắt buộc** giữa các lớp:

- Một document DBMS có thể dùng B-tree cho chỉ mục.
- Một key–value engine có thể dùng LSM-tree, không nhất thiết dùng hash table.
- Một hệ có thể dùng hash table trong RAM để lập chỉ mục cho memtable nhưng ghi dữ liệu bền vững bằng log.
- Một LSM-tree có thể sử dụng Bloom filter, bảng băm, sparse index và cache ở các tầng khác nhau.
- Một DBMS có thể hỗ trợ nhiều storage engine hoặc phối hợp các cấu trúc.

Vì vậy, khi nghe “NoSQL thường dùng LSM-tree”, cần hiểu đây là **một lựa chọn phổ biến cho một số workload**, không phải định nghĩa của NoSQL.

## 2. Vì sao cấu trúc lưu trữ ảnh hưởng hiệu năng?

RAM và SSD/đĩa có đặc tính khác nhau. Trong bộ nhớ, truy cập một phần tử của mảng hoặc hash bucket có thể rất nhanh. Với dữ liệu bền vững, hệ thống còn phải đối mặt với:

- **Số thao tác I/O** để tìm một bản ghi.
- **Kích thước trang/block** phải đọc hoặc ghi.
- **Truy cập ngẫu nhiên hay tuần tự** trên thiết bị.
- **Cache hit/miss** trong RAM.
- **Chi phí đồng bộ dữ liệu đã ghi** để đáp ứng cam kết durability.
- **Công việc nền** như checkpoint, flush, compaction, garbage collection.
- **Tranh chấp** giữa các lần đọc và ghi đồng thời.

Ví dụ một truy vấn cần tìm đúng một key có thể chỉ trả vài trăm byte, nhưng engine phải đọc các trang metadata và dữ liệu lớn hơn nhiều. Ngược lại, nếu quét 10.000 key theo thứ tự, cấu trúc đã sắp xếp giúp đọc các block liên tiếp và giảm bước tìm kiếm.

### Ba kiểu truy cập để so sánh

| Access pattern | Ví dụ | Điều storage engine cần làm |
| --- | --- | --- |
| **Point lookup** | `GET order:O1007` | Định vị đúng key |
| **Range scan** | `createdAt` trong một ngày, có thứ tự | Tìm mốc đầu rồi đọc một dải khóa |
| **Update/insert liên tục** | Hàng chục nghìn sự kiện mỗi giây | Đưa thay đổi vào lưu trữ và giữ khả năng phục hồi |

Không có cấu trúc nào tối ưu tuyệt đối cả ba nhóm với mọi tỷ lệ tải. **Thay đổi cách ghi có thể làm tăng chi phí đọc hoặc công việc nền**, và ngược lại.

## 3. Hash table: ý tưởng cốt lõi

**Hash table** sử dụng một hàm băm `h(key)` để ánh xạ khóa vào một vị trí hoặc **bucket**:

~~~text
Key                  Hash function         Bucket
order:O1007 ─────────── h(key) ───────────> 5
order:O1008 ─────────── h(key) ───────────> 2
order:O1009 ─────────── h(key) ───────────> 5

Bucket 0: ...
Bucket 1: ...
Bucket 2: [O1008]
Bucket 3: ...
Bucket 4: ...
Bucket 5: [O1007, O1009]  ← collision
~~~

Một mô hình đơn giản trong bộ nhớ:

~~~text
index = hash table

put(key, value):
  bucket = hash(key)
  tìm key trong bucket
  nếu đã có thì cập nhật, ngược lại thêm mục mới

get(key):
  bucket = hash(key)
  tìm key trong bucket
  trả value hoặc NOT_FOUND
~~~

Nếu hàm băm phân phối hợp lý, độ đầy được kiểm soát và cách xử lý va chạm phù hợp, **point lookup có chi phí kỳ vọng gần O(1)** trong mô hình RAM.

Tuy nhiên, `O(1)` ở đây là một mô tả **kỳ vọng theo số phần tử**, không phải cam kết độ trễ cố định tính bằng mili giây. Cache miss, bucket dài, resize, phân phối khóa và I/O có thể tạo biến động.

### Va chạm băm

Hai khóa khác nhau có thể có cùng bucket:

~~~text
h("order:O1007") → 5
h("order:O1009") → 5
~~~

Hash table phải xử lý collision, thường bằng một trong những họ kỹ thuật:

1. **Separate chaining**: một bucket liên kết hoặc chứa nhiều entry.
2. **Open addressing**: khi vị trí bị chiếm, dò những ô khác theo quy tắc probing.
3. **Biến thể bucket hóa**: tổ chức các nhóm entry theo cấu trúc của engine.

Chỉ lưu hash code mà không kiểm tra khóa thật có thể gây nhầm hai khóa bị collision. Trong triển khai đúng, việc định danh entry vẫn phải dựa trên **khóa và quy tắc so sánh khóa**.

### Load factor và resize

Nếu hash table có quá ít bucket so với số entry, nhiều collision làm chậm lookup. Engine có thể tăng số bucket và **rehash** các key:

~~~text
Trước resize: 8 buckets, 7 entries
Sau resize:  16 buckets, phân phối lại entries
~~~

Resize giúp giữ thời gian truy cập kỳ vọng, nhưng tiêu tốn CPU, bộ nhớ tạm và có thể tạo độ trễ ở một số thời điểm. Các triển khai có thể làm resize từng phần để tránh dừng lâu.

## 4. Ưu điểm và hạn chế của hash table

### Phù hợp với truy vấn đúng khóa

Ví dụ:

~~~text
GET session:S123
GET cache:product:P1001
GET userId:U42
~~~

Khi ứng dụng đã biết key và không cần đi theo thứ tự, hash table là một lựa chọn dễ hiểu và thường hiệu quả.

### Không duy trì thứ tự tự nhiên của khóa

Một hash table không tổ chức các key theo thứ tự từ điển:

~~~text
event:0001
event:0002
event:0003
...
~~~

có thể nằm ở những bucket không liên tiếp. Vì thế câu hỏi:

> “Tìm mọi key từ `event:0100` đến `event:0200` theo thứ tự.”

không tự được hash table phục vụ tốt. Nếu chỉ có hash table thông thường, có thể phải **duyệt nhiều entry, lọc rồi sắp xếp**, hoặc xây một cấu trúc phụ có thứ tự.

### Khi hash table dùng trên đĩa

Hash table không chỉ tồn tại trong RAM. Các kỹ thuật như **extendible hashing** hoặc **linear hashing** tổ chức bucket trên thiết bị lưu trữ và có cơ chế mở rộng bucket.

~~~text
Hash(key)
   │
   ▼
Directory / bucket metadata
   │
   ▼
Disk bucket chứa key hoặc con trỏ tới record
~~~

Trong thiết kế trên đĩa, lookup còn phải tính số block I/O và khả năng directory/bucket nằm trong cache. Không thể lấy công thức `O(1)` của hash table trong RAM để kết luận truy vấn đĩa chắc chắn tốn đúng một I/O.

**Điểm quan trọng:** hash table là **cấu trúc truy cập theo khóa**, không phải cơ chế durability. Một hash table RAM đơn thuần sẽ mất dữ liệu khi process mất bộ nhớ nếu không có log, snapshot hoặc hệ lưu bền vững kèm theo.

## 5. B-tree: cây tìm kiếm cân bằng dành cho lưu trữ theo block

**B-tree** là họ cây tìm kiếm nhiều nhánh, cân bằng, được thiết kế để giảm số lần truy cập block/page khi dữ liệu lớn.

Trong cây tìm kiếm nhị phân, một node thường có ít con. B-tree cho phép một node chứa **nhiều khóa phân cách và nhiều con**, nhờ đó chiều cao cây có thể nhỏ ngay cả với lượng dữ liệu lớn.

Ví dụ trực giác:

~~~text
                       [M | T]
                     /    |    \
                 keys<M  M..T  keys>T
~~~

Một node thực tế có thể chứa hàng chục hoặc hàng trăm khóa tham chiếu tùy kích thước page và key; minh họa trên cố ý đơn giản.

### B-tree và B+tree khác nhau thế nào?

Trong nhiều storage engine, thuật ngữ “B-tree” được dùng khá rộng; nhưng **B+tree** là biến thể đặc biệt phổ biến trong chỉ mục database:

- **B-tree tổng quát**: một số thiết kế có thể lưu record/value ở node nội bộ cũng như node lá.
- **B+tree**: node nội bộ chủ yếu chứa khóa phân cách/con trỏ; dữ liệu hoặc tham chiếu record được tổ chức ở **node lá**; lá có thể được nối để duyệt tuần tự.

Sơ đồ B+tree:

~~~text
                    Root
                 [20 | 40]
                /    |     \
               ▼     ▼      ▼
          [5,10,15] [20,30] [40,50,60]
              │        │        │
              └────────┴────────┘
                 Chuỗi lá có thứ tự
~~~

Với một dải khóa, engine tìm điểm bắt đầu bằng cây rồi lần qua những trang lá theo thứ tự, không phải băm từng key độc lập.

### Độ phức tạp theo số trang

Nếu một node có fan-out hiệu dụng xấp xỉ `B`, chiều cao cây tăng gần theo:

\[
O(\log_B N)
\]

trong đó `N` là số mục được lập chỉ mục. Fan-out lớn giúp cây thấp và giảm số trang cần đi qua khi lookup.

Thực tế, latency còn phụ thuộc:

- Trang root và node nội bộ có được cache trong RAM không.
- Kích thước page và độ dài key.
- Độ đầy của các node.
- Số lần đọc/ghi và cơ chế đồng thời.
- Thiết bị lưu trữ, cơ chế cache của OS/DBMS.

Không nên suy luận một số I/O cố định chỉ từ ký hiệu `O(log_B N)`.

## 6. B+tree thực hiện point lookup và range scan

Giả sử các key `orderId` được sắp tăng:

~~~text
Leaf A: O1001 O1002 O1003
Leaf B: O1004 O1005 O1006
Leaf C: O1007 O1008 O1009
~~~

**Point lookup:**

~~~text
GET O1008
  → đi từ root qua các khóa phân cách
  → tới Leaf C
  → tìm O1008
~~~

**Range scan:**

~~~text
GET O1003..O1008
  → tìm Leaf A, vị trí O1003
  → duyệt tiếp Leaf B
  → duyệt Leaf C tới O1008
~~~

Range scan là điểm mạnh của cấu trúc **đã có thứ tự khóa**.

### B+tree hữu ích với sort và cursor

Một index ghép có khóa:

~~~text
(tenantId, customerId, createdAt, orderId)
~~~

có thể hỗ trợ một số truy vấn có điều kiện bằng trên `tenantId`, `customerId` và phạm vi `createdAt`, khi thứ tự index tương thích.

Việc index có hỗ trợ sort giảm dần hay một tổ hợp điều kiện cụ thể phụ thuộc DBMS và quy tắc index, không phải mọi B-tree đều tự đáp ứng mọi thứ tự tùy ý.

### Thao tác insert và page split

Khi thêm key:

~~~text
INSERT O1010
  → tìm trang lá phù hợp
  → thêm entry theo thứ tự
  → nếu trang còn chỗ: hoàn tất cập nhật logic
  → nếu trang đầy: chia trang (split)
  → cập nhật node cha, có thể lan lên root
~~~

**Page split** có thể làm thay đổi nhiều page/metadata, đặc biệt khi dữ liệu mới nằm xen kẽ trong miền khóa. Với ghi cập nhật ngẫu nhiên trên tập dữ liệu lớn, việc sửa nhiều page không gần nhau có thể làm tăng random I/O và write amplification.

Nhưng B-tree không đồng nghĩa “ghi chậm” trong mọi tình huống: hệ có buffer pool, WAL, group commit và cơ chế gom/điều phối page writes. Nếu working set nằm trong RAM, nhiều thao tác không cần đọc trang từ SSD mỗi lần.

## 7. Một B-tree được cập nhật bền vững như thế nào?

Xét một DBMS dùng B+tree và **write-ahead logging (WAL)**. Một giao dịch sửa `status` của đơn hàng có thể đi qua:

~~~text
UPDATE order O1007:
  status = PAID
         │
         ▼
Thay đổi trang/record trong buffer pool
         │
         ▼
Ghi bản mô tả thay đổi vào WAL theo giao thức
         │
         ▼
Đảm bảo WAL đạt mức durable theo cam kết commit
         │
         ▼
Trả kết quả commit
         │
         ▼
Dirty data pages được flush ra file dữ liệu sau đó
~~~

Thứ tự chi tiết giữa cập nhật RAM, tạo WAL record, flush log và trả commit phụ thuộc engine. **Nguyên tắc của WAL** là thông tin phục hồi cần thiết phải được lưu bền vững **trước khi các thay đổi tương ứng của data page được phép trở thành trạng thái chỉ còn phụ thuộc vào page**.

Nếu mất điện sau khi WAL durable nhưng trước khi dirty page được flush, engine có thể **replay/recover** thay đổi theo cơ chế của nó.

### B-tree không tự bảo đảm durability

Một cây B+tree được giữ hoàn toàn trong RAM không tự sống sót sau crash. Độ bền phụ thuộc:

- WAL hoặc cơ chế ghi copy-on-write/tương đương.
- Chính sách `fsync`/flush và hành vi thiết bị lưu trữ.
- Checkpoint.
- Phục hồi transaction chưa commit/đã commit.
- Kiểm tra tính toàn vẹn của page và metadata.

Không phải mọi engine B-tree đều dùng cùng một WAL format; một số dùng **copy-on-write pages**, journal hoặc cách khác để bảo vệ tính nguyên tử của cập nhật.

## 8. LSM-tree: giải quyết bài toán ghi bằng cấu trúc nhiều tầng

**LSM-tree** (*Log-Structured Merge-tree*) là họ thiết kế lưu trữ thường sử dụng:

1. **WAL/commit log** để hỗ trợ phục hồi các lần ghi đã nhận theo cam kết durability.
2. **Memtable** trong RAM, thường là cấu trúc khóa có thứ tự hoặc phù hợp cho ghi/đọc.
3. **SSTable** (*Sorted String Table*) hoặc các tệp bất biến chứa dữ liệu đã sắp xếp theo khóa.
4. **Compaction** để hợp nhất, sắp xếp lại và loại bỏ các phiên bản không còn cần thiết theo quy tắc.

Sơ đồ tổng quát:

~~~text
Client PUT/DELETE
       │
       ├──────────────> WAL / commit log
       │
       ▼
    Memtable (RAM)
       │ khi đạt ngưỡng
       ▼
 Flush thành SSTable bất biến
       │
       ▼
   Level 0: SSTable A, SSTable B, ...
       │
       ▼
   Compaction / merge
       │
       ▼
   Level 1 / Level 2 / ...
       │
       ▼
   SSD/đĩa
~~~

Ý tưởng cốt lõi: thay vì mỗi lần cập nhật phải sửa ngay một trang đĩa tại vị trí ngẫu nhiên, engine **ghi nhận cập nhật ở cấu trúc thuận tiện cho ghi, rồi gom thành các tệp sắp xếp bằng thao tác tuần tự**.

Tên “tree” có thể gây nhầm: LSM-tree **không phải một cây con trỏ giống B-tree**. Nó là một mô hình lưu trữ nhiều tầng/run đã sắp xếp với cơ chế merge.

## 9. Đường ghi của LSM-tree từng bước

Giả sử thao tác:

~~~text
PUT order:O1007 {"status":"PAID"}
~~~

Một engine LSM điển hình có thể:

1. Kiểm tra đầu vào, transaction/write batch theo API.
2. Ghi bản thay đổi vào **WAL**.
3. Cập nhật **memtable** với key và version mới.
4. Xác nhận ghi theo chính sách durability, ví dụ chờ WAL được sync khi cấu hình yêu cầu.
5. Khi memtable đủ lớn, chuyển thành immutable memtable và **flush** ra SSTable.
6. Sau này compaction các SSTable để hạn chế số tệp, xử lý bản ghi trùng phiên bản và tối ưu đọc.

~~~text
Thời điểm t0:
  WAL:      PUT order:O1007 = PAID
  Memtable: order:O1007 → PAID

Thời điểm t1:
  Memtable flush → SSTable-001
  WAL cũ có thể được giải phóng theo recovery checkpoint/metadata

Thời điểm t2:
  SSTable-001 được hợp nhất với SSTable khác
  → tạo SSTable mới
~~~

### Flush không giống compaction

**Flush:**

- Chuyển dữ liệu đang ở memtable ra một hoặc nhiều tệp dữ liệu trên đĩa.
- Thường giữ dữ liệu sắp xếp theo key.
- Tạo dữ liệu bền vững ở dạng SSTable theo cơ chế engine.

**Compaction:**

- Đọc nhiều SSTable/run.
- Hợp nhất theo thứ tự key và version.
- Ghi ra SSTable mới.
- Loại bỏ những phiên bản/tombstone đủ điều kiện khi an toàn.
- Cập nhật metadata để engine dùng cấu trúc mới.

Flush đưa dữ liệu từ RAM sang storage format; compaction **tổ chức lại dữ liệu đã được flush**. Đây là hai bước khác nhau, dù đều tạo I/O nền.

### Không đồng nhất “đã ghi vào memtable” với “đã durable”

Memtable ở RAM sẽ mất khi process chết nếu không có bản ghi phục hồi. WAL/commit log phải đạt ngưỡng bền vững theo **cam kết write acknowledgment** để engine có thể khôi phục ghi sau crash.

Một cấu hình có thể ưu tiên throughput bằng cách không sync mỗi lần ghi; khi đó kết quả đã báo cho client có thể có độ bền khác với chế độ sync chặt. Phải đọc **write acknowledgment và durability settings của DBMS thực tế**, không suy từ chữ LSM.

## 10. SSTable là gì và vì sao tệp bất biến hữu ích?

**SSTable** thường là tệp chứa các bản ghi được **sắp xếp theo key** và không sửa trực tiếp tại chỗ sau khi tạo.

Ví dụ:

~~~text
SSTable-001
  a:001 → value A
  a:004 → value D
  a:008 → value H

SSTable-002
  a:003 → value C
  a:004 → value D2 (phiên bản mới hơn)
  a:010 → value J
~~~

Thay vì tìm vị trí của `a:004` trong SSTable-001 rồi ghi đè, LSM có thể đưa phiên bản mới vào memtable và sau đó vào SSTable-002. Khi compaction, engine xác định bản ghi nào phải được giữ theo thứ tự/phiên bản.

### Tệp bất biến đem lại điều gì?

- Có thể tạo tệp mới bằng **ghi tuần tự**.
- Tránh sửa tại chỗ từng record trong SSTable cũ.
- Hợp nhất nhiều run đã sắp xếp bằng thuật toán merge.
- Dễ xây index block, Bloom filter và metadata cho tệp mới.
- Có thể dùng snapshot/reference đến tệp bất biến theo cơ chế engine.

Đổi lại, cùng một key có thể tồn tại ở **nhiều nơi và nhiều phiên bản** cho tới khi compaction, khiến đường đọc phức tạp hơn so với một cấu trúc lưu record theo một vị trí chính duy nhất.

## 11. Đường đọc của LSM-tree

Để đọc `a:004`, engine thường cần xét trạng thái mới nhất trước rồi tìm xuống các tầng:

~~~text
GET a:004
   │
   ▼
Memtable hiện tại?
   ├── Có → trả phiên bản phù hợp
   └── Không
        │
        ▼
Immutable memtables / cache?
        │
        ▼
SSTable level 0 (có thể nhiều tệp)
        │
        ▼
Các level sâu hơn theo metadata/index
        │
        ▼
Trả giá trị hoặc NOT_FOUND
~~~

Vì key có thể xuất hiện nhiều lần, engine phải biết **bản ghi nào mới hơn**. Những phiên bản cũ trong SSTable không được phép ghi đè logic của bản mới chỉ vì được tìm thấy sau.

### Bloom filter giúp tránh đọc tệp không chứa key

Nhiều LSM engine dùng **Bloom filter** để kiểm tra khả năng một SSTable chứa key:

~~~text
Bloom filter cho SSTable X:
  "key chắc chắn không có" → bỏ qua tệp X
  "key có thể có"         → cần kiểm tra tiếp
~~~

Bloom filter có thể có **false positive**: báo “có thể có” trong khi key không tồn tại. Với cấu hình và thuật toán đúng, nó **không có false negative** cho tập key mà filter đại diện: không được trả “chắc chắn không có” khi key thực sự thuộc tập đó.

Bloom filter **không trả value**, không thay thế kiểm tra khóa thực trong dữ liệu, cũng không sửa được mọi trường hợp quét theo khoảng.

### Block cache và index trong SSTable

Để giảm I/O, engine còn có thể dùng:

- **Block cache**: giữ những block dữ liệu hoặc index được truy cập thường xuyên.
- **Sparse index / index block**: định vị khoảng key trong một SSTable.
- **Min/max key metadata**: bỏ qua tệp không thể chứa key.
- **Compression**: giảm dung lượng lưu và I/O, đổi lại CPU giải nén.

Vì vậy, kết luận “LSM phải mở mọi SSTable cho mỗi lần GET” là sai. Đường đọc thực tế phụ thuộc cấu hình level, Bloom filter, cache, sự chồng lấn key-range và truy vấn.

## 12. Tombstone: xóa logic trước, dọn vật lý sau

Với cấu trúc tệp bất biến, khi client gọi:

~~~text
DELETE a:004
~~~

engine thường không thể xóa ngay mọi bản sao cũ của `a:004` đang nằm rải rác trong các SSTable. Nó ghi một **tombstone** hoặc marker xóa:

~~~text
Memtable mới:
  a:004 → TOMBSTONE

SSTable cũ:
  a:004 → value D
  a:004 → value D2
~~~

Khi đọc `a:004`, tombstone mới hơn phải **che** các giá trị cũ. Nếu compaction xóa tombstone **quá sớm**, một giá trị cũ ở tầng chưa được hợp nhất có thể xuất hiện trở lại.

### Vì sao không xóa tombstone ngay?

Để xóa marker an toàn, engine phải biết những bản ghi cũ mà marker cần che đã được xử lý, đồng thời xét:

- Phạm vi SSTable/level tham gia compaction.
- Snapshot hoặc read view đang cần thấy trạng thái cũ.
- Version/sequence của bản ghi.
- Với cơ sở dữ liệu phân tán, cơ chế replica, repair và chính sách tombstone cụ thể.

Trong Cassandra, tombstone và điều kiện dọn liên quan cả đến replication/repair và chính sách như `gc_grace_seconds`; không nên tùy ý giảm thời gian dọn để giải phóng đĩa khi chưa hiểu khả năng bản ghi đã xóa xuất hiện lại từ replica cũ.

**Hết hạn TTL cũng có thể tạo trạng thái giống xóa logic**. Bản ghi được coi là hết hạn không nhất thiết giải phóng toàn bộ byte trên đĩa ngay tại deadline; việc thu hồi vật lý có thể cần compaction.

### Tombstone khác câu lệnh xóa hoàn tất về mặt nghiệp vụ

Nếu API trả rằng `DELETE` đã thành công, nghĩa logic thường là dữ liệu không còn xuất hiện theo đường đọc phù hợp. Nó **không tự chứng minh** mọi byte từng chứa dữ liệu đã bị xóa khỏi SSD, replica, backup, snapshot, search index hay log.

Với yêu cầu retention/bảo mật, cần thiết kế vòng đời dữ liệu trên **tất cả bản sao và tầng lưu trữ**, không thể chỉ nhìn vào tombstone.

## 13. Compaction: đánh đổi giữa tốc độ ghi và chi phí nền

LSM có lợi thế nhận ghi nhanh vì không phải sửa các record cũ trực tiếp. Nhưng các run chồng lấn và phiên bản cũ sẽ tích lũy. **Compaction** là bước bảo trì bắt buộc trong nhiều thiết kế để giữ đọc và dung lượng ở mức chấp nhận được.

Minh họa:

~~~text
SSTable A:  a:001  a:004(v1)  a:008
SSTable B:  a:003  a:004(v2)  a:010
SSTable C:  a:004(TOMBSTONE) a:012
                 │
                 ▼
            Merge/compaction
                 │
                 ▼
SSTable mới:
  a:001 a:003 a:008 a:010 a:012
  (a:004 có thể bị loại nếu đủ điều kiện an toàn)
~~~

Nếu chưa đủ điều kiện dọn tombstone hoặc phiên bản cũ do snapshot/replication, kết quả compaction **phải giữ metadata cần thiết**, không đơn giản xóa tất cả entry trùng key.

### Hai họ chiến lược compaction thường gặp

**Size-tiered compaction:**

- Gom các tệp/run có kích thước phù hợp rồi hợp nhất.
- Có thể giảm số lần một số dữ liệu bị viết lại so với những cấu hình leveled.
- Các tệp có miền khóa chồng lấn, nên point lookup có thể cần xem nhiều run hơn.
- Một đợt compaction lớn có thể cần dung lượng tạm và I/O đáng kể.

**Leveled compaction:**

- Tổ chức dữ liệu theo nhiều level với quy tắc kích thước và mức chồng lấn.
- Các level sâu hơn trong nhiều thiết kế duy trì phạm vi key ít chồng lấn trong cùng level.
- Có thể giảm read amplification cho point/range lookup.
- Dữ liệu có thể bị viết lại nhiều lần khi chuyển qua level, tăng write amplification.

Đó là **xu hướng đánh đổi**, không phải định luật “leveled luôn tốt hơn cho mọi đọc” hoặc “size-tiered luôn tốt hơn cho mọi ghi”. Engine còn có biến thể universal/tiered, time-window, hybrid và tuning riêng.

### Compaction debt và backpressure

Nếu ứng dụng ghi nhanh hơn tốc độ flush/compaction có thể theo kịp:

~~~text
Incoming writes tăng
         │
         ▼
Memtable flush tạo nhiều SSTable
         │
         ▼
Compaction không theo kịp
         │
         ▼
Tệp chồng lấn và pending bytes tăng
         │
         ▼
Read latency tăng / disk usage tăng
         │
         ▼
Engine có thể stall hoặc throttle writes
~~~

Một hệ có throughput ghi cao trong bài benchmark 30 giây chưa chắc duy trì được tốc độ đó hàng giờ nếu compaction debt liên tục tăng.

## 14. Ba loại amplification quan trọng

Khi so sánh storage engine, chỉ nhìn số request/giây có thể che giấu chi phí nền. Ba khái niệm thường dùng:

### 14.1. Write amplification

**Write amplification** là tỷ lệ giữa tổng lượng dữ liệu ghi xuống tầng thiết bị (bao gồm log, metadata, compaction hoặc rewrite) và lượng dữ liệu logic ứng dụng muốn ghi, với cách đo được xác định rõ.

\[
\text{WA}\approx
\frac{\text{bytes physically written}}{\text{bytes logically written}}
\]

Ví dụ:

~~~text
Ứng dụng cập nhật 1 GiB dữ liệu logic.
Tổng device writes gồm WAL, SSTable flush, compaction = 8 GiB.
WA theo cách đo trên = 8 lần.
~~~

Đây là ví dụ số học, **không phải WA mặc định của LSM hoặc B-tree**.

B-tree có thể ghi lại page lớn dù chỉ đổi vài byte; LSM có thể ghi dữ liệu nhiều lần trong compaction. Loại nào tốt hơn phụ thuộc block size, cache, loại ghi, mức phân mảnh, compaction strategy, size của value, WAL và cấu hình.

### 14.2. Read amplification

**Read amplification** mô tả việc engine phải đọc/xét nhiều dữ liệu hoặc truy cập nhiều cấu trúc hơn so với dữ liệu logic cần trả.

Ví dụ một truy vấn chỉ muốn một value:

~~~text
Logic result: 1 record
Engine: kiểm tra memtable, 3 filter/index blocks, 2 SSTable blocks
~~~

Read amplification có thể biểu diễn theo **số I/O**, **số byte**, **số tệp**, hoặc **số key được xét**, tùy ngữ cảnh. Vì thế không nên so sánh hai biểu đồ RA nếu định nghĩa đo khác nhau.

LSM có thể trả giá từ nhiều level/run; B-tree có thể phải đọc đường đi root → leaf. **Cache hit**, Bloom filter và index coverage ảnh hưởng lớn tới RA.

### 14.3. Space amplification

**Space amplification** phản ánh mức dung lượng lưu trữ thực tế vượt dữ liệu logic còn sống do:

- Phiên bản cũ.
- Tombstone.
- Tệp tạm trong compaction.
- Page trống/phân mảnh.
- Index, metadata.
- WAL và các bản sao nội bộ, tùy định nghĩa.

\[
\text{SA}\approx
\frac{\text{physical bytes used}}{\text{live logical data bytes}}
\]

Đây chỉ là công thức minh họa; cần xác định có tính replica, backup, compression và index riêng hay không.

### Bảng đánh đổi trực giác

| Cấu trúc | Đường đọc chính | Đường ghi chính | Chi phí nổi bật |
| --- | --- | --- | --- |
| **Hash table** | Định vị bucket theo hash | Sửa/thêm entry, có thể resize | Collision, memory overhead, thiếu thứ tự |
| **B/B+tree** | Đi theo cây, lá sắp xếp | Sửa page, split/merge, WAL hoặc cơ chế durability khác | Random page writes, contention, fragmentation |
| **LSM-tree** | Memtable, filter/index, nhiều SSTable/level | WAL + memtable + flush tuần tự | Compaction, phiên bản cũ, read/write/space amplification |

**Không thể chấm cấu trúc bằng một con số WA/RA/SA duy nhất.** Cần so với workload và SLO cụ thể.

## 15. So sánh độ phức tạp: đừng suy luận quá đơn giản

Trong giáo trình thuật toán, ta hay thấy:

~~~text
Hash lookup: O(1) trung bình
B-tree lookup: O(log_B N) theo block
LSM write: amortized efficient
~~~

Những mô tả đó có ích để hiểu thiết kế, nhưng chưa phải bảng dự đoán latency.

### Hash table

- Point lookup trung bình thường tốt khi hash phân bố đều.
- Kết quả xấu có thể xảy ra khi collision nhiều, rehash hoặc memory pressure.
- Range query thiếu cấu trúc có thứ tự.

### B-tree/B+tree

- Lookup, insert, delete thường theo chiều cao cây trong phân tích thuật toán.
- Quét khoảng thuận lợi vì key có thứ tự.
- Page split, cache miss và WAL sync ảnh hưởng thời gian thực.

### LSM-tree

- Ghi vào memtable và WAL thường thuận lợi cho tốc độ nhận ghi, nhưng phải tính **compaction amortized** và khả năng write stall.
- Point lookup có thể tìm qua nhiều cấu trúc, được giảm nhờ Bloom filter, index và cache.
- Range scan có thể phải **merge** kết quả từ nhiều sorted runs; không thể đọc đơn giản một chuỗi lá duy nhất như B+tree.

Nếu hai hệ đều quảng cáo `O(log N)`, không có nghĩa chúng đạt cùng p99 hoặc dùng cùng số byte ghi. Với storage engine, **hành vi dưới tải kéo dài** và **khuếch đại I/O** thường quan trọng hơn ký hiệu Big-O đơn lẻ.

## 16. Range scan: B+tree và LSM đều có thứ tự, nhưng khác chi phí

Giả sử cần:

~~~text
GET all events where key in [device:D7#2026-11-01,
                             device:D7#2026-11-14]
ORDER BY key ASC
~~~

**B+tree:**

~~~text
Find lower bound
     │
     ▼
Đọc liên tiếp các leaf pages đúng khoảng
     │
     ▼
Trả theo thứ tự
~~~

**LSM:**

~~~text
Tìm khoảng trong memtable và nhiều SSTables liên quan
     │
     ▼
Đọc các sorted runs
     │
     ▼
Merge iterator theo key/version
     │
     ▼
Ẩn giá trị cũ/tombstone, trả theo thứ tự
~~~

LSM vẫn hỗ trợ range scan vì dữ liệu trong memtable/SSTable có thứ tự. Nhưng nó có thể tốn công **merge nhiều iterator** nếu cùng một key-range xuất hiện trong nhiều run.

Nếu workload chủ yếu đọc khoảng dài, cần đo kích thước scan, mức chồng lấn file và compaction strategy. Không nên mặc định mọi LSM chỉ phù hợp point lookup hoặc không làm được truy vấn theo khoảng.

## 17. Bền vững dữ liệu là một cam kết về thời điểm ghi

**Durability** thường được hiểu là dữ liệu mà hệ thống đã xác nhận commit sẽ còn tồn tại qua những loại lỗi được cam kết chịu đựng.

Nhưng cần xác định rõ:

- **Lỗi process**: chương trình DBMS bị crash.
- **Lỗi OS/máy**: hệ điều hành khởi động lại.
- **Mất điện**: các buffer của OS/thiết bị có thể chưa được ghi bền vững.
- **Lỗi ổ đĩa**: thiết bị lưu trữ hỏng hoặc dữ liệu bị lỗi.
- **Lỗi node**: một máy trong cluster mất hoàn toàn.
- **Lỗi vùng triển khai**: mất nhiều node hoặc trung tâm dữ liệu.

Một WAL được sync giúp ứng phó một số lỗi, nhưng **không thay thế replica/backup** khi ổ đĩa hỏng vật lý. Replication cũng không tự thay thế backup: xóa nhầm hay ghi sai có thể được sao chép sang mọi replica.

### Câu hỏi quan trọng: ACK sau bước nào?

~~~text
Client PUT
    │
    ▼
Server nhận request
    │
    ▼
Ghi vào RAM
    │
    ▼
Append WAL trong bộ nhớ/OS buffer
    │
    ▼
WAL được sync theo cơ chế bền vững
    │
    ▼
Replica khác xác nhận theo consistency setting (nếu yêu cầu)
    │
    ▼
ACK gửi client
~~~

Đây là **một danh sách các mốc có thể có**, không phải trình tự bắt buộc của mọi hệ. Một số cấu hình ACK sớm hơn, một số yêu cầu WAL bền vững hoặc đa replica trước khi ACK.

**Durability không thể suy ra chỉ từ cấu trúc B-tree/LSM/hash.** Phải biết rõ **write concern**, sync policy và failover guarantees của DBMS đang vận hành.

## 18. WAL, fsync và checkpoint

### WAL — Write-Ahead Log

WAL là một nhật ký phục hồi được ghi trước các thay đổi dữ liệu theo giao thức phù hợp. Tùy engine, log có thể mô tả:

- Operation logic.
- Thay đổi page.
- Transaction/sequence.
- Commit/abort metadata.

Sau crash, engine dùng log để **redo**, **undo** hoặc khôi phục trạng thái nhất quán theo thuật toán của nó.

### `fsync`/sync và page cache

Một lệnh ghi thành công ở tầng ứng dụng có thể chỉ được hệ điều hành nhận vào page cache. Để đáp ứng một mức durability mạnh hơn, DBMS thường cần gọi cơ chế đồng bộ phù hợp để yêu cầu hệ thống lưu trữ đẩy dữ liệu cần thiết xuống thiết bị.

Tuy nhiên, `fsync` không phải phép màu:

- Bộ điều khiển lưu trữ và thiết bị phải thực hiện đúng cam kết flush/barrier.
- Engine phải ghi đúng thứ tự WAL/metadata.
- Bản ghi có thể cần checksum và cơ chế phát hiện corruption.
- Thiết bị hỏng hoàn toàn vẫn có thể làm mất bản sao đơn lẻ.

### Checkpoint

**Checkpoint** ghi nhận một mốc trạng thái đã đủ an toàn để giới hạn công việc recovery. Với engine B-tree có WAL, dirty pages có thể được flush dần và checkpoint đánh dấu tiến độ. Với LSM, trạng thái memtable đã flush, WAL segments và manifest/SSTable metadata là những thành phần quan trọng.

Không phải “checkpoint” luôn là một bản sao đầy đủ của toàn database tại cùng một thời điểm. Nó là một phần của **giao thức phục hồi** theo engine.

## 19. Ví dụ crash recovery với B-tree

Giả sử một storage engine dùng buffer pool, B+tree và WAL.

~~~text
T0: Data page trên đĩa có balance=1000
T1: Transaction trừ 200
T2: WAL ghi thông tin đủ để phục hồi
T3: WAL durable; transaction commit được ACK
T4: Data page trong buffer pool có balance=800
T5: Crash trước khi page mới được flush
~~~

Sau khởi động:

~~~text
Disk data page cũ: balance=1000
WAL: có transaction đã commit trừ 200
Recovery:
  đưa dữ liệu về trạng thái balance=800
  theo quy tắc replay/redo của engine
~~~

Nếu crash xảy ra **trước khi transaction được commit theo cam kết**, engine phải bảo đảm những thay đổi chưa commit không xuất hiện như giao dịch đã hoàn thành, thông qua rollback/undo/redo hoặc giao thức phù hợp.

**Ví dụ chỉ minh họa cơ chế khái niệm.** Thuật toán recovery thật còn phải xử lý page LSN, partial page write, checksum, idempotent redo, transaction ordering và nhiều trường hợp khác.

## 20. Ví dụ crash recovery với LSM-tree

Giả sử:

~~~text
T0: SSTable cũ có order:O1007 status=NEW
T1: PUT order:O1007 status=PAID
T2: WAL đã durable theo chính sách ghi
T3: Memtable chứa status=PAID
T4: ACK success
T5: Crash trước khi memtable flush
~~~

Khi khởi động:

~~~text
SSTable cũ vẫn có status=NEW
WAL có PUT status=PAID đã commit
Recovery replay vào memtable hoặc trạng thái tương ứng
GET order:O1007 → status=PAID
~~~

Điều quan trọng là **WAL hoặc một cơ chế bền vững tương đương** đã lưu thay đổi trước khi memtable mất. Nếu WAL chỉ nằm trong buffer và engine ACK trước mốc sync cần thiết, crash/mất điện có thể gây mất những ghi đã ACK theo cấu hình yếu hơn.

### Flush và WAL cleanup phải được phối hợp

Một engine không được xóa WAL cần thiết **trước khi** trạng thái tương ứng đã có cách phục hồi bền vững, ví dụ các SSTable/manifest đã commit đúng.

Tình huống nguy hiểm:

~~~text
WAL bị xóa quá sớm
  +
Memtable chưa flush an toàn
  +
Crash
  =
Không còn bản ghi đáng tin để phục hồi dữ liệu mới
~~~

Engine trưởng thành thiết kế giao thức metadata, manifest và thứ tự flush để tránh trường hợp này. Người dùng không nên tự xóa file WAL/SSTable chỉ để giải phóng dung lượng.

## 21. Compaction có ảnh hưởng đến durability không?

Có. Dù compaction là tác vụ tối ưu lưu trữ, nó **không được làm mất dữ liệu còn hợp lệ**.

Một compaction an toàn về mặt ý tưởng:

~~~text
SSTables cũ A, B
        │
        ▼
Đọc và merge → tạo SSTable mới C
        │
        ▼
Ghi bền vững dữ liệu/metadata mới theo giao thức
        │
        ▼
Cập nhật manifest/version set atomically
        │
        ▼
Chỉ sau khi an toàn, có thể xóa A, B không còn dùng
~~~

Nếu crash giữa lúc tạo C, engine phải có cách dùng lại A/B hoặc hoàn tất recovery mà không coi một tệp ghi dở là dữ liệu hợp lệ.

**Manifest** là metadata mô tả những tệp/tầng nào đang tạo nên phiên bản trạng thái lưu trữ được công nhận, theo cơ chế LSM engine. Nó quan trọng vì **SSTable bất biến chỉ có ích nếu engine biết bản nào đang hợp lệ**.

Ngoài crash, compaction còn phải giữ đúng ngữ nghĩa của:

- Nhiều phiên bản cùng key.
- Tombstone.
- Snapshot/transaction đọc trạng thái cũ.
- TTL.
- Dữ liệu chưa được nhân bản/repair an toàn trong môi trường phân tán.

Không phải cứ “giữ bản mới nhất” là luôn đúng cho mọi engine có MVCC hoặc snapshot.

## 22. Atomicity, isolation và durability là những câu hỏi khác nhau

Một DBMS có thể giữ dữ liệu qua crash nhưng vẫn có lỗi **lost update** nếu ứng dụng dùng sai giao thức đồng thời.

Ví dụ:

~~~text
balance = 1000
Client A đọc 1000, muốn trừ 700
Client B đọc 1000, muốn trừ 700

A ghi 300
B ghi 300
~~~

Nếu cả hai báo thành công, bất biến nghiệp vụ đã sai dù hai lần ghi `300` có thể đều được WAL lưu bền vững.

Phân biệt:

| Thuộc tính | Câu hỏi |
| --- | --- |
| **Atomicity** | Một thao tác/transaction có bị nhìn thấy một phần hay không? |
| **Consistency theo invariant nghiệp vụ** | Trạng thái sau thao tác có giữ điều kiện được yêu cầu không? |
| **Isolation/concurrency control** | Các thao tác đồng thời có thể ảnh hưởng nhau thế nào? |
| **Durability** | Ghi đã commit có sống sót qua lỗi trong phạm vi bảo đảm không? |
| **Replication consistency** | Các bản sao nhìn thấy thay đổi theo thứ tự và mức cam kết nào? |

Hash table, B-tree hay LSM-tree **không tự mang toàn bộ bộ tính chất này**. Engine và transaction layer phải phối hợp với ứng dụng để đạt đúng yêu cầu.

## 23. Cùng một dữ liệu, ba phương án thiết kế

Giả sử kho key–value lưu:

~~~text
Key: product:P1001
Value: {"title":"Sổ tay","priceMinor":89000,"stock":42}
~~~

### Phương án A — Hash table trong RAM + log/snapshot

~~~text
RAM:
  hash(product:P1001) → value hoặc offset

Persistence:
  AOF / append log hoặc snapshot theo chính sách
~~~

Đọc đúng key thường nhanh nếu dữ liệu/index đã có trong RAM. Nhưng range scan theo key không tự nhiên, và durability phụ thuộc cách log/snapshot được ghi.

**Ví dụ liên hệ:** Redis sử dụng nhiều cấu trúc dữ liệu trong RAM; việc dữ liệu có sống qua restart phụ thuộc cơ chế persistence như RDB snapshot hoặc AOF và cấu hình. Lệnh Redis `HGET` trên một hash **không có nghĩa toàn bộ Redis storage engine là “disk hash table”**.

### Phương án B — B+tree trên đĩa với buffer pool

~~~text
Root/internal pages
     │
     ▼
Leaf page chứa product:P1001
     │
     ▼
Value hoặc record reference
~~~

Đọc đúng key đi theo cây; range scan có thể duyệt lá theo thứ tự. Ghi update có thể làm dirty page và cần WAL/copy-on-write/đường durable phù hợp.

**Ví dụ liên hệ:** MongoDB với WiredTiger sử dụng cấu trúc B-tree ở nhiều đường lưu trữ/chỉ mục. Tuy nhiên, cần phân biệt **cấu trúc bên trong engine** với cú pháp document query của MongoDB.

### Phương án C — LSM-tree

~~~text
PUT product:P1001 → WAL + memtable
                  → flush SSTable
                  → compaction levels
~~~

Ghi nhiều cập nhật có thể thuận lợi do gom thao tác, nhưng công việc compaction và việc tìm bản mới nhất qua nhiều cấu trúc là đánh đổi.

**Ví dụ liên hệ:** LevelDB/RocksDB là các storage engine key–value nổi tiếng theo thiết kế LSM. Cassandra/HBase và các hệ wide-column liên quan dùng nhiều ý tưởng về commit log, memtable và tệp bất biến được hợp nhất trong nền, dù chi tiết hoàn toàn không đồng nhất.

## 24. Nên chọn cấu trúc nào theo workload?

### Workload A — Session hoặc cache truy cập bằng key

~~~text
GET session:S123
SET session:S123
EXPIRE session:S123
~~~

Nếu dữ liệu vừa bộ nhớ và chủ yếu dùng point lookup, hash-based in-memory access có thể hiệu quả. Nhưng nếu session phải không mất sớm, không được coi cache eviction và persistence là vấn đề phụ. Cần tách **cache có thể tái tạo** khỏi **state cần cam kết bền vững**.

### Workload B — Đơn hàng truy vấn theo khoảng thời gian

~~~text
Find orders for customer C42
createdAt in [start, end)
ORDER BY createdAt DESC
~~~

Một B+tree index ghép hoặc một LSM-based sorted-key layout có thể phục vụ đọc theo khoảng. Quyết định phụ thuộc tỷ lệ read/write, số lần cập nhật, kích thước kết quả và query semantics; hash table thuần túy theo `orderId` không đủ cho pattern này.

### Workload C — Dòng sự kiện cảm biến ghi liên tục

~~~text
Device D7 sends 2000 events/second
Query recent events by device and time
Retention = 30 days
~~~

LSM-like storage thường đáng đánh giá khi ghi lớn, có thể chia bucket theo thiết bị/thời gian và chấp nhận compaction/TTL. Tuy vậy, phải đo:

- Write throughput bền vững sau nhiều giờ.
- Compaction backlog.
- Tombstone/TTL overhead.
- Hot partition theo device.
- Range scan p95/p99.
- Dung lượng và quy tắc dọn dữ liệu.

### Workload D — Truy vấn phân tích quét hàng tỷ bản ghi

Không nên mặc định chỉ chọn trong ba cấu trúc. Với thống kê nhiều chiều và đọc theo cột, **columnar storage, analytical engine hoặc materialized aggregates** có thể phù hợp hơn việc quét một key–value store giao dịch.

**Kết luận:** lựa chọn storage engine là một phần của thiết kế tổng thể, không thay thế thiết kế partition key, index, transaction hoặc hệ phân tích chuyên dụng.

## 25. Khi key tăng theo thời gian, cấu trúc có ảnh hưởng gì?

Khóa có thứ tự thường giúp range scan, nhưng có thể tạo **vùng ghi nóng** hoặc page/level tập trung tùy engine.

Ví dụ khóa:

~~~text
event:D7:2026-11-14T09:00:00Z
event:D7:2026-11-14T09:00:01Z
event:D7:2026-11-14T09:00:02Z
~~~

Với B+tree, key tăng dần có thể tập trung ghi vào vùng lá cuối của một dải. Với LSM, key tăng dần có thể thuận lợi cho flush tuần tự nhưng vẫn tạo tải trên partition/shard sở hữu dải key đó. Với hash partitioning, các key có thể phân bố rộng hơn nhưng việc range scan theo thời gian có thể khó hơn.

Đừng chỉ hỏi “hash hay tree”; phải xét:

- **Partition/sharding** nằm trên tầng nào?
- Key có được sắp xếp trong từng partition không?
- Một partition có bị một thiết bị/tenant nóng áp đảo không?
- Muốn đọc một khoảng thời gian có cần fan-out qua nhiều shard không?

Một B-tree hoàn hảo trên mỗi shard vẫn không tự sửa được **đường định tuyến shard không phù hợp với query**.

## 26. Kích thước value và việc tách dữ liệu lớn

Đối với các value lớn như hình ảnh, payload tài liệu hoặc blob:

~~~text
Key: product:P1001
Value: metadata vài KiB + ảnh 15 MiB
~~~

Nếu mọi lần sửa `priceMinor` buộc engine phải ghi lại ảnh lớn, chi phí có thể rất cao.

Các storage engine có những chiến lược khác nhau:

- Lưu value inline trong page/block.
- Lưu con trỏ/reference tới value ở vùng khác.
- Tách blob ra object storage và giữ metadata/URI trong DB.
- Dùng **key–value separation** hoặc log-structured value storage trong một số thiết kế.

Không phải mọi LSM đều luôn ghi lại toàn bộ blob trong mỗi compaction, và không phải mọi B-tree đều luôn đặt toàn bộ value trong leaf page. Phải xem **record layout và giá trị có được tách riêng hay không**.

### Thiết kế dữ liệu theo access pattern

Nếu màn hình danh sách chỉ cần 5 trường, lưu một document có blob rất lớn có thể khiến fetch/projection có chi phí khác nhau theo engine và index. Ngoài chọn cấu trúc, có thể cần:

- Projection chỉ lấy field cần.
- Covering index hoặc read model tóm tắt.
- Tách metadata và payload.
- Dùng object storage cho dữ liệu nhị phân lớn.

Đây là ví dụ cho thấy **mô hình dữ liệu, chỉ mục và storage engine phải được đánh giá cùng nhau**.

## 27. Lưu trữ phân tán làm bài toán phức tạp hơn

Hash table, B-tree và LSM thường được mô tả trên một node, nhưng nhiều NoSQL DBMS phân phối dữ liệu qua nhiều node:

~~~text
Client
  │
  ▼
Coordinator / Router
  ├── Node A: local storage engine
  ├── Node B: local storage engine
  └── Node C: local storage engine
~~~

Mỗi node có thể dùng LSM hoặc B-tree, nhưng request vẫn phải biết:

- Khóa được định tuyến tới node/replica nào.
- Ghi cần bao nhiêu replica ACK.
- Đọc có thể thấy dữ liệu cũ từ replica nào.
- Node lỗi thì failover/repair thế nào.
- Các bản sao xung đột được giải quyết ra sao.

### Hashing ở tầng sharding khác hash table nội bộ

Một cơ sở dữ liệu có thể dùng **consistent hashing** hoặc hash partitioning để chọn node:

~~~text
hash(partitionKey) → token → replica set
~~~

trong khi **mỗi node** lưu dữ liệu bằng LSM-tree.

Đó là hai vai trò khác nhau:

| Hash ở tầng phân tán | Hash table storage/index |
| --- | --- |
| Chọn partition/node sở hữu key | Tìm entry trong cấu trúc nội bộ |
| Quan tâm cân bằng phân phối và routing | Quan tâm collision, bucket, load factor |
| Không quyết định engine trên mỗi node | Không tự quyết định placement giữa các node |

Đừng nói “Cassandra dùng hashing nên storage engine là hash table”. Hệ có thể dùng hashing để phân phối key nhưng memtable/SSTable để lưu dữ liệu trong mỗi node.

## 28. Một ví dụ thực hành: theo dõi một key qua ba cấu trúc

Ta có các thao tác:

~~~text
PUT   k:7 = "A"
PUT   k:9 = "B"
PUT   k:7 = "C"
GET   k:7
DELETE k:7
GET   k:7
~~~

Kết quả logic mong đợi:

~~~text
Sau PUT k:7="C":  GET k:7 → "C"
Sau DELETE k:7:   GET k:7 → NOT_FOUND
GET k:9 → "B"
~~~

### Với hash table có persistence phù hợp

~~~text
hash(k:7) → bucket
PUT A → entry k:7=A
PUT C → thay entry thành C
DELETE → xóa/đánh dấu entry
~~~

Muốn sống qua crash, engine còn cần log/snapshot hoặc ghi bền vững theo giao thức riêng.

### Với B+tree

~~~text
Tìm leaf chứa k:7
PUT A → thêm record
PUT C → sửa record/phiên bản theo cơ chế engine
DELETE → xóa logic/vật lý theo giao thức
~~~

Các bước có thể làm dirty page, page split/merge và yêu cầu WAL/transaction metadata. Với snapshot/MVCC, các version cũ có thể được giữ lại một thời gian.

### Với LSM-tree

~~~text
WAL/memtable:
  k:7 → "A"
  k:9 → "B"
  k:7 → "C"  (bản mới hơn thắng)
  k:7 → TOMBSTONE

SSTables qua các đợt flush:
  có thể còn "A", "B", "C", TOMBSTONE

GET k:7:
  thấy tombstone mới nhất → NOT_FOUND

Compaction:
  loại version/tombstone cũ khi đủ điều kiện an toàn
~~~

LSM thể hiện rõ **sự khác biệt giữa trạng thái logic mới nhất** và **nhiều bản ghi vật lý còn tồn tại cho tới compaction**.

## 29. Một phép thử về dữ liệu được ACK và phục hồi

Giả sử ứng dụng ghi `k:7 = "C"` và nhận phản hồi thành công. Sau đó mất điện trước lúc storage engine hoàn thành mọi công việc nền.

Kết quả **không thể xác định chỉ từ tên cấu trúc**:

| Cấu trúc | Nếu chỉ dữ liệu RAM đã thay đổi | Nếu cơ chế durability đã cam kết/ghi bền vững đúng |
| --- | --- | --- |
| Hash table RAM | Có thể mất trạng thái mới | Có thể phục hồi từ log/snapshot phù hợp |
| B-tree với buffer pool | Dirty page chưa flush có thể mất khỏi RAM | WAL/copy-on-write có thể khôi phục commit |
| LSM-tree với memtable | Memtable mất khi crash | WAL/commit log và metadata an toàn cho phép replay |

Ngay cả khi WAL đã tồn tại trên thiết bị, câu hỏi “có thể mất dữ liệu không?” còn phụ thuộc:

- WAL có bao gồm commit record hoặc thông tin cần thiết không?
- Đã sync theo chính sách nào?
- Đã ACK khi bao nhiêu replica durable?
- Thiết bị lưu trữ có hỏng không?
- Hệ có checkpoint/manifest nhất quán không?

**Không dùng “ghi nhanh” làm từ đồng nghĩa với “ghi bền vững”.** Có thể một engine ghi rất nhanh bằng cách hoãn sync, nhưng đó là một đánh đổi durability cần được nói rõ.

## 30. Các sản phẩm tiêu biểu và điều cần tránh khi gán nhãn

| Sản phẩm/họ | Liên hệ với cấu trúc | Lưu ý |
| --- | --- | --- |
| **Redis** | Nhiều kiểu dữ liệu và bảng tra cứu trong RAM; có thể dùng hash-based indexing bên trong | Durability phụ thuộc RDB/AOF và cấu hình; Redis hash data type không phải toàn bộ storage engine |
| **LevelDB** | Key–value engine dựa trên LSM | WAL, memtable, sorted files và compaction |
| **RocksDB** | LSM-based key–value engine với nhiều tùy chọn compaction/cache | Chi phí tùy tuning, hardware, workload |
| **Apache Cassandra** | Commit log, memtable, SSTable và compaction theo hướng LSM | Phân tán theo token/partition, replication và tombstone có quy tắc riêng |
| **Apache HBase** | Kiến trúc lưu trữ dạng memstore/HFiles/compaction theo họ LSM | Tổ chức region và phân phối dữ liệu ảnh hưởng routing |
| **MongoDB + WiredTiger** | Dùng cấu trúc B-tree trong storage/index ở nhiều đường | Document API, journaling, checkpoint và replication là các lớp bổ sung |
| **Một RDBMS có B-tree indexes** | B-tree/B+tree phổ biến cho chỉ mục | Không phải NoSQL, nhưng cùng khái niệm storage engine |

Đây là các **ví dụ giúp liên hệ khái niệm**, không phải bảng xác nhận mọi phiên bản sản phẩm đều có đúng một engine hoặc cùng cơ chế. Một số DBMS hỗ trợ các engine/định dạng khác nhau và thay đổi qua phiên bản.

### Câu hỏi nên hỏi khi xem một DBMS cụ thể

1. Cấu trúc primary storage và secondary index là gì?
2. Đường đọc point/range dùng cấu trúc nào?
3. Ghi trả ACK khi WAL/replica ở trạng thái nào?
4. Memtable/buffer pool/cache chiếm bao nhiêu RAM?
5. Flush/checkpoint/compaction có thể gây stall không?
6. TTL/delete có cần tombstone và dọn vật lý không?
7. Có giới hạn value size và record layout không?
8. Có thể đo read/write/space amplification bằng metric nào?

Các câu hỏi này có giá trị hơn việc hỏi đơn giản “engine này là B-tree hay LSM?”.

## 31. So sánh trong một bảng tổng hợp

| Tiêu chí | Hash table | B-tree/B+tree | LSM-tree |
| --- | --- | --- | --- |
| Cách định vị | Hàm băm → bucket/entry | Tìm trên cây cân bằng | Memtable + sorted runs/levels |
| Khóa có thứ tự tự nhiên | Thường không | Có | Có trong các run |
| Point lookup | Thường rất tốt khi hash/cache phù hợp | Tốt với index và buffer pool | Tốt khi filter/index/cache được tuning |
| Range scan | Không phải thế mạnh nếu không có cấu trúc phụ | Thế mạnh tự nhiên | Hỗ trợ, thường cần merge nhiều run |
| Ghi cập nhật | Sửa/thêm entry; có thể resize | Sửa page, split/merge; có thể random writes | WAL + memtable, flush; compaction nền |
| Ghi tuần tự vào file dữ liệu | Tùy thiết kế hash disk/log | Không phải mục tiêu chính của mọi cập nhật | Là ý tưởng trọng tâm ở flush/merge |
| Công việc nền | Resize/rehash hoặc log/snapshot | Checkpoint/page flush/vacuum tùy engine | Flush, compaction, cleanup |
| Xóa | Xóa/đánh dấu entry theo thiết kế | Xóa/đánh dấu, rebalance/versioning | Tombstone, compaction theo điều kiện an toàn |
| Durability tự có từ cấu trúc? | **Không** | **Không** | **Không** |
| Điểm cần đo | Collision, load factor, RAM/I/O | Page cache, split, random I/O, WAL | Compaction debt, RA/WA/SA, Bloom/cache |
| Phù hợp nổi bật | Lookup theo khóa | Lookup và range theo thứ tự | Workload ghi lớn và key–range có thể tổ chức |

**Bảng là xu hướng kỹ thuật**, không phải cam kết benchmark. Một B+tree được cache tốt có thể ghi rất nhanh, một LSM được tuning tốt có thể đọc range hiệu quả, và một hash-based storage có thể dùng cấu trúc phụ để hỗ trợ thứ tự.

## 32. Các lỗi suy luận thường gặp

| Nhận định | Vì sao chưa đúng | Cách hiểu nên dùng |
| --- | --- | --- |
| “NoSQL là key–value nên chắc chắn dùng hash table.” | API và cấu trúc vật lý khác nhau | Kiểm tra engine thật |
| “Hash lookup O(1) nên luôn nhanh nhất.” | Cache, collision, resize, I/O và query shape | Đo latency thực và phân bố tải |
| “Hash table không thể lưu bền vững.” | Có thể kết hợp log/snapshot/disk hashing | Tách cấu trúc truy cập khỏi durability |
| “B-tree luôn ghi ngẫu nhiên mỗi PUT.” | Buffer pool, WAL, batching có thể gom ghi | Xem write path thực |
| “B-tree không làm được update concurrent.” | Concurrency thuộc transaction/locking/MVCC layer | Xem guarantee của DBMS |
| “LSM chỉ dùng cho ghi, không hỗ trợ range.” | SSTable được sắp xếp và merge iterator | Đo range scan với số run |
| “WAL chính là memtable.” | WAL là log phục hồi; memtable là cấu trúc truy cập RAM | Hai thành phần khác vai trò |
| “Flush và compaction là một.” | Flush chuyển memtable ra SSTable; compaction hợp nhất tệp | Tách metric và tác động |
| “SSTable bất biến nên không thể xóa key.” | Tombstone cho phép xóa logic | Dọn vật lý cần compaction |
| “Tombstone có thể xóa ngay khi thấy.” | Có thể làm lộ version cũ hoặc ảnh hưởng replica | Chỉ dọn khi an toàn |
| “Compaction là tối ưu tùy chọn, bỏ cũng không sao.” | Backlog có thể làm chậm đọc/ghi và phình disk | Xem như công việc vận hành quan trọng |
| “LSM chắc chắn có WA thấp hơn B-tree.” | Compaction có thể ghi lại dữ liệu nhiều lần | Đo WA trên workload thực |
| “WAL ghi rồi là không bao giờ mất dữ liệu.” | Cần sync, hardware, replica/backup theo phạm vi lỗi | Mô tả rõ mốc ACK và failure model |
| “Replication thay thế backup.” | Xóa nhầm hoặc corruption có thể nhân bản | Thiết kế backup/restore riêng |
| “Durability tự bảo vệ số dư khỏi lost update.” | Durability khác isolation/invariant | Dùng atomic conditional update/transaction |
| “Hash partitioning nghĩa local storage dùng hash table.” | Hashing có thể chỉ dùng để chọn node | Tách sharding khỏi storage engine |

## 33. Bài tập thực hành

### Bài 1 — Chọn cấu trúc theo truy vấn

Hệ thống có ba nhu cầu:

~~~text
A. GET session theo sessionId; hầu như không scan.
B. Lấy đơn hàng theo customerId và createdAt trong 30 ngày.
C. Ghi 100.000 sự kiện/giây rồi truy vấn gần đây theo device/time.
~~~

Hãy chỉ ra **họ cấu trúc đáng đánh giá trước** cho từng nhu cầu và những điều phải đo trước khi quyết định.

**Gợi ý:** A gợi ý hash-based point lookup; B gợi ý B+tree hoặc LSM sorted key layout; C khiến LSM đáng khảo sát. Nhưng vẫn cần xác định durability, partitioning, latency và độ lớn dữ liệu.

### Bài 2 — Hash table và range scan

Một hash table chứa các key:

~~~text
item:001, item:002, item:003, ..., item:100000
~~~

Ứng dụng muốn trả các item từ `item:010000` đến `item:019999` theo thứ tự tăng. Vì sao hash table thuần túy không phải cấu trúc lý tưởng? Những phương án bổ sung nào có thể đáp ứng truy vấn?

**Gợi ý:** hash phá thứ tự key; có thể thêm B-tree/sorted index, duy trì một read model có thứ tự hoặc dùng storage engine hỗ trợ range scans.

### Bài 3 — Mô phỏng B+tree

Giả sử mỗi trang lá trong B+tree minh họa chỉ chứa tối đa 3 key.

~~~text
Leaf 1: [10,20,30]
Leaf 2: [40,50,60]
~~~

Khi thêm key `25`, trang nào được tìm? Vì sao có thể xảy ra split? Sau split cần cập nhật thành phần nào?

**Gợi ý:** tìm trang chứa miền key 10–30, chèn 25 làm vượt sức chứa mô phỏng; phải tạo/trang lại lá và cập nhật separator trong node cha theo thuật toán cụ thể.

### Bài 4 — Phiên bản cũ trong LSM

Cho:

~~~text
SSTable A: k=100 → "v1"
SSTable B: k=100 → "v2" (mới hơn)
Memtable:  k=100 → TOMBSTONE (mới nhất)
~~~

`GET k=100` phải trả gì? Vì sao compaction không được tự xóa tombstone khi chưa biết những version cũ đã được xử lý?

**Gợi ý:** trả NOT_FOUND; bỏ tombstone quá sớm có thể làm `v1` hoặc `v2` xuất hiện lại.

### Bài 5 — WAL và crash

Engine LSM ACK một lệnh PUT sau khi ghi memtable nhưng **trước khi WAL được sync**, rồi máy mất điện. Có thể khẳng định value vẫn tồn tại sau restart không?

**Gợi ý:** không. Kết quả phụ thuộc durability mode và những thành phần đã ghi thật sự bền vững trước crash.

### Bài 6 — Flush hay compaction?

Phân loại:

~~~text
A. Immutable memtable được ghi thành SSTable mới.
B. Nhiều SSTable được merge thành tệp mới.
C. Version cũ được bỏ sau khi xác minh an toàn.
D. WAL được replay để phục hồi memtable sau crash.
~~~

**Gợi ý:** A là flush; B/C liên quan compaction; D là recovery.

### Bài 7 — Đọc nhiều tệp và Bloom filter

Một engine LSM có 12 SSTable. Có Bloom filter hỗ trợ lookup một key. Nếu 11 filter báo “chắc chắn không có” và một filter báo “có thể có”, engine có được phép trả value ngay mà không kiểm tra tệp đó không?

**Gợi ý:** không. Bloom filter có false positive; phải kiểm tra key thật trong dữ liệu/index của tệp liên quan.

### Bài 8 — Write amplification

Ứng dụng ghi 5 GiB dữ liệu logic; tổng số byte storage device ghi do WAL, flush và compaction được đo là 35 GiB. Tính WA theo định nghĩa trong bài. Vì sao con số đó không thể so sánh trực tiếp với một dashboard chỉ tính bytes của SSTable?

**Gợi ý:** WA = 7 theo cách đo này; phải thống nhất thành phần numerator và denominator.

### Bài 9 — Workload chạy lâu

Một benchmark LSM chạy 30 giây đạt 150.000 PUT/giây, nhưng sau 2 giờ chỉ còn 40.000 PUT/giây và latency p99 tăng mạnh. Hãy nêu ít nhất bốn điều cần kiểm tra.

**Gợi ý:** compaction backlog, số SSTable ở level 0, write stalls, disk I/O, cache pressure, WAL sync, số version trùng, partition hot.

### Bài 10 — Durability và phân tán

Một DBMS ghi durable vào WAL của node A rồi ACK. Ngay sau đó ổ đĩa node A hỏng vật lý hoàn toàn. WAL có đủ để phục hồi dữ liệu không? Hãy nêu những thành phần nào khác có thể cần.

**Gợi ý:** không thể phục hồi từ WAL đã mất cùng ổ; cần replica, backup/snapshot, cơ chế failover và chính sách consistency phù hợp.

### Bài 11 — B-tree và LSM cho lịch sử đơn hàng

Một hệ có 95% đọc point lookup, 4% range scan và 1% ghi; hệ khác có 80% ghi, 15% point lookup, 5% range scan. Có thể khẳng định hệ đầu phải dùng B-tree và hệ sau phải dùng LSM không?

**Gợi ý:** không. Còn kích thước value, working set, SLA p99, đồng thời, shard routing, durability và cấu hình cache. Tỷ lệ read/write là tín hiệu, chưa phải phán quyết.

### Bài 12 — Vòng đời dữ liệu

Cassandra dùng TTL cho các sự kiện sau 30 ngày. Sau đúng 30 ngày, dung lượng đĩa chưa giảm. Điều đó có nhất thiết nghĩa TTL không hoạt động?

**Gợi ý:** không. Hết hạn logic, tombstone và compaction/dọn vật lý là các bước khác nhau. Phải xem policy và độ trễ/metric thực tế.

## 34. Mẫu ghi quyết định storage engine

Một nhóm thiết kế có thể dùng bảng YAML sau để tránh chọn engine chỉ bằng khẩu hiệu “ghi nhanh” hoặc “lookup nhanh”:

~~~yaml
dataset: "Order events"
businessPatterns:
  - "Append events by order and time"
  - "Point lookup by event ID"
  - "Range query by order/time"
volume:
  estimatedEventsPerDay: "TBD"
  payloadBytesP50: "TBD"
  payloadBytesP99: "TBD"
  peakWritesPerSecond: "TBD"
  retainedDays: 90
correctness:
  durabilityAfterAck: "Define tolerated failure model"
  atomicity: "Define transaction/write batch boundary"
  ordering: "Per-order ordering, if required"
  replication: "Define required replicas and ACK level"
storageEvaluation:
  candidates:
    - "B-tree/B+tree based engine"
    - "LSM-tree based engine"
  measures:
    - "Sustained write throughput"
    - "Point-read p95/p99"
    - "Range-read p95/p99"
    - "WAL sync and commit latency"
    - "Compaction/checkpoint stalls"
    - "Read/write/space amplification"
    - "Recovery time after crash"
    - "Disk use after TTL and deletion"
operationalQuestions:
  - "How are snapshots and backups produced?"
  - "Can online traffic continue during compaction/rebuild?"
  - "How are corrupt data files detected and repaired?"
  - "What happens on a full disk?"
  - "How are hot partitions distributed?"
decisionStatus: "Needs workload measurements"
~~~

Đây là **mẫu tài liệu**, không phải cấu hình cho một DBMS cụ thể. Các trường `TBD` cần dữ liệu đo hoặc giả định được ghi rõ; con số retention ở đây chỉ để minh họa.

## 35. Kết luận

**Hash table, B-tree và LSM-tree giải quyết những đánh đổi khác nhau của đường truy cập và cập nhật dữ liệu:**

1. **Hash table** tổ chức lookup theo hàm băm; thường hiệu quả cho point lookup, nhưng không tự giữ khóa theo thứ tự để quét khoảng. Hashing để chọn shard và hash table nội bộ là hai tầng khác nhau.
2. **B-tree/B+tree** tổ chức khóa theo thứ tự trên cây cân bằng với fan-out lớn; tốt cho point lookup và range scan. Việc sửa page, split và quản lý dirty pages tạo những chi phí riêng, được buffer pool và cơ chế durability hỗ trợ.
3. **LSM-tree** nhận ghi qua WAL/memtable rồi flush thành SSTable và compaction trong nền; đây là một mô hình thường hữu ích cho ghi lớn, nhưng phải quản lý nhiều version, tombstone, read amplification và compaction debt.
4. **Không cấu trúc nào tự bảo đảm durability.** Muốn biết một ghi đã ACK có sống qua crash/mất điện hay không phải xác định WAL/sync, checkpoint/manifest, replication, backup và phạm vi lỗi được cam kết.
5. **Không một cấu trúc nào luôn thắng mọi workload.** Hãy đo point lookup, range scan, ghi bền vững, tail latency, write/read/space amplification và công việc nền trên dữ liệu cùng tải đại diện.

**Nguyên tắc thực hành:** đừng chọn storage engine chỉ vì một nhãn “hash”, “B-tree” hoặc “LSM”. Hãy bắt đầu từ **mẫu truy cập, ranh giới nhất quán, yêu cầu độ bền và vòng đời dữ liệu**, sau đó đánh giá cách mỗi cấu trúc thực hiện **đọc, ghi, dọn và phục hồi**. Đó là nền tảng để thiết kế NoSQL vừa đạt hiệu năng vừa bảo vệ dữ liệu khi xảy ra lỗi.
