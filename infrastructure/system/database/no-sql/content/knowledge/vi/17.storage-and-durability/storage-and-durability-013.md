# Đối chiếu cơ chế lưu trữ thực tế trước khi suy luận hành vi

## 1. Mở đầu: cùng là NoSQL nhưng dữ liệu sống sót qua sự cố khác nhau

Một nhóm triển khai hai hệ thống:

- **Hệ A:** lưu trạng thái phiên và cache trong Redis.
- **Hệ B:** lưu đơn hàng trong một document database có journaling, replication và chính sách backup.

Cả hai đều được gọi chung là **NoSQL**. Ứng dụng đều có thể gửi lệnh ghi và nhận phản hồi thành công. Nhưng khi một máy chủ mất điện ngay sau phản hồi, liệu dữ liệu vừa ghi có được giữ lại?

Câu trả lời **không thể suy ra từ nhãn NoSQL**. Nó phụ thuộc vào hệ quản trị cụ thể, storage engine, cấu hình persistence, cách xác nhận ghi, cơ chế replication, topology, loại lỗi và cam kết vận hành.

Ngay cả khi dùng cùng một sản phẩm, hai cluster có cấu hình khác nhau vẫn có thể có mức bảo đảm khác nhau. Ví dụ một Redis chỉ dùng cache trong bộ nhớ sẽ khác Redis bật AOF hoặc snapshot; một database có replica không đương nhiên bảo đảm mọi ghi đã được lưu an toàn khi mất toàn bộ vùng; một search index trả kết quả nhanh không đương nhiên là nguồn dữ liệu bền vững.

**Mục tiêu bài học:** biết cách **đối chiếu cơ chế lưu trữ và cấu hình thật** trước khi kết luận về tốc độ ghi, khả năng đọc, độ bền, nguy cơ mất dữ liệu, xóa/TTL, khôi phục và các giới hạn vận hành.

## 2. Ba lớp cần tách bạch trước khi phân tích

### 2.1. Mô hình dữ liệu không phải storage engine

**Data model** trả lời dữ liệu được biểu diễn và truy vấn dưới dạng gì:

- Key–value: key trỏ tới value.
- Document: document và trường lồng nhau.
- Wide-column: partition và clustering columns.
- Graph: node, relationship và property.
- Search: document tìm kiếm và inverted index.

**Storage engine** trả lời các byte, trang, file, log và chỉ mục được tổ chức ra sao trên bộ nhớ và thiết bị lưu trữ.

Hai hệ cùng hỗ trợ document có thể dùng những cấu trúc on-disk, cache, log và checkpoint khác nhau. Ngược lại, một thư viện lưu trữ kiểu LSM có thể được dùng để hiện thực những sản phẩm với API và dữ liệu logic khác hẳn nhau.

### 2.2. API thành công không phải bằng chứng duy nhất về độ bền

Một ứng dụng gọi:

~~~text
PUT key=value
-> success
~~~

Phải hỏi tiếp:

- Success có nghĩa **server nhận request**, **đã sửa dữ liệu trong RAM**, **đã ghi log**, **đã sync xuống storage**, hay **đã được một quorum xác nhận**?
- Server nào xác nhận? Primary/leader, replica gần nhất hay nhiều replica?
- Nếu client timeout thì ghi thất bại hay đã thành công nhưng phản hồi bị mất?
- Dữ liệu có thể bị rollback khi failover không?
- Replica có nhận được cùng giá trị nhưng chưa lưu bền vững không?

Độ bền chỉ có ý nghĩa khi mô tả **mức xác nhận cùng mô hình lỗi** cụ thể.

### 2.3. Sản phẩm được triển khai khác với sản phẩm trong tài liệu

Một tài liệu kiến trúc nói “có WAL và replication” chưa đủ nếu:

- WAL đã bị tắt hoặc cấu hình sync khác mong đợi.
- Replication factor thực tế thấp hơn thiết kế.
- Các replica đặt cùng một failure domain.
- Disk là volume tạm hoặc snapshot chưa được bật.
- Database là dịch vụ managed có tầng lưu trữ bên dưới không công khai.
- Version triển khai khác version được mô tả trong tài liệu.

**Luôn đối chiếu sản phẩm, phiên bản, cấu hình và topology đang chạy** trước khi suy luận.

## 3. Các thuật ngữ phải phân biệt

| Thuật ngữ | Nghĩa cơ bản | Không nên đánh đồng với |
| --- | --- | --- |
| **Durability** | Ghi đã được cam kết vẫn tồn tại sau một phạm vi lỗi được định nghĩa | Availability, backup |
| **Availability** | Dịch vụ còn khả năng phục vụ yêu cầu trong phạm vi lỗi | Đảm bảo ghi mới không mất |
| **Consistency** | Các thao tác đọc/ghi quan sát trạng thái theo hợp đồng nhất quán | Durability |
| **Atomicity** | Một thao tác/transaction có hiệu lực toàn phần hoặc không có trong phạm vi cam kết | Replication |
| **WAL / redo log** | Ghi log thay đổi để phục hồi trạng thái | Backup lâu dài |
| **Journal / commit log** | Nhật ký ghi có semantics tùy engine | Cam kết đã fsync trong mọi cấu hình |
| **Page cache** | Bộ nhớ đệm các trang từ thiết bị lưu trữ | Bộ nhớ dữ liệu duy nhất |
| **Memtable** | Cấu trúc trong RAM nhận ghi trước khi flush | Dữ liệu đã chắc chắn nằm trên SSTable |
| **SSTable** | File sorted immutable thường gặp trong họ LSM | Toàn bộ dữ liệu đã compaction xong |
| **Checkpoint / flush** | Chuyển trạng thái từ bộ nhớ hoặc log vào dạng lưu bền khác | Backup có thể dùng để restore mọi thời điểm |
| **Compaction** | Gộp/sắp xếp lại file hoặc đoạn lưu trữ | Transaction commit |
| **Replication** | Duy trì nhiều bản sao dữ liệu | Bản sao lưu độc lập trước lỗi thao tác |
| **Backup** | Bản lưu phục hồi theo chính sách và mốc thời gian | Replica luôn có sẵn để chuyển đổi |
| **RPO** | Mức dữ liệu tối đa chấp nhận mất theo thời gian | Độ trễ phục vụ |
| **RTO** | Mục tiêu thời gian khôi phục dịch vụ | Bảo đảm không mất dữ liệu |

Một hệ có thể **durable nhưng tạm unavailable**. Một replica có thể **available nhưng đọc dữ liệu cũ**. Một cluster có thể **replicated nhưng mọi bản sao cùng xóa nhầm**, khi đó vẫn cần backup hoặc khả năng point-in-time restore.

## 4. Lần theo đường ghi: dữ liệu đi qua những lớp nào?

Sơ đồ khái niệm của một hệ có log và cấu trúc lưu trữ đĩa:

~~~mermaid
flowchart TD
    A["Client write"] --> B["API / leader / coordinator"]
    B --> C["Validation + concurrency control"]
    C --> D["Write-ahead / commit log"]
    C --> E["Memory structures / cache"]
    D --> F[("Persistent storage")]
    E --> G["Flush / checkpoint"]
    G --> H[("Data pages hoặc SSTables")]
    B --> R["Replication pipeline"]
    R --> S[("Other replicas")]
    B --> ACK["ACK theo write policy"]
    H --> I["Compaction / cleanup"]
~~~

Sơ đồ này chỉ là **mô hình suy luận**. Thứ tự log, memory update, replication và ACK có thể khác theo engine và cấu hình. Không suy ra rằng mọi database đi qua tất cả các node hoặc luôn ghi WAL trước khi nhận vào memory theo cùng một API.

### 4.1. Các mốc ghi rất khác nhau

Giả sử:

~~~text
t0: request tới leader
t1: ghi vào bộ nhớ của server
t2: append vào log của tiến trình / OS buffer
t3: yêu cầu hệ điều hành sync log xuống tầng lưu trữ
t4: replica khác xác nhận theo giao thức
t5: dữ liệu được flush thành data files
t6: checkpoint/compaction diễn ra
~~~

Ứng dụng có thể nhận ACK ở một mốc do **write concern/durability policy** quy định. Không có quy tắc rằng ACK luôn xảy ra sau t6; nhiều engine trả ACK rất lâu trước khi compaction.

### 4.2. Ghi vào RAM, ghi qua OS page cache và ghi bền không giống nhau

Gọi write() có thể chỉ chuyển dữ liệu vào buffer của hệ điều hành. Một yêu cầu fsync/fdatasync có thể giúp buộc đồng bộ dữ liệu theo semantics hệ thống file, nhưng kết quả thật còn phụ thuộc:

- File system, block device và storage controller.
- Cache của thiết bị, flush/barrier và bảo vệ mất điện.
- Loại volume local, network hoặc managed storage.
- Các lớp ảo hóa, RAID và cấu hình thực tế.

**“Có fsync” không có nghĩa dữ liệu bất tử trước mọi lỗi.** Nó là một mắt xích trong hợp đồng độ bền khi các tầng còn lại hoạt động theo bảo đảm đã công bố.

### 4.3. Dữ liệu đã bền không đồng nghĩa đã xuất hiện ở mọi đường đọc

Một ghi có thể được lưu bền ở nguồn nhưng:

- Replica đọc chậm hơn.
- Search index chưa refresh.
- Cache vẫn giữ bản cũ.
- Analytics/read model chưa nhận event.

Độ bền của nguồn và độ trễ đồng bộ bản chiếu là hai trục riêng. Đừng dùng “search chưa thấy” để kết luận “database chưa lưu”, cũng đừng dùng “database đã commit” để cam kết “mọi màn hình đều thấy ngay”.

## 5. Họ lưu trữ dựa trên B-tree hoặc B+tree

Một số storage engine tổ chức data page và index quanh cấu trúc cây cân bằng như B-tree/B+tree, kết hợp cache, journal/WAL và checkpoint.

Mô hình đơn giản:

~~~text
              [Root page]
               /      \
       [Internal]    [Internal]
         /   \          /   \
      leaf  leaf      leaf  leaf
~~~

Tìm key sẽ đi qua cây để đến page lá chứa record hoặc pointer phù hợp. Các page thường được cache để giảm I/O.

### 5.1. Suy luận hiệu năng nào có cơ sở?

- Lookup theo key và range có thể hiệu quả khi **index phù hợp**.
- Các page có tính locality giúp một số kiểu truy vấn theo thứ tự.
- Cập nhật có thể làm page dirty, split, tạo write amplification hoặc checkpoint I/O.
- Cache hit ratio và cấu trúc index có ảnh hưởng lớn tới độ trễ đọc.

Nhưng không thể kết luận:

> B-tree luôn đọc nhanh hơn LSM, hoặc B-tree không có write amplification.

Tốc độ thật phụ thuộc page size, cache, phân bố key, số index, độ chọn lọc, loại ổ đĩa, concurrency và cách engine ghi log/checkpoint.

### 5.2. Một page trong cache không có nghĩa đã bền

Nếu ứng dụng cập nhật dữ liệu rồi database thay đổi page ở memory, vẫn cần cơ chế log/checkpoint theo chính sách. Sau crash, engine có thể phải **replay log** hoặc phục hồi từ checkpoint.

Không nên tự suy từ việc “cây đã cập nhật” rằng thiết bị lưu trữ đã có đúng trạng thái cuối cùng.

## 6. Họ LSM-tree: memtable, WAL, SSTable và compaction

Nhiều hệ lưu trữ tối ưu ghi sử dụng **Log-Structured Merge-tree (LSM-tree)** hoặc các cấu trúc tương tự.

Một đường ghi khái niệm:

~~~mermaid
flowchart TD
    W["Incoming writes"] --> M["Memtable trong RAM"]
    W --> L["WAL / Commit log"]
    M --> F["Flush"]
    F --> S0[("SSTables level / tier đầu")]
    S0 --> C["Compaction"]
    C --> S1[("SSTables level / tier sau")]
    Q["Reads"] --> M
    Q --> S0
    Q --> S1
~~~

Trong một số engine, WAL append và memtable update được phối hợp theo thứ tự để phục hồi; chính xác ACK diễn ra khi nào phải xem implementation và cấu hình.

### 6.1. Memtable là cấu trúc đệm ghi

Memtable giữ dữ liệu mới trong RAM để cập nhật hiệu quả. Khi đạt ngưỡng hoặc theo cơ chế engine, dữ liệu được flush thành file sorted/immutable.

Nếu chỉ biết “ghi nằm trong memtable”, không thể kết luận đã bền. Phải kiểm tra **WAL/commit log có được lưu và sync theo điều kiện ACK hay chưa**.

### 6.2. SSTable không nhất thiết được sửa tại chỗ

SSTable thường là file bất biến, sắp theo key. Khi cập nhật một key, engine có thể giữ phiên bản mới trong memtable/SSTable mới, còn dữ liệu cũ chờ compaction.

Vì vậy:

~~~text
KEY K được ghi lần 1 -> file cũ có K=v1
KEY K được ghi lần 2 -> file mới có K=v2
Đọc K -> chọn giá trị hợp lệ mới nhất theo semantics engine
Compaction -> sắp xếp/gộp và dọn phiên bản không còn cần
~~~

Người dùng vẫn có thể đọc v2 trước khi compaction hoàn tất. **Compaction không phải bước xác nhận commit nghiệp vụ**.

### 6.3. Compaction là hoạt động nền có chi phí

Compaction có thể:

- Đọc lại nhiều file và ghi lại các file mới.
- Giảm số file cần đọc hoặc tổ chức dữ liệu theo level/tier.
- Dọn những phiên bản cũ/tombstone khi điều kiện an toàn được đáp ứng.
- Tăng disk I/O, CPU và tạm cần thêm dung lượng.

**Write amplification:** cùng một byte logic có thể được ghi nhiều lần qua log, flush và compaction.

**Read amplification:** đọc một key có thể phải xem nhiều cấu trúc/file nếu cache, Bloom filter hoặc compaction chưa tối ưu.

**Space amplification:** có thể tồn tại nhiều phiên bản/file tạm và dữ liệu chờ cleanup.

Không có chiến lược compaction tốt tuyệt đối. Workload ghi liên tục, range scan, TTL-heavy và read-hot có thể cần đánh đổi khác nhau.

### 6.4. Bloom filter không bảo đảm tìm thấy record

Một số LSM storage engine dùng **Bloom filter** để kiểm tra khả năng một key có trong file.

- Bloom filter có thể nói **“có thể tồn tại”**, dẫn tới tra file.
- Nếu được xây và sử dụng đúng, câu trả lời **“chắc chắn không có”** giúp bỏ qua file không liên quan.
- Có thể có **false positive**, nhưng không được có false negative trong mô hình hoạt động đúng.

Bloom filter có thể giảm read I/O khi lookup key không tồn tại, nhưng không tự chữa mọi truy vấn range, scan hoặc truy vấn thiếu index.

### 6.5. Tombstone và TTL trong LSM

Khi xóa key, engine có thể ghi **tombstone** thay vì xóa vật lý dữ liệu cũ ngay lập tức. Đọc phải tôn trọng tombstone; compaction xử lý cleanup theo các điều kiện của engine.

~~~text
SSTable cũ: K -> "A"
SSTable mới: K -> TOMBSTONE
Đọc K: không trả "A"
Compaction sau đó: dọn phiên bản cũ khi an toàn
~~~

Đây là ví dụ cơ chế logic. Trong hệ phân tán, retention của tombstone cần tính tới replica còn trễ hoặc repair; xóa tombstone quá sớm ở một số kiến trúc có thể gây **dữ liệu đã xóa xuất hiện lại**.

**Xóa không còn thấy** và **byte đã được thu hồi** không phải cùng thời điểm.

## 7. Đối chiếu LSM và B-tree mà không biến thành định kiến

| Khía cạnh | Họ B-tree/page-oriented | Họ LSM |
| --- | --- | --- |
| Tổ chức chính | Page cây và index có thể cập nhật/copy-on-write tùy engine | Memtable + file sorted và compaction |
| Ghi | Cập nhật logic page/index và log theo cơ chế engine | Buffer ghi và flush/compaction theo cơ chế engine |
| Đọc key | Tìm qua cây và cache | Kết hợp memtable, nhiều file/level, filter/cache |
| Range scan | Có thể tận dụng thứ tự key trong index | Có thể merge nhiều run/file đã sorted |
| Cleanup | Checkpoint, vacuum/rewrite tùy engine | Compaction, tombstone cleanup |
| Chi phí nền | Dirty-page flush, page split, checkpoint | Flush, compaction, bloom/filter maintenance |
| Đánh đổi | Locality, cache, fragmentation, WAL | Read/write/space amplification, compaction debt |

Đây là **bảng khái niệm**, không phải bảng xếp hạng tốc độ. Hai sản phẩm dùng cùng họ engine vẫn có thể khác rất xa vì:

- Chiến lược compaction, cache, compression.
- Loại transaction và index phụ.
- Ghi được sync theo chính sách nào.
- Replication, topology và thiết bị lưu trữ.
- Mô hình partition/shard, workload và dữ liệu.

**Không thể kết luận hành vi của một deployment chỉ từ từ khóa “LSM” hoặc “B-tree”.**

## 8. Ví dụ cụ thể: Cassandra không chỉ là “ghi rất nhanh”

Cassandra thường được mô tả bằng các thành phần **commit log, memtable, SSTable và compaction**. Một write đi qua coordinator tới các replica theo partition key và mức nhất quán yêu cầu.

~~~mermaid
flowchart LR
    C["Client write"] --> O["Coordinator"]
    O --> R1["Replica 1"]
    O --> R2["Replica 2"]
    O --> R3["Replica 3"]
    R1 --> L1["Commit log + memtable"]
    R2 --> L2["Commit log + memtable"]
    R3 --> L3["Commit log + memtable"]
    L1 --> S1[("SSTables")]
    L2 --> S2[("SSTables")]
    L3 --> S3[("SSTables")]
~~~

### 8.1. Xác nhận ghi phụ thuộc consistency level

Ví dụ với replication factor ba trong một topology phù hợp:

- **ONE:** coordinator có thể xác nhận khi một replica đáp ứng điều kiện ghi.
- **QUORUM:** yêu cầu quorum theo mô hình replica tương ứng.
- **LOCAL_QUORUM:** ràng buộc ở data center cục bộ.

Những tên này mô tả **số/nhóm replica cần xác nhận** theo protocol. Chúng **không tự cung cấp** kết luận rằng mọi replica đã fsync commit log tại thời điểm client nhận ACK.

Phải xem:

- Cấu hình **commitlog_sync**, chế độ batch/periodic và phiên bản Cassandra.
- Vai trò coordinator, timeout, hinted handoff và topology.
- Replication factor và cách phân phối replica theo rack/region.
- Mức consistency ở cả đọc lẫn ghi, cùng repair.
- Semantics lỗi khi coordinator đã gửi ghi nhưng client bị timeout.

### 8.2. Ghi được ACK không có nghĩa đã flush SSTable

Một write có thể được hệ xác nhận khi memtable/commit log đã đi qua các bước bảo đảm tương ứng, dù dữ liệu chưa tạo SSTable mới. Sau crash, engine có thể dùng commit log để khôi phục phần chưa flush.

Do đó:

> “Chưa thấy SSTable mới” không chứng minh ghi bị mất; “đã có SSTable” cũng không tự chứng minh toàn bộ replica nhất quán và có thể phục hồi ở cấp cluster.

### 8.3. Compaction strategy ảnh hưởng workload

Các chiến lược như **Size-Tiered**, **Leveled** hoặc **Time-Window** có thể phù hợp với các kiểu dữ liệu khác nhau:

- Ghi cập nhật thường xuyên.
- Đọc ngẫu nhiên theo key.
- Dữ liệu time-series có TTL.
- Scan theo khoảng trong một partition.

Time-window compaction có thể hữu ích khi dữ liệu theo thời gian và được ghi đúng thứ tự tương đối, nhưng cập nhật muộn, TTL khác nhau hoặc tombstone nằm ở nhiều file có thể tạo đặc điểm vận hành riêng.

Không được suy chỉ từ tên strategy rằng tombstone sẽ biến mất đúng sau TTL hoặc sau một khoảng thời gian cố định.

### 8.4. Tombstone, repair và deleted data

Khi một replica bỏ lỡ delete vì outage, các replica còn lại cần giữ thông tin xóa đủ lâu để quá trình repair/đồng bộ không cho bản giá trị cũ quay lại. Tham số như **gc_grace_seconds** và chiến lược repair cần được hiểu theo phiên bản và chính sách vận hành thực tế.

Chọn thời gian tombstone thấp chỉ để giảm disk usage có thể tạo rủi ro dữ liệu xóa bị hồi sinh nếu không đáp ứng điều kiện sửa chữa replica. Cần xem đúng hợp đồng của cluster, không lấy một giá trị TTL chung để quyết định.

## 9. MongoDB: storage engine, journaling, checkpoint và write concern

MongoDB có **document model** ở tầng API; với các deployment phổ biến, **WiredTiger** là storage engine sử dụng cơ chế cache, journaling và checkpoint. Không nên đồng nhất mô hình BSON với cách lưu page, cache và recovery.

### 9.1. Tầng vật lý và tầng logic khác nhau

Ở tầng API:

~~~javascript
db.orders.insertOne({
  orderId: "O1001",
  status: "PENDING",
  totalVnd: 450000
});
~~~

Ở tầng lưu trữ, engine có thể dùng page, cache, journal/checkpoint và các cấu trúc index phù hợp. Lệnh insert **không nói rõ** lúc nào data page được flush xuống file hoặc một backup đã được cập nhật.

### 9.2. Write concern là một phần của hợp đồng

Ví dụ ý tưởng ghi với write concern:

~~~javascript
db.orders.insertOne(
  {
    orderId: "O1002",
    status: "PENDING",
    totalVnd: 320000
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 5000
    }
  }
);
~~~

Điểm cần phân biệt:

- **w:** điều kiện xác nhận bởi node/replica theo topology.
- **j:** yêu cầu journaling acknowledgment theo semantics hỗ trợ.
- **wtimeout:** giới hạn chờ để nhận write concern acknowledgment; timeout không tự có nghĩa thao tác ghi đã bị rollback.

Hành vi chính xác của **majority**, journaling và các chế độ mặc định có thể phụ thuộc version/configuration. Đọc tài liệu của deployment hiện tại trước khi khẳng định mức mất dữ liệu có thể xảy ra.

### 9.3. Read concern và write concern là hai câu hỏi

Một ghi được đa số replica xác nhận chưa chắc đồng nghĩa:

- Mọi secondary đã bắt kịp.
- Một read từ bất kỳ secondary nào thấy ngay dữ liệu.
- Search/analytics đã cập nhật.

Write concern mô tả điều kiện xác nhận **ghi**. Read concern, read preference và session semantics ảnh hưởng điều kiện quan sát **đọc**. Không dùng cùng một từ “majority” để thay thế mọi khía cạnh.

### 9.4. Transaction commit, checkpoint và backup

Transaction đã commit theo hợp đồng MongoDB không có nghĩa một checkpoint mới hoặc một backup mới đã hoàn tất. Journal/recovery và checkpoint là cơ chế nội bộ phục vụ trạng thái dữ liệu; backup/PITR là đường bảo vệ và khôi phục khác, cần được cấu hình và thử riêng.

### 9.5. Cấu hình thật quan trọng hơn mô tả chung

Một khảo sát MongoDB phải biết:

- Server version, storage engine và deployment type.
- Replica set/sharding topology.
- Write concern/read concern mặc định và tại từng operation.
- Journaling và hành vi storage/volume.
- Backup/PITR và thời gian retention.
- Cache pressure, checkpoint behavior, disk headroom.

Một ứng dụng có thể vô tình ghi với write concern thấp hơn mức hệ thống kỳ vọng nếu từng thao tác/driver override cấu hình. Hãy kiểm tra **đường ghi thực của use case**, không chỉ đọc tài liệu cấu hình cluster.

## 10. Redis: từ in-memory store tới persistence có điều kiện

Redis thường đặt tập dữ liệu hoạt động trong RAM và cung cấp nhiều chiến lược persistence, tùy phiên bản/triển khai:

- **RDB snapshot:** chụp trạng thái tại những mốc đã cấu hình hoặc theo thao tác quản trị.
- **AOF (Append Only File):** ghi lại các lệnh thay đổi ở định dạng log để khôi phục.
- **Kết hợp cơ chế:** một số deployment có thể dùng đồng thời AOF và RDB.
- **Không bật persistence:** phù hợp với một số cache có thể tái tạo, nhưng không phù hợp nếu nghiệp vụ trông đợi dữ liệu bền vững sau restart.

### 10.1. RDB snapshot và cửa sổ mất dữ liệu

~~~text
10:00 Snapshot được tạo
10:01 Đặt key quan trọng
10:02 Máy chủ mất dữ liệu volatile
~~~

Nếu chỉ có snapshot 10:00 và không có cơ chế ghi bền khác, phần thay đổi sau snapshot có thể mất khi khôi phục. Khoảng mất dữ liệu phụ thuộc lịch snapshot và tình huống lỗi thực tế, không cố định theo nhãn Redis.

### 10.2. AOF và fsync policy

Trong các cấu hình Redis có AOF, **appendfsync** thường có những lựa chọn như:

- **always:** yêu cầu đồng bộ thường xuyên hơn, có chi phí.
- **everysec:** chính sách đồng bộ định kỳ khoảng một giây; không nên biến thành bảo đảm tuyệt đối “chỉ mất đúng một giây”.
- **no:** để hệ điều hành kiểm soát lịch sync theo cơ chế tương ứng.

Phải xét thêm phiên bản, hoạt động rewrite AOF, tình trạng disk và replication. Không nên kết luận “bật AOF = zero data loss” trong mọi failure mode.

### 10.3. Replication và persistence là hai trục

Primary có thể gửi thay đổi tới replica trong RAM nhưng replica chưa lưu bền theo chính sách storage. Một lệnh chờ replica xác nhận nhận ghi **không tự là bằng chứng mọi bản sao đã fsync**.

Failover có thể thay đổi node phục vụ đọc/ghi, nhưng dữ liệu mới nhất có được giữ hay không phụ thuộc cơ chế replica acknowledgment, lag, durability và thời điểm lỗi.

### 10.4. Eviction không phải xóa nghiệp vụ

Nếu Redis được cấu hình làm cache với eviction policy:

~~~text
maxmemory reached
    -> eviction theo policy
    -> key biến mất khỏi cache
~~~

Key mất do eviction hoặc TTL không chứng minh người dùng đã chủ động xóa record gốc. Nếu Redis là **source of truth**, việc cho phép evict key theo memory pressure có thể làm sai nghiệp vụ.

Hãy phân biệt:

- Cache mất key có thể được tái tạo từ nguồn bền.
- Session mất key có thể buộc đăng nhập lại, nếu hợp đồng cho phép.
- Số dư, đơn hàng hoặc khóa nghiệp vụ duy nhất không thể tùy tiện mất chỉ vì thiếu RAM.

### 10.5. Khảo sát nhanh cấu hình Redis

Trên môi trường có quyền phù hợp, các lệnh như:

~~~redis
INFO persistence
INFO replication
CONFIG GET appendonly
CONFIG GET appendfsync
CONFIG GET save
CONFIG GET maxmemory-policy
~~~

giúp thu thập trạng thái persistence và eviction. Một managed service có thể hạn chế CONFIG hoặc dùng cấu hình qua control plane; không được coi việc lệnh bị từ chối là bằng chứng không có persistence.

## 11. RocksDB và embedded storage engine: thư viện khác database service

RocksDB là ví dụ về một **embedded key–value storage engine** dựa trên LSM, được ứng dụng hoặc một hệ quản trị khác tích hợp. Vì là thư viện, behavior của ứng dụng phụ thuộc vào:

- RocksDB options tại thời điểm mở database.
- WAL có bật không, sync write được yêu cầu không.
- Memtable, block cache, write buffer.
- Compaction style và compression.
- Cách ứng dụng mở/đóng database, xử lý crash và checkpoint.
- Thiết bị lưu trữ đặt database files.

### 11.1. Một ví dụ ý tưởng cấu hình ghi

~~~java
// Pseudocode minh họa semantics của một engine nhúng.
WriteOptions options = new WriteOptions()
    .setSync(true)
    .setDisableWAL(false);

database.put(options, keyBytes, valueBytes);
~~~

Ví dụ phản ánh các khái niệm **sync** và **WAL**, không phải code hoàn chỉnh có thể chạy không cần import, mở database hoặc đóng resource. Cần đối chiếu API và cách quản lý native resources ở đúng phiên bản thư viện.

Nếu application chọn disable WAL hoặc không yêu cầu sync, phạm vi có thể mất dữ liệu khi crash sẽ khác một cấu hình ghi có đồng bộ log. Tuy nhiên, bật sync cũng không thay backup, replication, xử lý lỗi ổ đĩa và kiểm thử recovery.

### 11.2. Embedded database không tự có replication

RocksDB lưu dữ liệu tại một process/máy nếu ứng dụng dùng nó như embedded engine. Replication, leader election, failover hoặc transaction phân tán phải đến từ **tầng sản phẩm bao quanh** hoặc được ứng dụng tự thiết kế.

Đừng suy từ việc “engine dùng RocksDB” rằng hệ thống đương nhiên có quorum hoặc đa vùng.

## 12. DynamoDB và managed NoSQL: tránh suy đoán implementation kín

Một dịch vụ managed như DynamoDB công bố **API, mô hình partition/index, consistency, durability và backup** ở cấp dịch vụ. Người sử dụng thường không có đủ bằng chứng để khẳng định cụ thể service đó đang dùng một cấu trúc file, compaction hay thiết bị vật lý nào trong từng phiên bản hạ tầng.

Điều nên dựa vào:

- Hợp đồng **PutItem, UpdateItem, TransactWriteItems** và conditional write.
- Semantics **eventual/strongly consistent read** trong phạm vi được hỗ trợ.
- Hành vi của **Global Secondary Index** và độ trễ cập nhật.
- Retry, throttling, timeout, idempotency.
- Backup/PITR, export/restore, replication đa vùng nếu dùng.
- Giới hạn phục vụ, item size, hot partition và capacity.

Điều không nên tuyên bố nếu không có nguồn kỹ thuật xác thực:

> Mọi ghi DynamoDB chắc chắn đi qua memtable loại X, SSTable loại Y và compaction ở thời điểm Z.

Đó là một giả định implementation không cần thiết để thiết kế ứng dụng. **Ưu tiên service contract và phép đo** hơn suy diễn về storage internals không được công bố.

### 12.1. GSI không phải nguồn nhất quán mạnh cho mọi quyết định

Một write vào base table được service xác nhận theo hợp đồng không đồng nghĩa GSI đã có thể đọc ngay trạng thái mới. GSI là một đường truy cập được cập nhật theo cơ chế eventual.

Nếu ứng dụng cần uniqueness hoặc tồn kho, không được dùng:

~~~text
Query GSI: không thấy item
-> kết luận được phép cấp phát resource duy nhất
~~~

thay cho conditional write/transaction phù hợp tại nguồn authoritative.

### 12.2. Multi-region không tự cho mọi thao tác một thứ tự toàn cục

Khi dùng dữ liệu đa vùng có nhiều writer, phải xem semantics **conflict resolution**, replication lag và tính nhất quán của sản phẩm/phiên bản cụ thể. Không suy rằng thêm region đồng nghĩa mọi thao tác có linearizability toàn cầu hoặc không bao giờ cần giải quyết xung đột.

## 13. Search index: refresh, transaction log và tính dẫn xuất

Elasticsearch/OpenSearch sử dụng cơ chế indexing/search với Lucene segment, refresh, translog và flush theo version/thiết lập thực tế.

Một luồng khái niệm:

~~~text
Index request
    -> engine ghi nhận thay đổi
    -> dữ liệu được refresh thành searchable view
    -> các segment/transaction-log được flush/merge theo cơ chế
~~~

### 13.1. Được ACK không đồng nghĩa tìm thấy ngay

Một write vào search index có thể được xác nhận trước khi tài liệu trở nên khả kiến trong kết quả search. Nếu ứng dụng kiểm tra:

~~~text
POST /articles/_doc/A123 -> success
GET /articles/_search?q=... -> chưa thấy A123
~~~

không thể lập tức kết luận indexing đã mất. Cần phân biệt **write acknowledgment**, **search refresh** và **replica visibility**.

### 13.2. Search có thể không phải nguồn chính

Nếu search index được xây từ database nguồn, có thể khôi phục nó bằng **reindex** khi giữ đủ dữ liệu và event log. Nhưng cần:

- Dữ liệu nguồn đầy đủ.
- Mapping/analyzer/schema version phù hợp.
- Replay update/delete sau snapshot.
- Bảo vệ không hồi sinh document đã xóa.

Nếu chỉ còn search index mà nguồn đã mất, nội dung/tính nhất quán và quan hệ nghiệp vụ có thể không đủ để tái dựng hệ thống.

### 13.3. Compaction/segment merge không phải xóa tức thời

Một document bị xóa có thể ngừng xuất hiện trong search trước khi các byte cũ trong segment được thu dọn. Backup/snapshot cũng có vòng đời riêng. Không suy từ query không thấy record rằng dữ liệu đã bị xóa vật lý khỏi mọi lớp.

## 14. Bảng đối chiếu nhanh: biết gì và chưa biết gì?

| Hệ hoặc loại | Cơ chế nên kiểm tra | Không được suy từ tên sản phẩm |
| --- | --- | --- |
| MongoDB | Storage engine, journaling, checkpoint, write/read concern, replica topology | Mọi ghi thành công đều đã hiện trên mọi secondary |
| Cassandra | Commit log sync, memtable/SSTable, compaction, RF/CL, repair/tombstone | QUORUM đồng nghĩa mọi replica đã fsync và không thể mất dữ liệu |
| Redis | RDB/AOF, appendfsync, replication, maxmemory eviction, TTL | Dùng Redis đồng nghĩa vừa nhanh vừa bền như database giao dịch |
| RocksDB embedded | WAL/sync options, memtable, SST/compaction, file placement | Thư viện tự có replication và failover |
| DynamoDB | Service API contract, strong/eventual reads, GSI, PITR, global tables | Biết chính xác SSTable/compaction nội bộ của managed service |
| Elasticsearch/OpenSearch | Translog, refresh, flush, segment merge, snapshots, replicas | ACK index đồng nghĩa search thấy ngay hoặc đã dọn vật lý |
| Neo4j / graph DB | Transaction log/checkpoint, page cache, index, clustering theo version | “Graph” tự suy ra cơ chế lưu hoặc độ bền khác nhau |

Bảng là **bản đồ câu hỏi cần xác minh**, không thay tài liệu version cụ thể. Trong một deployment có thể còn proxy, tiered storage, object store, cache tầng dịch vụ hoặc plugin làm thay đổi đường dữ liệu.

## 15. Sơ đồ câu hỏi cần điều tra một thao tác ghi

~~~mermaid
flowchart TD
    A["Ứng dụng nhận ACK ghi"] --> B{"ACK theo hợp đồng nào?"}
    B --> C["Đọc write policy, version, driver"]
    C --> D{"Log / journal được ghi và sync khi nào?"}
    D --> E["Kiểm tra storage config và failure domain"]
    E --> F{"Cần bao nhiêu replica ACK?"}
    F --> G["Đối chiếu topology và replication status"]
    G --> H{"Kịch bản lỗi nào phải chịu được?"}
    H --> I["Process / host / AZ / region / xóa nhầm"]
    I --> J["Recovery plan + backup + failover"]
    J --> K["Thử trong môi trường kiểm soát"]
~~~

Không nên nhảy thẳng từ:

> “Database này dùng WAL.”

sang:

> “Mọi ghi sau ACK đều an toàn khi mất cả một region.”

WAL là một cơ chế trong một node; kết luận đa vùng còn phụ thuộc replication, failure domain và khả năng phục hồi.

## 16. Phân loại lỗi: độ bền luôn gắn với một failure model

| Tình huống | Câu hỏi cần xác minh |
| --- | --- |
| Ứng dụng client crash | Server đã commit chưa? Client có thể retry an toàn không? |
| Database process crash | WAL/journal/recovery phục hồi trạng thái nào? |
| Host restart | Data volume có persistent không? Cache nào mất? |
| Mất điện/thiết bị hỏng | Đã sync theo hợp đồng? Disk failure handling và replica ở đâu? |
| Mất một node | Replica quorum và leader failover có đủ không? |
| Mất một availability zone | Replica nằm ở AZ khác và được phép failover không? |
| Mất một region | Có dữ liệu vùng khác và chính sách cross-region replication phù hợp không? |
| Partition mạng | Hệ ưu tiên availability hay write consistency theo loại thao tác? |
| Operator xóa nhầm | Backup/PITR và audit có cho phục hồi bản trước delete không? |
| Bug ghi dữ liệu sai | Replica có nhân bản sai lầm không? Có lịch sử/audit/rollback không? |
| Ransomware hoặc credential compromise | Backup có cô lập quyền, immutable/retention phù hợp không? |

### 16.1. Process crash khác mất toàn bộ host

Process crash có thể giữ OS page cache và thiết bị nguyên vẹn; host power loss đặt ra câu hỏi về sync/write cache. Một bài test chỉ restart database **không chứng minh** hệ chịu được mất điện đột ngột.

### 16.2. Replica không thay thế backup

Nếu ứng dụng xóa nhầm một collection và thao tác được replication thành công, cả primary và replica có thể cùng mất dữ liệu logic. Replication tăng khả năng tiếp tục phục vụ khi node lỗi, nhưng **không tự bảo vệ khỏi thao tác hợp lệ mà sai**.

### 16.3. Timeout không trả lời được trạng thái commit

~~~text
Client -> DB: CreateOrder(id=O1001)
DB commit thành công
Mạng đứt trước khi ACK tới client
Client thấy timeout
~~~

Nếu client gọi lại bằng ID mới, có thể tạo hai đơn. Cần **idempotency key/conditional write** và khả năng truy vấn trạng thái đã commit.

Một request timeout không được mặc định là “chưa ghi”; một request thành công cũng chỉ có độ bền trong phạm vi write policy đã chọn.

## 17. Tính nhất quán và độ bền là hai trục tách biệt

### 17.1. Có thể đọc cũ nhưng dữ liệu mới vẫn đã bền

Giả sử:

~~~text
Primary: version 42 đã commit theo write concern
Replica: version 41 chưa bắt kịp
Search:  version 40 chưa refresh
~~~

Một người dùng đọc replica/search thấy version cũ không nhất thiết là bằng chứng write version 42 đã mất. Đó có thể là **replication/index lag**.

### 17.2. Có thể đọc mới nhưng vẫn chưa có cam kết bền tương ứng

Một cache ghi vào RAM có thể trả ngay giá trị mới. Điều này chỉ chứng minh reader đó quan sát memory state hiện tại, không chứng minh ghi sẽ sống sót qua host power loss.

### 17.3. Strong read không thay backup

Một hệ linearizable có thể trả đúng trạng thái mới nhất, rồi người dùng có quyền quản trị xóa nhầm tất cả. Strong consistency không tự cung cấp điểm khôi phục về hôm qua.

### 17.4. Quorum không phải bảo đảm thần kỳ

Trong một số mô hình replica, điều kiện giao nhau của read/write quorum được viết:

\[
R + W > N
\]

Với N là số replica và R/W là số phản hồi cần cho đọc/ghi. Đây là trực giác về **giao nhau giữa quorum**, không đủ để kết luận mọi đọc đều linearizable hay mọi ACK đều đã sync xuống storage.

Cần xem phiên bản, replica placement, sloppy quorum nếu có, protocol giải quyết phiên bản và semantics acknowledgment. Không dùng bất đẳng thức để thay thế hợp đồng sản phẩm.

## 18. Partition, shard, cache và đường đọc có thể làm sai suy luận

Hai truy vấn cùng “GET key” có thể đi qua hai đường khác nhau:

~~~text
GET /orders/O1001
    -> API cache
    -> primary read

GET /orders/search
    -> search index
    -> async projection
~~~

Nếu API cache còn giá trị cũ, việc thấy dữ liệu cũ không chứng minh storage engine chưa ghi bền. Nếu shard đang di chuyển, query timeout có thể do định tuyến hoặc tải, không phải dữ liệu bị xóa. Nếu index bị thiếu entry, dữ liệu gốc vẫn có thể tồn tại.

**Trước khi truy lỗi độ bền, hãy vẽ đường đọc thực tế**:

1. Client gọi endpoint nào?
2. API đọc cache hay source?
3. Query dùng shard/partition/index nào?
4. Read preference/consistency level nào?
5. Có asynchronous projection hoặc CDN không?
6. Có retry hoặc fallback gây quan sát khác nhau không?

Một thử nghiệm chỉ gọi API qua cache không thể chứng minh nội dung của journal hay SSTable ở nguồn.

## 19. Checkpoint, compaction, TTL và xóa: đừng nhầm những mốc vật lý

### 19.1. Checkpoint

Checkpoint giúp engine giới hạn lượng log phải replay và tạo mốc phục hồi. Nhưng checkpoint:

- Không nhất thiết là toàn bộ backup độc lập.
- Không tự chứng minh mọi replica có cùng checkpoint.
- Không đồng nghĩa dữ liệu vừa được ACK chỉ có bền sau checkpoint.
- Có thể diễn ra theo chu kỳ/áp lực cache và làm thay đổi I/O.

### 19.2. Compaction

Compaction tổ chức lại dữ liệu lưu trữ và có thể dọn record/version không còn cần. Không nên dùng **thời điểm compaction xong** làm mốc transaction nghiệp vụ; engine có thể phục vụ trạng thái mới từ các file chưa merge.

### 19.3. TTL

TTL là quy tắc hết hạn logic, không nhất thiết là timer xóa byte đúng tới mili-giây.

~~~text
expiresAt = 10:00
10:00:01 Query không còn trả giá trị theo TTL
10:05     Job cleanup/compaction có thể vẫn đang xử lý
~~~

Hành vi cụ thể khác nhau ở Redis, Cassandra, MongoDB TTL index, DynamoDB TTL và search index. Không nên suy cùng một semantics cho tất cả.

### 19.4. Xóa và phục hồi dữ liệu đã xóa

Một tombstone có thể ngăn đọc giá trị cũ trong khi file/replica khác vẫn còn bản cũ. Nếu tombstone bị thu dọn trước khi một replica lag được repair, hệ có thể có rủi ro dữ liệu “sống lại” tùy thuật toán.

Phải kiểm tra chính sách **retention, repair, compaction, replication và restore** cùng nhau. Chỉ xem một lệnh DELETE trả success chưa đủ để kết luận tất cả bản sao và bản lưu đã sạch.

## 20. Backup, snapshot và point-in-time recovery

Độ bền của database và khả năng khôi phục là hai yêu cầu liên quan nhưng khác nhau.

### 20.1. Snapshot

Snapshot là một bản trạng thái tại một mốc theo cơ chế sản phẩm/storage. Cần biết:

- Snapshot có nhất quán ở mức table/cluster/transaction không?
- Có bao gồm journal/log cần thiết để restore không?
- Snapshot file system có phối hợp với database không?
- Mất bao lâu để tạo, lưu và phục hồi?
- Có thể kiểm tra tính toàn vẹn không?

Một bản copy ngẫu nhiên các file đang thay đổi **không phải mặc nhiên là backup nhất quán**.

### 20.2. Point-in-time recovery (PITR)

PITR dùng snapshot cùng chuỗi log/change thích hợp để khôi phục về một thời điểm trong khoảng được hỗ trợ.

~~~text
00:00  Base backup
00:00–12:00  Logs/changes được giữ
10:35  Operator xóa nhầm
10:34:59  Mốc muốn phục hồi
~~~

PITR chỉ khả dụng nếu dịch vụ/cluster đã cấu hình đúng, log đủ, retention không bị vượt và quy trình restore được thử nghiệm.

### 20.3. RPO và RTO

**Recovery Point Objective (RPO):** hệ chấp nhận mất tối đa bao nhiêu dữ liệu khi khôi phục.

**Recovery Time Objective (RTO):** hệ cần khôi phục khả năng phục vụ trong bao lâu.

Ví dụ mục tiêu giả định:

~~~text
Đơn hàng chính thức:
  RPO = gần 0 theo phạm vi sự cố đã quy định
  RTO = 30 phút

Cache gợi ý:
  RPO = chấp nhận tái tạo toàn bộ
  RTO = vài giờ hoặc giảm chức năng tạm thời
~~~

Các số chỉ minh họa. Nếu backup được tạo mỗi 24 giờ mà không có log bổ sung, khó tuyên bố RPO 5 phút cho mọi sự cố.

### 20.4. Restore là một phần của kiểm chứng độ bền

“Backup job success” mới chứng minh công việc backup báo thành công theo một hợp đồng. Phải **thử restore** để biết:

- File có đọc được không?
- Khóa mã hóa và quyền truy cập có sẵn không?
- Có tương thích version engine/schema không?
- Recovery có đạt RTO không?
- Index/materialized view có rebuild đúng không?
- Các thao tác delete sau snapshot có được replay khi cần không?

Không chỉ đo dung lượng backup; hãy đo **khả năng khôi phục một hệ thống có thể phục vụ lại**.

## 21. Đối chiếu cấu hình đang chạy: một checklist điều tra cụ thể

### 21.1. Nhận dạng deployment

Ghi lại:

~~~text
Product:
Version/build:
Managed hay self-hosted:
Storage engine nếu được công bố:
Driver/SDK version:
Cluster topology:
Region/AZ/rack placement:
Data volume type:
Runtime read/write configuration:
Backup/PITR status:
~~~

### 21.2. Thu thập đường ghi thực

Với mỗi use case quan trọng:

~~~text
Operation: CreateOrder
API/SDK method:
Write concern / consistency level:
Transaction boundary:
Idempotency policy:
Number/location of replicas:
Expected ACK meaning:
Accepted failure model:
Recovery mechanism:
~~~

Một cluster có thể có default an toàn nhưng một thư viện ghi dữ liệu cấu hình override riêng. Vì vậy phải đọc **cấu hình SDK/call path thực tế**, không chỉ dashboard cluster.

### 21.3. Quan sát hoạt động nền

Các dấu hiệu hữu ích:

- Journal/WAL/commit log sử dụng và lỗi I/O.
- Memtable hoặc write buffer pressure.
- Số file/level, compaction backlog hoặc pending tasks.
- Checkpoint duration, dirty pages, disk utilization.
- Cache hit/miss và eviction.
- Replication lag, quorum failures và repair status.
- Backup age, restore validation và log retention.

Không suy trực tiếp “compaction backlog cao = chắc chắn mất dữ liệu”. Nó là tín hiệu vận hành có thể ảnh hưởng latency, disk headroom hoặc đọc/ghi, cần đặt trong bối cảnh.

## 22. Ví dụ lệnh quan sát, không phải thao tác cấu hình

Các lệnh dưới đây chỉ để **minh họa cách thu thập chứng cứ**; có thể cần quyền quản trị hoặc bị hạn chế trên managed service. Không chạy thay đổi cấu hình trên production chỉ để thử bài học.

### 22.1. MongoDB

Ví dụ trong mongosh:

~~~javascript
db.adminCommand({ buildInfo: 1 });
db.adminCommand({ serverStatus: 1 });
db.adminCommand({ getCmdLineOpts: 1 });
~~~

Thông tin cần xem tùy cấu hình:

- Version và build.
- Storage engine/cache/journal metrics nếu được công bố.
- Replica, replication status và write concern thực tế.
- Các tham số startup/runtime liên quan.

Không phải account nào được phép chạy mọi command; managed service có thể che các thông tin nội bộ. Output của serverStatus cũng thay đổi theo version và engine.

### 22.2. Cassandra

Những lệnh vận hành thường gặp:

~~~text
nodetool status
nodetool tablestats
nodetool compactionstats
~~~

Đối chiếu cùng cấu hình node/cluster:

~~~text
commitlog_sync
replication settings
compaction strategy
gc_grace_seconds
repair schedule
~~~

Không lấy một snapshot nodetool đơn lẻ làm chứng cứ rằng toàn cluster đã bền; cần xem cả nhật ký lỗi, topology, metric dài hạn và mức ghi/đọc của ứng dụng.

### 22.3. Redis

~~~redis
INFO persistence
INFO replication
CONFIG GET appendonly
CONFIG GET appendfsync
CONFIG GET save
CONFIG GET maxmemory-policy
~~~

Nếu CONFIG không được phép trên dịch vụ managed, đọc parameter group/control plane và tài liệu của nhà cung cấp. Phải đối chiếu actual config và data volume, không chỉ default ngoài tài liệu.

### 22.4. DynamoDB

Ưu tiên API/control plane được hỗ trợ:

~~~text
DescribeTable
DescribeContinuousBackups
ListBackups
CloudWatch metrics theo table/index
~~~

Những API trên giúp xác minh trạng thái dịch vụ/backup/index/capacity trong phạm vi được công bố. **Không suy luận ngược** từ chúng ra loại cấu trúc on-disk nội bộ chưa được xác nhận.

### 22.5. Elasticsearch/OpenSearch

Ví dụ request quan sát:

~~~http
GET /_cluster/health
GET /_nodes/settings
GET /_cat/segments?v
GET /_cat/indices?v
~~~

Cần đọc cùng mapping/index lifecycle, refresh settings, translog/flush metrics và snapshot repository status. Một cluster health “green” không đồng nghĩa mọi bản ghi vừa ACK đã searchable ngay hoặc mọi snapshot phục hồi được.

### 22.6. Đường quan sát của ứng dụng

Ngoài config database, bổ sung metric ở lớp API:

~~~text
Write ACK duration
Write concern timeout
Retry count
Idempotency conflict count
Read-after-write lag
Replica/read model lag
Restore test result
Data reconciliation mismatch
~~~

Một lỗi do client timeout hoặc cache stale có thể trông như lỗi storage nếu chỉ nhìn API response. Trace xuyên application, driver và database giúp khoanh vùng đúng hơn.

## 23. Kiểm thử giả thuyết lưu trữ một cách an toàn

Lý thuyết về storage engine chỉ hữu ích khi được đối chiếu với hành vi **đã cấu hình**. Nhưng thử lỗi kiểu rút điện, xóa file dữ liệu hay tắt journal trên production là không phù hợp.

### 23.1. Môi trường thử nghiệm

Chuẩn bị một deployment **riêng**, cùng sản phẩm/phiên bản/cấu hình quan trọng và loại volume gần với production. Dữ liệu giả lập nhưng có phân phối và tải tương tự:

- Document nhỏ/lớn.
- Write update liên tục.
- TTL/delete và tombstone.
- Read/write concurrency.
- Partition hot, cache pressure.
- Index và backup đang hoạt động.

Kết quả từ môi trường thử không tự thay thế cam kết sản phẩm, nhất là khi hạ tầng managed production có những tầng không thể mô phỏng đầy đủ.

### 23.2. Kiểm thử ACK và crash

Quy trình khái niệm:

1. Ghi một tập record với ID duy nhất và lưu danh sách request đã được **ACK**.
2. Ghi thêm record mà client có thể chưa nhận ACK.
3. Gây lỗi process trên môi trường cô lập theo phương án được phê duyệt.
4. Khởi động lại database theo runbook.
5. Đọc authoritative state và đối chiếu ID/version.
6. Phân loại mất dữ liệu, ACK ambiguous, retry, duplicate.

**Không đánh đồng record chưa ACK nhưng vẫn tồn tại là lỗi.** Nó có thể đã commit trước khi phản hồi mất. Trường hợp quan trọng nhất là bảo đảm dành cho các record đã ACK **trong failure model đã thử**.

### 23.3. Kiểm thử replication/failover

Trong môi trường kiểm thử:

- Ghi với từng mức write concern cần hỗ trợ.
- Gây lỗi một node hoặc cô lập một đường mạng có kiểm soát.
- Xác minh semantics khi writer timeout.
- Đối chiếu dữ liệu đã ACK sau failover.
- Kiểm tra replica lag và thời gian phục vụ trở lại.

Không suy từ một thử nghiệm lỗi một node rằng hệ có thể sống sót qua mất region hoặc mất tất cả replica cùng lúc.

### 23.4. Kiểm thử restore

Tạo backup, thêm dữ liệu, xóa nhầm một tập mẫu rồi restore/PITR trên môi trường riêng. Đo:

- Mốc dữ liệu được phục hồi.
- Thời gian phục hồi.
- Số bản ghi/version lệch.
- Khả năng chạy lại ứng dụng và index.
- Các thay đổi/delete cần replay.

Đây là phép thử trực tiếp hơn nhiều so với chỉ xem trạng thái “backup thành công”.

### 23.5. Kiểm thử compaction và TTL

Tạo dữ liệu có nhiều update/delete, theo dõi compaction, tombstone và disk headroom. Quan sát:

- Dữ liệu có hết hiển thị theo semantics TTL không?
- Disk usage giảm vào giai đoạn nào?
- Read latency thay đổi ra sao khi compaction backlog tăng?
- Có bản ghi hồi sinh sau replica recovery/reindex không?

Không đặt mục tiêu “byte phải biến mất ngay sau TTL” nếu engine không có hợp đồng như vậy.

## 24. Kiểm chứng một kết luận bằng chứng cứ nhiều tầng

Một kết luận kỹ thuật tốt có cấu trúc:

> Trong cluster X, phiên bản Y, thao tác Z dùng write policy P. Theo hợp đồng của sản phẩm, ACK có nghĩa A. Cấu hình và topology hiện tại là B. Kiểm thử lỗi F trên môi trường tương ứng quan sát C. Vì vậy hệ đáp ứng mục tiêu M **trong phạm vi điều kiện đó**; chưa có bằng chứng cho các lỗi ngoài phạm vi như mất toàn region.

Đối chiếu với một kết luận quá chung:

> Database này là NoSQL dùng WAL nên bảo đảm không bao giờ mất dữ liệu.

Câu thứ hai bỏ qua write policy, fsync, replication, failure domain và backup.

### 24.1. Ma trận chứng cứ

| Cần chứng minh | Nguồn chứng cứ phù hợp | Chưa chứng minh được gì |
| --- | --- | --- |
| Engine đang dùng | Runtime metadata/config của deployment | Mọi write đều có cùng durability |
| WAL/journaling bật | Config/runtime status | Log đã sync theo từng ACK |
| ACK bởi quorum | SDK request + cluster policy + logs | Các replica đều ở AZ độc lập |
| Đọc thấy ngay | Read policy + test read-after-write | Dữ liệu tồn tại qua power loss |
| Có backup | Backup catalog/status | Backup restore được trong RTO |
| Replica lag thấp | Metrics dài hạn | Operator xóa nhầm có thể khôi phục |
| Compaction khỏe | Pending tasks, disk I/O, SST count | Xóa vật lý toàn bộ dữ liệu nhạy cảm |
| Restore thành công | Test restore end-to-end | Mọi loại lỗi khác cũng được xử lý |

### 24.2. Không dựa vào một benchmark đơn lẻ

Benchmark “1 triệu write/giây” có thể:

- Chạy trên data fit-in-memory.
- Dùng write concern nhẹ.
- Không tính index phụ, compression hoặc replication.
- Đo latency trung bình thay vì p99.
- Chạy trước khi compaction backlog tích tụ.
- Không kiểm tra sau crash.

Để so với production, phải biết **mô hình tải, bản ghi, index, consistency, durability, concurrency và thời gian chạy đủ dài**. Tốc độ ghi cao dưới policy có thể mất dữ liệu không phải bằng chứng policy bền hơn cũng có tốc độ tương đương.

## 25. Tình huống 1: cache giá sản phẩm và nguồn đặt hàng

Kiến trúc:

~~~text
Product DB -> Price cache (Redis) -> Catalog API
                             |
                             v
                         UI hiển thị

Checkout API -> Product/Order source có thẩm quyền
~~~

Redis cache có thể không bật persistence vì dữ liệu có thể tái tạo. Nếu Redis restart làm mất cache, hệ có thể reload từ nguồn. Đây là lựa chọn hợp lý **nếu**:

- Cache miss được xử lý.
- Nguồn chịu được tải tăng khi warm cache.
- Checkout kiểm tra giá ở nguồn, không chốt hóa đơn chỉ theo cache cũ.
- Có giới hạn retry và cơ chế chống cache stampede.

**Kết luận đúng:** “Cache có thể mất mà không mất dữ liệu nghiệp vụ nguồn.”

**Kết luận sai:** “Redis không bền nên toàn bộ hệ đặt hàng có nguy cơ mất đơn tương ứng.” Độ bền đơn hàng phụ thuộc nguồn và quy trình ghi đơn, không thể suy trực tiếp từ cache.

## 26. Tình huống 2: số lượng tồn kho và ghi nhận ACK

Một kho còn một sản phẩm. Hai request cùng đặt hàng:

~~~text
Client A: reserve 1
Client B: reserve 1
~~~

Nếu cả hai đọc cache “available=1” rồi ghi vào hai vùng không có phân xử phù hợp, hệ có thể oversell dù mỗi write được lưu rất bền.

Cần phân biệt:

- **Atomicity/concurrency:** ai có quyền giữ sản phẩm cuối cùng?
- **Durability:** khi giữ hàng thành công, record có sống sót qua lỗi được yêu cầu không?
- **Consistency:** người khác nhìn trạng thái mới qua những đường đọc nào?
- **Recovery:** nếu nguồn bị hỏng hoặc xóa nhầm, giữ chỗ được phục hồi thế nào?

Một storage engine nhanh và bền không tự giải quyết invariant xuyên nhiều writer. Cần conditional write/transaction/quota allocation hoặc một cơ chế phân xử nghiệp vụ phù hợp.

## 27. Tình huống 3: migration sang engine khác

Một nhóm chuyển từ document store sang database dùng LSM và suy:

> LSM tối ưu write, nên có thể chuyển toàn bộ workload mà không đổi logic.

Nhưng ứng dụng hiện tại có:

- Truy vấn range theo nhiều field.
- Update document lớn với nhiều index phụ.
- Đọc một bản ghi bằng nhiều kiểu filter.
- Query trạng thái thiếu field.
- Giao dịch cập nhật nhiều document.

Engine mới có thể có **khả năng truy vấn, transaction boundary và tổ chức key khác**. Dù core write path tốt cho sequential writes, thiết kế access pattern không phù hợp có thể tăng read amplification, scan và compaction pressure.

Trước migration:

1. Ghi lại mọi query và bất biến.
2. Xác định mô hình key/index ở đích.
3. Kiểm tra write acknowledgment và transaction semantics.
4. Mô phỏng workload có update, delete, TTL, range và hotspot.
5. Lập kế hoạch backfill, dual-read/reconciliation và rollback.
6. Kiểm tra khả năng restore và failover ở đích.

**Không suy behavior từ tên cấu trúc vật lý trước khi xác định API và mô hình dữ liệu thật.**

## 28. Tình huống 4: ứng dụng báo “đã lưu” nhưng restart mất dữ liệu

Mô phỏng:

~~~text
1. App ghi key và nhận success.
2. App đọc lại key, thấy giá trị mới.
3. Host restart ngoài dự kiến.
4. Key biến mất.
~~~

Có một số giả thuyết khác nhau:

- Store chỉ giữ key trong RAM và không bật persistence.
- Persistence bật nhưng ACK không chờ mức sync cần cho failure mode đã xảy ra.
- Volume dữ liệu không được giữ qua restart/recreate.
- Dữ liệu ở replica cũ nhưng failover sang node thiếu dữ liệu.
- TTL/eviction đã xóa key.
- App đọc/ghi nhầm namespace, region hoặc cluster sau restart.
- Một job cleanup hoặc migration đã thay đổi key.

Không nên kết luận ngay “database lỗi” hoặc “WAL hỏng”. Hãy kiểm tra **namespace, storage policy, volume lifecycle, TTL/eviction, replication, audit và trạng thái ACK** theo thứ tự có bằng chứng.

## 29. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “NoSQL không có transaction.” | Mỗi sản phẩm có phạm vi atomicity/transaction riêng; cần đối chiếu API/version. |
| “Có WAL thì không bao giờ mất dữ liệu.” | WAL chỉ là một thành phần; cần sync, failure model, replica và backup. |
| “Ghi thành công nghĩa là đã ghi vào SSTable.” | ACK có thể trước flush/compaction; log hỗ trợ recovery. |
| “Compaction xong mới đọc được bản mới.” | Nhiều LSM đọc từ memtable/SSTable trước compaction. |
| “B-tree luôn đọc nhanh, LSM luôn ghi nhanh.” | Phụ thuộc workload, cấu hình, cache, disk, index và tải nền. |
| “Replica = backup.” | Replication có thể sao chép cả thao tác xóa nhầm/ghi sai. |
| “QUORUM = đã fsync mọi replica.” | Quorum nói về acknowledgment theo protocol; disk sync là câu hỏi khác. |
| “Mất một node không mất dữ liệu thì mất region cũng không.” | Failure domain và replication topology khác nhau. |
| “Redis luôn mất dữ liệu khi restart.” | Phụ thuộc RDB/AOF, volume và thời điểm lỗi. |
| “Bật AOF nghĩa là zero data loss.” | Cần xét appendfsync, power loss, replication và các loại lỗi khác. |
| “Strong read chứng minh write durable.” | Tính mới của read và khả năng sống sót qua crash khác nhau. |
| “TTL hết hạn nghĩa là byte đã được xóa.” | Expiration/visibility khác physical cleanup. |
| “Search đã ACK thì query thấy ngay.” | Cần xét refresh và read consistency. |
| “Managed service chắc dùng một engine cụ thể.” | Không đoán implementation kín nếu chưa có chứng cứ. |
| “Backup thành công thì chắc chắn phục hồi được.” | Phải thử restore, version/schema/khóa và RTO. |
| “Client timeout nghĩa là ghi thất bại.” | Ghi có thể commit nhưng ACK bị mất; cần idempotency. |
| “Quét nhanh trên dữ liệu nhỏ chứng minh phù hợp production.” | Cần workload, consistency, data size và thử lỗi đại diện. |

## 30. Quy trình ra quyết định cho một hệ NoSQL mới

### Bước 1 — Xác định điều cần bảo vệ

Phân loại dữ liệu:

- Cache có thể tái tạo.
- Session có thể mất trong phạm vi chấp nhận.
- Event telemetry có thể cần giữ đủ theo SLA.
- Đơn hàng, thanh toán hoặc sổ cái có invariant và RPO nghiêm ngặt.
- Tài liệu nhạy cảm có yêu cầu xóa và retention riêng.

Không chọn durability policy theo toàn hệ chỉ bằng một con số nếu các nhóm dữ liệu có rủi ro khác nhau.

### Bước 2 — Xác định cụ thể sản phẩm và storage engine

Ghi version/build, managed hay self-hosted, storage engine/cơ chế được nhà cung cấp công bố, replication topology, loại volume và địa điểm dữ liệu.

### Bước 3 — Định nghĩa write/read semantics

Với từng endpoint quan trọng, ghi:

~~~text
Write policy:
Read policy:
ACK nghĩa là gì:
Transaction/atomic boundary:
Idempotency behavior:
Recovery behavior on timeout:
~~~

### Bước 4 — Lần theo đường ghi

Tìm nơi ghi log/journal, memory buffering, flush/checkpoint, compaction và replication. Không cần giả định tầng mà service không công bố; với managed service, dùng API contract và metric phù hợp.

### Bước 5 — Viết failure matrix

Đánh giá process crash, host loss, disk loss, AZ/region outage, partition mạng và xóa nhầm. Ghi rõ mỗi tình huống được hệ chống chịu ở mức nào.

### Bước 6 — Chọn RPO/RTO và phương án backup

Quy định mục tiêu khôi phục, tần suất snapshot, log retention, cô lập quyền backup và cách restore.

### Bước 7 — Benchmark theo đúng policy

Đo p50/p95/p99 latency, throughput, compaction backlog, disk pressure, cache và replication lag dưới write concern/durability thật. Không so benchmark write-unsafe với write-durable rồi kết luận engine nào nhanh hơn.

### Bước 8 — Thử lỗi có kiểm soát

Chỉ trong môi trường được phép: process crash, replica failure, timeout, restore và reindex. Phân biệt ghi ACK, ghi ambiguous và retry để đánh giá đúng.

### Bước 9 — Xây observability và runbook

Theo dõi WAL/journal errors, disk pressure, replica lag, backup freshness, restore tests, query lag và data reconciliation. Có quy trình cho cả lỗi mất dữ liệu lẫn đọc cũ nhưng dữ liệu vẫn bền.

### Bước 10 — Ghi kết luận có phạm vi

Kết luận nên gắn với **version + configuration + operation + failure model + evidence**, không chỉ tên database hoặc một biểu đồ benchmark.

## 31. Bài tập thực hành

### Bài 1: Phân loại các tuyên bố

Cho các nhận định:

1. “DB dùng SSTable nên tất cả ghi được ACK đã nằm trên SSTable.”
2. “DB có ba replica nên không cần backup.”
3. “Đọc từ search không thấy bản mới có thể do index lag.”
4. “Để đánh giá mất điện, cần biết fsync policy và tầng storage.”

**Câu hỏi:** Nhận định nào hợp lý?

**Gợi ý:** (3) và (4) có cơ sở. (1) bỏ qua WAL/memtable/flush; (2) bỏ qua xóa nhầm và failure domain.

### Bài 2: Đường ghi LSM

Một engine ghi vào WAL và memtable, sau đó flush thành SSTable.

**Câu hỏi:** Vì sao dữ liệu có thể đọc được trước flush? Vì sao chưa flush không tự có nghĩa ghi sẽ mất sau crash?

**Gợi ý:** Reader có thể đọc memtable; WAL có thể hỗ trợ phục hồi sau crash theo điều kiện durability đã được cấu hình.

### Bài 3: Phân biệt ACK và replica lag

Primary version 12 đã được ghi theo policy. Secondary version 11 và search index version 10.

**Câu hỏi:** Đọc secondary thấy version 11 có chứng minh version 12 đã mất không?

**Gợi ý:** Không. Cần phân biệt lag của đường đọc với độ bền của ghi ở nguồn và đánh giá theo read/write concern.

### Bài 4: Redis và dữ liệu nguồn

Ứng dụng dùng Redis chỉ làm cache sản phẩm, RDB snapshot thưa và không có AOF. Redis restart mất một số key.

**Câu hỏi:** Có bắt buộc khôi phục từng key từ Redis backup không?

**Gợi ý:** Không nhất thiết nếu cache có thể tái tạo từ source authoritative, có cache-miss handling và nguồn chịu tải warming. Nhưng nếu Redis là nguồn duy nhất, policy này cần được đánh giá lại.

### Bài 5: Cassandra QUORUM

Một cluster có RF=3 và ứng dụng ghi với QUORUM.

**Câu hỏi:** Có thể từ đó kết luận hai replica đã fsync dữ liệu trên disk trước ACK không?

**Gợi ý:** Không. Phải kiểm tra commitlog sync, cơ chế ACK, topology và version. Quorum và local persistence là hai câu hỏi khác.

### Bài 6: Crash test với ACK bị mất

Client gửi CreateOrder, không nhận response vì timeout; database đã commit. Client retry bằng orderId mới.

**Câu hỏi:** Lỗi nào có thể xuất hiện và cách ngăn?

**Gợi ý:** Có thể tạo trùng đơn. Dùng idempotency key, unique/conditional write và tra cứu trạng thái request cũ trước khi thực hiện lại.

### Bài 7: TTL và byte vật lý

Một session có TTL hết lúc 10:00; query 10:01 không thấy. Disk usage vẫn chưa giảm.

**Câu hỏi:** Có chắc engine xóa sai không?

**Gợi ý:** Không. Expiration/visibility và physical cleanup có thể khác thời điểm; cần xem cơ chế TTL, tombstone, compaction và eviction của sản phẩm.

### Bài 8: Backup và RPO

Hệ chỉ tạo snapshot mỗi 12 giờ, không có log/PITR bổ sung, nhưng nhóm sản phẩm đòi RPO tối đa 5 phút khi mất toàn bộ data volume.

**Câu hỏi:** Có phù hợp không?

**Gợi ý:** Không. Với nguồn khôi phục duy nhất là snapshot 12 giờ/lần, có thể mất đến gần 12 giờ thay đổi; cần một đường bảo vệ bổ sung và thử restore.

### Bài 9: Benchmark không tương đương

Hệ A chạy benchmark với write acknowledgment từ một node và không yêu cầu sync; hệ B ghi majority và yêu cầu journal sync. Hệ A có throughput gấp đôi.

**Câu hỏi:** Đã chứng minh engine A tốt hơn cho thanh toán chưa?

**Gợi ý:** Chưa. Hai benchmark không cùng hợp đồng độ bền/nhất quán. Cần chuẩn hóa failure model, write policy, workload và latency tails.

### Bài 10: Reindex sau restore

Tài liệu A123 được tạo lúc 09:00, xóa lúc 10:00, nhưng backup 09:30 được restore và search index được build lại.

**Câu hỏi:** Rủi ro nào xuất hiện?

**Gợi ý:** A123 có thể hồi sinh nếu các delete sau mốc backup không được replay. Cần log/tombstone, restore workflow và xác minh trước khi phục vụ.

### Bài 11: MongoDB write concern

Một app dùng write concern khác nhau giữa endpoint tạo đơn và endpoint analytics. Nhóm vận hành chỉ xem cấu hình mặc định replica set.

**Câu hỏi:** Vì sao chưa đủ chứng minh độ bền của CreateOrder?

**Gợi ý:** Từng operation/driver có thể override write concern. Cần kiểm tra call path, transaction scope, journal, deployment và test đúng endpoint.

### Bài 12: Managed service opaque

Nhóm muốn khẳng định DynamoDB chắc chắn dùng SSTable dạng X và vì thế có độ trễ compaction Y.

**Câu hỏi:** Có nên viết kết luận ấy vào tài liệu kiến trúc?

**Gợi ý:** Không nếu implementation không được công bố/kiểm chứng. Dựa vào API contract, tính năng và metric mà dịch vụ hỗ trợ; chỉ ghi giả thuyết nội bộ khi có bằng chứng phù hợp.

### Bài 13: Lập failure matrix

Hãy chọn một hệ dùng cho đơn hàng và điền:

| Lỗi | Trạng thái ghi đã ACK | Có thể đọc? | Có thể phục hồi? | Bằng chứng cần có |
| --- | --- | --- | --- | --- |
| Database process crash | ? | ? | ? | ? |
| Một replica chết | ? | ? | ? | ? |
| Mất availability zone | ? | ? | ? | ? |
| Xóa nhầm collection | ? | ? | ? | ? |
| Restore từ backup cũ | ? | ? | ? | ? |

**Gợi ý:** Không điền theo “kiến thức chung NoSQL”. Phải dựa trên topology, write policy, storage config, backup/PITR và thử nghiệm có kiểm soát của deployment đã chọn.

## 32. Kết luận

**Không thể suy luận độ bền, hiệu năng hoặc hành vi phục hồi của một NoSQL database chỉ từ tên mô hình dữ liệu.** Cần đối chiếu **storage engine thật, đường ghi, WAL/journal, memory buffering, flush/checkpoint, compaction, replica topology, write/read policy, thiết bị lưu trữ và khả năng backup/restore**.

Họ LSM giúp hiểu memtable, SSTable, tombstone và compaction; họ B-tree giúp hiểu page, cache và checkpoint. Nhưng những cấu trúc này chỉ là **một phần** của hệ thống. Cassandra, MongoDB, Redis, RocksDB, DynamoDB và Elasticsearch có API, phạm vi ghi, replication, persistence và cách vận hành khác nhau; một số managed service không công bố chi tiết on-disk implementation.

Trước mỗi kết luận “ghi này an toàn”, “xóa đã hoàn tất” hay “engine này nhanh hơn”, hãy chỉ rõ **hệ và phiên bản nào, cấu hình nào, thao tác nào, lỗi nào, bằng chứng nào**. Một thiết kế tốt không dừng ở lời giải thích cơ chế lưu trữ mà còn biết **kiểm chứng ACK, quan sát phục hồi, thử backup/restore và bảo vệ bất biến nghiệp vụ** trong failure model thực tế.
