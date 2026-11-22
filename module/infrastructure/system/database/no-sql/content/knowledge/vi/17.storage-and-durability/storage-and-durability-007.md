# Compaction, garbage collection và ảnh hưởng đến tải nền

Một cụm NoSQL có thể ghi thành công hàng chục nghìn sự kiện mỗi giây nhưng sau vài ngày lại xuất hiện những dấu hiệu khó hiểu: số file dữ liệu tăng, dung lượng đĩa không giảm sau khi TTL hết hạn, p99 của API ghi đột ngột tăng, một số thao tác đọc phải quét quá nhiều phiên bản cũ, hoặc hệ thống chủ động làm chậm ghi dù CPU còn rảnh. Nguyên nhân có thể không nằm ở câu truy vấn mà ở **công việc lưu trữ chạy nền**.

Hai khái niệm quan trọng trong chương **Lưu trữ và độ bền** của **Database No SQL** là:

- **Compaction:** tổ chức lại dữ liệu lưu trữ, thường bằng cách hợp nhất những file hoặc phiên bản dữ liệu để cải thiện cách đọc, giảm lượng dữ liệu trùng/cũ, kiểm soát cấu trúc lưu trữ và thu hồi những phần có thể bỏ.
- **Garbage collection (GC) ở tầng lưu trữ:** nhận diện và giải phóng đối tượng, phiên bản, block, file hoặc metadata không còn cần thiết theo các quy tắc an toàn của hệ thống. Nó khác với **JVM garbage collection**, vốn thu hồi object không còn được tham chiếu trong heap Java.

Compaction và storage GC có thể liên quan chặt chẽ nhưng **không đồng nghĩa**. Một lượt compaction có thể viết lại hàng trăm GiB mà không thu hồi được bao nhiêu byte; một cơ chế GC kiểu xóa file không còn tham chiếu có thể giải phóng dung lượng mà không cần trộn các bản ghi như compaction. Mỗi cơ chế đều có chi phí CPU, bộ nhớ, I/O, mạng và tác động lên độ trễ của request người dùng.

Mục tiêu bài học: hiểu **vì sao những công việc này tồn tại**, chúng tương tác thế nào với tính bền vững của dữ liệu và bản sao, chúng gây ra những loại tải nền nào, đo bằng chỉ số gì, và thiết kế/kiểm thử chúng ra sao để đạt cả **throughput, p99, headroom và tính đúng**.

> **Quy ước:** Ví dụ Cassandra, HBase, RocksDB, MongoDB, Redis, DynamoDB và hệ search chỉ minh họa các kiến trúc thường gặp. Tên metric, chi tiết chiến lược, giới hạn và khả năng cấu hình phụ thuộc sản phẩm/phiên bản. Tất cả con số hiệu năng trong bài là **giả định để suy luận**, không phải benchmark của một nhà cung cấp.

## 1. Tại sao dữ liệu đã bị sửa hoặc xóa vẫn còn trên đĩa?

Hãy xét khóa **sensor:42** với các phiên bản theo thời gian:

~~~~text
10:00  PUT sensor:42 = 22.5
10:01  PUT sensor:42 = 23.0
10:02  PUT sensor:42 = 23.4
10:03  DELETE sensor:42
~~~~

Ở mô hình ghi trực tiếp tại chỗ, ta có thể tưởng tượng chỉ cần ghi đè giá trị cuối. Nhưng nhiều NoSQL tối ưu ghi theo cách **append hoặc tạo phiên bản mới**, để ghi tuần tự, phục hồi crash và duy trì dữ liệu phân tán.

Khi đó các giá trị cũ hoặc dấu xóa có thể nằm ở những nơi khác nhau:

~~~~text
Memtable:       sensor:42 -> tombstone
SSTable mới:    sensor:42 -> 23.4
SSTable giữa:   sensor:42 -> 23.0
SSTable cũ:     sensor:42 -> 22.5
~~~~

Đọc khóa này phải áp dụng **thứ tự phiên bản và quy tắc xóa**, không được tùy tiện trả giá trị bất kỳ. Compaction giúp dồn nhiều phiên bản vào tổ chức lưu trữ thuận tiện hơn; GC giúp loại những phần **chắc chắn không cần cho các thao tác đọc/khôi phục hợp lệ**.

### 1.1. Dữ liệu có thể “chết” theo nhiều nghĩa

| Trạng thái | Ví dụ | Có thể xóa vật lý ngay không? |
| --- | --- | --- |
| Giá trị bị một giá trị mới thay thế | sensor:42 = 22.5 trước khi thành 23.4 | Chỉ khi không còn reader/snapshot cần phiên bản cũ |
| Khóa bị DELETE | sensor:42 có tombstone | Phải xét an toàn bản sao, thứ tự và các bản cũ còn tồn tại |
| Bản ghi hết TTL | Sự kiện quá hạn 30 ngày | Chỉ khi policy, snapshot và cơ chế engine cho phép |
| File compaction đầu vào | SSTable đã có output thay thế | Chỉ sau khi output/metadata được commit và không còn tham chiếu |
| Block không còn được index tham chiếu | Blob cũ sau khi đổi giá trị | GC có thể thu hồi sau khi chứng minh không còn reference |
| WAL segment đã checkpoint | Log cũ của những ghi đã flush an toàn | Theo cơ chế durability/replication/backup của engine |
| Snapshot/backup hết hạn | Bản lưu trữ không còn cần thiết | Sau khi chính sách giữ dữ liệu và ràng buộc khôi phục cho phép |

**Dữ liệu không còn hiện trong truy vấn thông thường không chứng minh rằng mọi byte của nó đã không còn cần thiết.** Một transaction cũ, một replica chưa bắt kịp hoặc một snapshot còn sống có thể cần thông tin đó.

### 1.2. Phân biệt các lớp garbage collection

Trong một ứng dụng Java dùng NoSQL, thuật ngữ GC có ít nhất ba ngữ cảnh:

1. **JVM GC:** thu hồi Java object không còn reachable trong heap của service hoặc database JVM; biểu hiện ở pause time, allocation rate, heap và CPU.
2. **Storage GC:** giải phóng file, block, record version hoặc segment không còn reachable theo metadata/durability của database.
3. **Application-level cleanup:** job xóa dữ liệu theo retention, tài khoản không hoạt động, session hết hạn hoặc bản dẫn xuất không còn cần.

Chúng có thể ảnh hưởng nhau nhưng không phải một thao tác. Ví dụ một job compaction tạo nhiều object tạm, gây áp lực lên **JVM GC**; tuy nhiên **JVM GC không tự giải phóng SSTable cũ**. Ngược lại, một Redis key hết TTL không đồng nghĩa Java service đang dùng Redis vừa chạy garbage collector.

## 2. Đường ghi và khả năng chịu crash trong một LSM-based NoSQL

Để hiểu compaction, cần nhìn đường đi của một write trong mô hình **Log-Structured Merge-tree (LSM)**:

~~~~mermaid
flowchart TD
    W["Client write"] --> WAL["Commit log / WAL"]
    W --> MEM["Memtable (in memory)"]
    WAL --> ACK["Write acknowledgment theo cấu hình"]
    MEM --> FLUSH["Flush"]
    FLUSH --> L0["SSTable ở level / tier mới"]
    L0 --> COMPACT["Background compaction"]
    OLD["SSTable cũ"] --> COMPACT
    COMPACT --> OUT["File/level đã hợp nhất"]
    OUT --> META["Commit metadata / manifest"]
    META --> GC["GC file đầu vào khi an toàn"]
~~~~

Các bước và thứ tự ACK phụ thuộc engine, write consistency và độ bền đã cấu hình. **Không được mặc định write success luôn đồng nghĩa fsync đã hoàn thành trên mọi replica**.

### 2.1. Commit log / WAL để làm gì?

**Write-ahead log (WAL)** hoặc commit log ghi lại ý định/thao tác để có thể phục hồi trạng thái sau khi mất bộ nhớ. Trong một triển khai điển hình:

1. Request ghi được kiểm tra và chấp nhận.
2. Log và vùng nhớ ghi được cập nhật theo ranh giới đồng bộ/bền vững của engine.
3. Client nhận ACK theo chính sách ghi.
4. Memtable được flush thành file lưu trữ.
5. Khi dữ liệu đã được checkpoint/flush an toàn, những log segment tương ứng có thể đủ điều kiện được thu hồi.

**Compaction không thay thế WAL.** Mục tiêu compaction là tổ chức và tối ưu dữ liệu sau ghi; WAL phục vụ phục hồi/thứ tự ghi trước khi dữ liệu được lưu bền ở cấu trúc chính.

### 2.2. Memtable flush không phải compaction

- **Flush:** chuyển dữ liệu từ memtable sang file lưu trữ. Có thể tạo nhiều SSTable mới dù chưa loại mọi phiên bản cũ.
- **Compaction:** đọc một hoặc nhiều file đã tồn tại, hợp nhất/tổ chức lại, tạo output file.
- **Garbage collection:** xác nhận và giải phóng những file/block/version không còn cần.

Mỗi hành động có thể làm I/O tăng. Nếu chỉ có metric “background disk writes” mà không tách flush, compaction, WAL và repair, ta khó biết nguyên nhân.

### 2.3. Tính bền vững của compaction sau crash

Một compaction an toàn cần tránh tình huống:

~~~~text
Đọc file cũ A và B
Đang ghi file mới C
Tiến trình crash giữa chừng
Khởi động lại
~~~~

Nếu xóa A/B trước khi C được ghi và công bố bền vững, dữ liệu có thể mất. Một thiết kế engine thường có cơ chế tương đương:

1. Viết output C vào file mới.
2. Hoàn thiện dữ liệu, checksum và trạng thái bền vững theo hợp đồng.
3. **Atomically install/publish** danh sách file mới qua manifest/metadata.
4. Chỉ giải phóng A/B khi không còn được tập metadata hiện hành, reader hoặc snapshot giữ.

Sau crash, engine phải có cách xác định tập file hợp lệ và dọn **file output dở dang**. Đây là lý do compaction gắn với **độ bền** chứ không chỉ tối ưu hiệu năng.

> Cơ chế atomic install, journaling, manifest và fsync cụ thể khác nhau theo engine. Ở đây trình bày yêu cầu đúng đắn tổng quát, không phải thuật toán nội bộ của một database cụ thể.

## 3. Compaction cải thiện điều gì ngoài thu hồi dung lượng?

Một engine có thể compaction ngay cả khi **không có bản ghi nào hết hạn**:

- Giảm số file phải tra cứu cho một point lookup.
- Đưa những vùng key liên quan vào tổ chức file thuận tiện hơn.
- Hợp nhất nhiều bản ghi đã cập nhật cùng khóa.
- Tái tổ chức dữ liệu theo level/tier để kiểm soát read amplification.
- Tạo lại bảng chỉ mục phụ/bloom filter/metadata theo cơ chế của engine.
- Giảm lượng phiên bản cũ và tombstone khi đủ điều kiện bỏ.

### 3.1. Read amplification

**Read amplification** diễn tả mức công việc lưu trữ cần làm để phục vụ một lượng dữ liệu logic được yêu cầu. Nó có nhiều cách định nghĩa theo engine.

Ví dụ một point lookup cần kiểm tra 12 SSTable trước khi tìm thấy phiên bản mới nhất, so với 2 SSTable sau compaction. Mặc dù cả hai truy vấn đều trả **một value**, lượng file/metadata/block phải chạm khác nhau.

Với range scan, read amplification còn có thể đến từ:

- Phiên bản trùng khóa ở nhiều file.
- Tombstone và bản ghi hết TTL.
- Các file có khoảng key chồng lấp.
- Nén và đọc block lớn hơn phần dữ liệu cần trả.

Chỉ số có ích: **files/tables touched per read, bytes scanned / bytes returned, cache miss, tombstone scanned** và p99.

### 3.2. Write amplification

**Write amplification (WA)** là tỷ số giữa byte ghi vật lý được quy cho workload với byte ghi logic của người dùng, theo phạm vi tính được nêu rõ.

\[
WA =
\frac{B_{\text{physical writes attributable to workload}}}
{B_{\text{logical application writes}}}
\]

Compaction thường góp phần quan trọng vì dữ liệu còn sống có thể bị ghi lại nhiều lần khi đi qua các level. Tuy nhiên tổng WA có thể còn gồm WAL, index, replica và lớp device.

Ví dụ minh họa trong một kỳ:

~~~~text
Logical application writes:          100 GiB
WAL physical writes:                 100 GiB
Flush output (sau nén):               70 GiB
Compaction output writes:            280 GiB
Index/metadata physical writes:       30 GiB
                                     -------
Tổng các thành phần đếm:             480 GiB
~~~~

Theo phạm vi đã chọn, WA khoảng **480/100 = 4,8**. Nhưng nếu một số counter đã tính trùng WAL/index hoặc một metric đo tại đĩa khác với tầng engine, không thể cộng máy móc. Phải xác minh **từng byte counter đếm gì**, và không so raw input với compressed output mà quên nêu khác biệt.

### 3.3. Space amplification

**Space amplification** diễn tả lượng không gian lưu trữ so với dữ liệu logic hợp lệ:

\[
SA =
\frac{B_{\text{physical storage occupied}}}
{B_{\text{logical live data}}}
\]

Nếu 300 GiB dữ liệu live cần 600 GiB file, index và bản cũ tại một node, SA = **2** theo phạm vi local đó. Nếu tính ba replica và snapshot ở cấp cluster, tử số thay đổi. Hãy giữ **cùng ranh giới đo** khi so kết quả.

Ba mục tiêu có quan hệ đánh đổi: giảm read amplification, write amplification và space amplification **đồng thời** đến mức thấp nhất thường không khả thi với cùng workload và storage engine.

## 4. Các chiến lược compaction thường gặp

Chiến lược compaction xác định **khi nào chọn file nào để hợp nhất, chọn bao nhiêu file và tổ chức output ở đâu**. Tên chính xác khác theo sản phẩm; dưới đây là mô hình khái niệm.

### 4.1. Size-tiered compaction

**Size-tiered** gom những file có kích thước tương đương rồi hợp nhất thành file lớn hơn.

~~~~text
Input:  4 file nhỏ ~100 MB
         ↓ merge
Output: 1 file ~400 MB (trừ obsolete data)
~~~~

Lợi ích:

- Có thể ghi tuần tự hiệu quả, không phải liên tục đụng mọi level.
- Thường hợp lý với workload ingest lớn và ghi append.

Đánh đổi:

- Nhiều file/nhóm file có khoảng key chồng lấp → point/range read có thể cần kiểm tra nhiều nơi.
- Khi gom file lớn, có thể cần **dung lượng tạm cao**.
- Dữ liệu cũ và tombstone có thể cần đợi vòng hợp nhất phù hợp mới được dọn.

### 4.2. Leveled compaction

**Leveled** tổ chức file theo các level với quy tắc kích thước và mức chồng lấp, thường tối ưu để giảm số file có thể chứa một key trong từng level.

~~~~text
L0: nhiều file mới, có thể overlap
L1: các range key được tổ chức
L2: dung lượng lớn hơn, range key có kiểm soát
L3: ...
~~~~

Lợi ích:

- Có thể giảm read amplification, hữu ích cho workload point lookup và range scan nặng.
- Kiểm soát số file liên quan tới một truy vấn ở những level được tổ chức.

Đánh đổi:

- Có thể tăng write amplification vì giá trị phải được merge/di chuyển qua nhiều level.
- Tác vụ compaction chạy đều với áp lực ghi đáng kể.
- Khi backlog không theo kịp, write stall hoặc độ trễ đọc có thể tăng.

Không khẳng định leveled luôn ghi nhiều hơn size-tiered trong mọi cấu hình; kết quả phụ thuộc level size, fanout, compression và workload.

### 4.3. Time-window compaction

Với dữ liệu time-series có thời hạn tương đối đồng đều, chiến lược theo **cửa sổ thời gian** có thể hợp nhất chủ yếu trong một nhóm file của cùng window, rồi giảm việc ghi lại dữ liệu lịch sử đã ổn định.

~~~~text
Window ngày D:     file A + B + C -> file D-stable
Window ngày D+1:   file E + F -> file D+1-stable
Window ngày D+2:   dữ liệu đang được ghi
~~~~

Ưu điểm tiềm năng:

- Giảm mức độ trộn dữ liệu rất cũ với dữ liệu mới.
- Phù hợp với TTL đồng đều theo tuổi dữ liệu, giảm công việc xử lý những window đã đóng.
- Có thể giúp dọn file theo lô khi toàn bộ dữ liệu trong nhóm đủ điều kiện.

Nhưng dễ sai khi:

- Có **late writes** cập nhật window cũ thường xuyên.
- Một file chứa các bản ghi TTL khác nhau đáng kể.
- Dữ liệu được sửa/ghi đè nhiều lần theo khóa cũ.
- Cửa sổ quá lớn khiến mỗi lượt dọn rất nặng; quá nhỏ khiến có quá nhiều file.

Đừng mặc định time-window compaction tương đương tính năng **drop partition** của mọi NoSQL. Vẫn phải xem điều kiện xóa và metadata của engine.

### 4.4. Universal/other compaction và lựa chọn

Một số LSM engine cung cấp **universal compaction** hoặc các biến thể tối ưu ghi, latency hay space. Không nên suy luận từ một tên gọi rằng nó luôn tốt nhất.

| Workload chính | Điểm ưu tiên | Vấn đề phải đo |
| --- | --- | --- |
| Ghi append rất lớn | Write throughput, write amplification | Backlog, read amplification, file overlap |
| Point lookup nhiều | Read latency và số file phải chạm | Write amplification, CPU/IO nền |
| Scan theo range | Đọc tuần tự, bản ghi sống được sắp gần nhau | Tombstone, số file, block read |
| Time-series TTL đồng đều | Nhóm file cùng thời hạn, dễ thu hồi | Late data, TTL mix, fan-out theo thời gian |
| Update/delete nhiều | Loại version cũ, giảm scan | Compaction I/O, an toàn tombstone |
| Đĩa rất đắt hoặc hạn chế | Space amplification và file tạm | Compaction aggressiveness, p99, stall |

**Chọn chiến lược bằng kết quả workload thật** và tài liệu sản phẩm, không sao chép một lựa chọn từ hệ khác.

## 5. Garbage collection ở tầng lưu trữ

Compaction xử lý tổ chức dữ liệu và phiên bản; **storage GC** tập trung vào việc xác định thứ gì không còn được tham chiếu hoặc không còn cần theo hợp đồng dữ liệu.

### 5.1. Reachability: còn ai tham chiếu dữ liệu?

Một file có thể không còn nằm trong bộ file hiện hành nhưng vẫn được giữ bởi:

- Snapshot.
- Transaction/read snapshot chưa đóng.
- Iterator đang quét dữ liệu.
- Backup/recovery checkpoint.
- Replica hoặc thao tác migration cần khôi phục.
- Manifest/metadata chưa commit hoàn tất.

Ví dụ:

~~~~text
Current manifest --> File C (sau compaction)
Old snapshot -----> File A, File B
Reader active ----> File B
~~~~

**File A/B chỉ được xóa khi các chính sách cho phép và không còn reference cần bảo vệ.** Một lượt compaction đã tạo C không đủ để kết luận A/B có thể bị unlink ngay.

### 5.2. Mark-and-sweep ở hệ lưu object/block

Một cách GC khái niệm:

1. Xác định tập **root references** còn hợp lệ từ manifest, snapshot, version metadata.
2. **Mark** những object/block còn reachable.
3. Chờ hoặc kiểm tra an toàn theo cơ chế nhất quán metadata.
4. **Sweep** những object không được tham chiếu và đủ điều kiện xóa.
5. Ghi lại checkpoint và khả năng retry idempotent.

~~~~mermaid
flowchart TD
    ROOT["Current manifest + snapshots"] --> MARK["Mark reachable objects"]
    ALL["Danh sách object hiện có"] --> DIFF["Reachable vs all"]
    MARK --> DIFF
    DIFF --> SAFE{"Đủ điều kiện xóa?"}
    SAFE -->|Có| DELETE["Delete garbage objects"]
    SAFE -->|Chưa| KEEP["Giữ tới chu kỳ sau"]
~~~~

Không được sweep chỉ dựa trên **một lần liệt kê có thể thiếu** nếu hệ thống có ghi đồng thời hoặc metadata cập nhật trễ. Thuật toán GC phải có ranh giới snapshot, generation/epoch, thời gian đệm hoặc cơ chế tương đương để tránh xóa nhầm dữ liệu mới đang được tham chiếu.

### 5.3. Reference counting, epoch và snapshot pinning

Một số engine dùng:

- **Reference count** để biết còn bao nhiêu reader/snapshot giữ file.
- **Epoch/generation** để trì hoãn giải phóng cho tới khi các reader cũ kết thúc.
- **Manifest snapshot** để đóng băng bộ file hợp lệ của một read snapshot.
- **Lease** hoặc checkpoint để phối hợp khi đối tượng nằm ở remote storage.

Mỗi cách có đánh đổi. Reference count sai hoặc bị bỏ sót khi crash có thể gây leak hoặc xóa nhầm; epoch cũ không kết thúc có thể giữ file quá lâu. Khi điều tra đĩa tăng, nên hỏi **file cũ bị giữ bởi ai**, không chỉ hỏi compaction đã chạy bao nhiêu lượt.

## 6. Tombstone, TTL, replica và điều kiện xóa an toàn

Một trong những điểm khó của GC trong NoSQL phân tán là **an toàn trước replica chậm**.

### 6.1. Tại sao cần tombstone?

Giả sử:

~~~~text
Replica A: DELETE key=K đã được áp dụng
Replica B: offline, còn key=K với giá trị cũ
~~~~

Nếu A dọn sạch thông tin xóa quá sớm, B có thể mang giá trị cũ trở lại khi tái đồng bộ theo một số giao thức. Đây là nguy cơ **deleted data resurrection** hay **zombie data**.

Tombstone giúp biểu thị rằng dữ liệu đã bị xóa theo một version/timestamp/causal order cụ thể. Nhưng tombstone chỉ được dọn khi engine có đủ điều kiện an toàn theo quy tắc của nó.

### 6.2. Điều kiện GC tombstone không chỉ dựa vào thời gian

Trong Cassandra và những kiến trúc liên quan, thời gian giữ dấu xóa cùng tình trạng **repair và replica** ảnh hưởng đến thời điểm có thể bỏ tombstone. Nếu replica có thể bị offline vượt quá những giả định về quá trình sửa chữa, dữ liệu xóa có thể hồi sinh.

**Không tự ý giảm gc_grace_seconds hoặc can thiệp tham số tương tự** chỉ vì thấy tombstone chiếm đĩa. Cần hiểu cách engine xử lý dấu xóa, trạng thái node đã bỏ lỡ delete, lịch repair, topology và phiên bản.

Tương tự, với hệ dựa trên snapshot/MVCC, việc một row đã bị xóa ở phiên bản mới không có nghĩa các transaction/snapshot cũ đã kết thúc.

### 6.3. TTL hết hạn có luôn giải phóng dung lượng không?

Không. Có ít nhất ba mốc:

~~~~text
expiresAt đạt deadline
  -> Query không còn trả dữ liệu theo chính sách
  -> Background cleanup/compaction xử lý đủ điều kiện
  -> Byte/file được tái sử dụng hoặc giải phóng
~~~~

Một số dịch vụ xóa nền không bảo đảm đúng thời điểm deadline; ứng dụng cần **lọc hạn sử dụng** ở đường đọc nếu hợp đồng buộc không bao giờ trả dữ liệu hết hạn.

### 6.4. Data lifecycle và legal hold

Dữ liệu có yêu cầu xóa theo pháp lý và dữ liệu cần giữ để phục hồi/điều tra có thể có **chính sách khác nhau**. GC an toàn cần biết:

- Deadline không được phục vụ dữ liệu cho user.
- Deadline xóa vật lý theo yêu cầu và các ngoại lệ được phép.
- Snapshot/backup retention và yêu cầu phục hồi.
- Read model, search index, cache, event log có bản sao hay không.
- Dữ liệu có **legal hold** cần bảo vệ không.

Không chỉ chạy compaction rồi coi mọi bản sao đã bị xóa.

## 7. MVCC và GC của các phiên bản cũ

Một số NoSQL/document engine sử dụng **multi-version concurrency control (MVCC)** hoặc cơ chế snapshot tương đương. Các transaction đọc có thể cần nhìn thấy phiên bản cũ trong khi transaction ghi đã commit bản mới.

Ví dụ:

~~~~text
T0: Reader R1 bắt đầu snapshot ở version 10
T1: Writer cập nhật K từ v10 sang v11
T2: Reader R2 thấy v11
T3: Reader R1 vẫn có quyền đọc v10
T4: Reader R1 kết thúc
~~~~

Nếu GC loại v10 trước T4 mà không có cách phục vụ snapshot cũ đúng đắn, R1 có thể đọc sai hoặc lỗi. Do đó, **oldest active snapshot/read timestamp** có thể giới hạn việc dọn phiên bản cũ.

### 7.1. Long-running transaction làm GC chậm

Một transaction hoặc iterator đọc kéo dài hàng giờ có thể giữ các phiên bản/file mà writer mới đã thay thế. Điều này ảnh hưởng:

- Storage amplification.
- Dung lượng cần giữ cho snapshot.
- Khả năng compaction thu hồi byte.
- p99 do hệ thống phải quản lý nhiều phiên bản.

Không nhất thiết phải kill mọi reader dài, nhưng cần giới hạn phù hợp, timeout/lease, pagination và giám sát **oldest pinned snapshot**. Cơ chế cụ thể phụ thuộc engine.

## 8. Garbage collection của Java khác storage GC

Trong một dịch vụ NoSQL triển khai bằng Java hoặc một ứng dụng Java sử dụng NoSQL, **JVM GC** có thể làm dừng hoặc trì hoãn những thread phục vụ request.

Ví dụ:

~~~~text
Compaction thread tạo nhiều buffer/object tạm
    -> Allocation rate tăng
    -> Heap hoặc GC pressure tăng
    -> Pause / CPU GC tăng
    -> API p99 tăng dù disk I/O chưa đầy
~~~~

Một số engine dùng bộ nhớ ngoài heap, native code hoặc memory-mapped file nên mối liên hệ giữa compaction và JVM heap khác nhau. Không mặc định mọi NoSQL đều chạy trên JVM.

Khi phân tích metric:

| Chỉ số | Thuộc loại | Ý nghĩa |
| --- | --- | --- |
| JVM pause p99, GC CPU, allocation rate | JVM GC | Thu hồi Java object, ảnh hưởng pause/CPU |
| Compaction pending bytes, SSTables merged | Storage compaction | Công việc hợp nhất dữ liệu lưu trữ |
| Expired/deleted object cleanup | Storage/application GC | Loại dữ liệu hết hiệu lực theo chính sách |
| Disk/file reusable bytes | Storage reclaim | Dung lượng được giải phóng hoặc tái sử dụng |

Nếu p99 tăng khi compaction chạy, nên đo cả **disk I/O contention và JVM GC** để tìm nguyên nhân, không chỉ giả định một loại.

## 9. Tác vụ nền cạnh tranh những tài nguyên nào?

~~~~text
                         MỘT NODE
                +------------------------+
Client reads -->|                        |
Client writes ->| CPU / RAM / Disk I/O   |--> p50, p95, p99
Compaction ---->| Network / Cache /      |
Storage GC ---->| Disk free space        |
Repair -------->|                        |
Backup -------->|                        |
                +------------------------+
~~~~

### 9.1. Đĩa: bandwidth, IOPS và queue depth

Compaction thường đọc và ghi dữ liệu lớn. Nếu disk đã gần giới hạn, request nhỏ có thể phải chờ:

- **IOPS:** số thao tác I/O mỗi giây.
- **Throughput:** MiB/s hoặc GiB/s.
- **Latency:** thời gian hoàn thành một I/O.
- **Queue depth:** số I/O đang chờ.
- **Volume quota/credits:** giới hạn theo loại cloud volume.

CPU thấp không bảo đảm node có đủ khả năng đọc/ghi. Disk queue dài có thể làm request p99 xấu ngay cả khi CPU chỉ 40%.

### 9.2. CPU và nén dữ liệu

Compaction có thể giải nén file đầu vào, so sánh khóa và nén file đầu ra. Compression ratio tốt giảm dung lượng và I/O nhưng thường tăng chi phí CPU. Cần đo:

- CPU của compaction và CPU phục vụ client.
- Compression/decompression throughput.
- GC pause nếu sử dụng JVM.
- p99 request khi thay thuật toán nén.

Không đổi compression và compaction strategy đồng thời rồi kết luận một trong hai làm p99 thay đổi.

### 9.3. Bộ nhớ và page cache

Compaction buffer, Bloom filter/index cache, memtable và page cache cạnh tranh RAM. Một đợt scan lớn có thể đẩy những block truy vấn nóng khỏi cache, khiến request sau đó phải đọc đĩa nhiều hơn.

Vì vậy, tác động không nhất thiết kết thúc ngay khi compaction dừng: **cache warm-up** sau đó có thể khiến p99 tiếp tục cao.

### 9.4. Network và replica

Repair/rebalance có thể tạo traffic lớn trong khi compaction đang hoạt động. Nếu node vừa phục vụ replica reads vừa gửi dữ liệu tới node khác, network contention có thể làm cả read và write path chậm.

**Compaction I/O, repair traffic và foreground traffic phải được nhìn cùng trục thời gian** để tránh chẩn đoán nhầm.

### 9.5. Dung lượng tạm trong lúc compaction

Engine có thể cần **ghi file output trước khi xóa file input**. Nếu 600 GiB input chứa 100 GiB obsolete data, output có thể còn 500 GiB. Không có nghĩa luôn cần thêm đúng 500 GiB cùng lúc, vì compaction có thể tiến hành theo nhóm file. Tuy nhiên **đĩa gần đầy là một rủi ro lớn cho chính quá trình dọn**.

Một khung lập kế hoạch:

\[
H_{\text{required}} =
H_{\text{ingest burst}}+
H_{\text{compaction peak}}+
H_{\text{recovery}}+
H_{\text{safety}}
\]

Đây là khung các loại nhu cầu, không phải tổng chính xác ở mọi engine; phải đo đỉnh đồng thời trong thử nghiệm.

## 10. Compaction debt và hiện tượng write stall

**Compaction debt** là lượng công việc hợp nhất chưa được thực hiện theo cơ chế đánh giá của engine. Nếu mỗi ngày phát sinh công việc nhiều hơn số xử lý, backlog tăng.

\[
G_{\text{backlog}}=
R_{\text{new work}}-R_{\text{completed work}}
\]

Ví dụ:

~~~~text
Compaction work created:   450 GiB/ngày
Compaction completed:      300 GiB/ngày
Backlog growth:            150 GiB/ngày
After 7 days:            1.050 GiB backlog tăng thêm
~~~~

Trong những LSM engine, khi số file hoặc pending bytes quá lớn, hệ thống có thể **trì hoãn hoặc chặn ghi** để tránh tình trạng mất kiểm soát. Tên ngưỡng như slowdown/stop trigger tùy sản phẩm.

### 10.1. Vòng xoáy khi dọn không kịp

~~~~mermaid
flowchart TD
    IN["Ingest lớn"] --> FILES["Số file/phiên bản mới tăng"]
    FILES --> BACKLOG["Compaction backlog tăng"]
    BACKLOG --> READ["Read amplification / disk usage tăng"]
    READ --> LAT["p99 tăng"]
    BACKLOG --> STALL["Write throttling / stall"]
    STALL --> RETRY["Client timeout và retry"]
    RETRY --> IN
~~~~

Retry không kiểm soát có thể tạo thêm tải, dù thao tác logic ban đầu đã thành công hoặc đang chờ. Cần timeout/backoff/idempotency theo hợp đồng ứng dụng để không biến một đợt bảo trì chậm thành bão request.

### 10.2. Vì sao giảm compaction để cải thiện p99 có thể phản tác dụng?

Giả sử compaction có khả năng xử lý 450 GiB/ngày khi chạy theo cấu hình bình thường, nhưng có 400 GiB công việc mới mỗi ngày. Nếu hạ concurrency khiến nó chỉ còn xử lý 250 GiB/ngày, **p99 giờ cao điểm có thể giảm** nhưng backlog tăng khoảng 150 GiB/ngày.

Do đó mọi quyết định throttle cần:

- Cơ chế **xử lý bù** ngoài giờ cao điểm nếu có.
- Năng lực xử lý dài hạn ít nhất theo kịp lượng công việc mới.
- Dung lượng đĩa dự phòng cho burst/failure.
- Chỉ số cảnh báo pending bytes, số file và write stalls.
- Một ngưỡng rollback nếu backlog hoặc disk growth vượt dự báo.

## 11. Ví dụ định lượng tải nền

Giả sử một đợt compaction:

~~~~text
Input SSTables read:         800 GiB
Output SSTables written:     600 GiB
Logical obsolete data gone:  200 GiB
Duration:                      1 giờ
~~~~

### 11.1. Tổng I/O

\[
B_{\text{IO}}=800+600=1.400\text{ GiB}
\]

Tốc độ I/O trung bình:

\[
R_{\text{IO}}=
\frac{1.400\times1024}{3.600}
\approx398,2\text{ MiB/s}
\]

Đây là **tổng read+write throughput** tính theo phạm vi đang quan sát, không phải yêu cầu băng thông disk theo từng chiều; thiết bị có thể có giới hạn read/write khác nhau.

### 11.2. I/O cho mỗi GiB thu hồi

\[
C_{\text{IO/reclaim}}=
\frac{800+600}{200}
=7\text{ GiB I/O/GiB reclaimed}
\]

**Đây không phải công thức định nghĩa WA**. Nó giúp đánh giá mức tài nguyên đã trả để dọn obsolete data trong đợt này. Compaction còn có mục đích cải thiện cấu trúc đọc, nên một lượt không thu hồi byte nào vẫn có thể mang giá trị.

### 11.3. Reclaim throughput

\[
R_{\text{reclaim}}=
\frac{200\text{ GiB}}{1\text{ giờ}}
=200\text{ GiB/giờ}
\]

Nhưng **logical obsolete data gone** không tự bằng **byte đã trả lại filesystem**. Nếu snapshot đang tham chiếu các file cũ, output đã hợp lệ nhưng byte vật lý có thể chưa được giải phóng. Phải định nghĩa rõ tử số được đo ở cấp nào.

### 11.4. Điều gì xảy ra nếu disk chỉ còn 250 MiB/s headroom?

Nếu throughput I/O nền trung bình gần 398 MiB/s nhưng hạ tầng chỉ còn khoảng 250 MiB/s băng thông an toàn ngoài workload ứng dụng, một trong các kết quả có thể xảy ra:

- Background I/O bị giới hạn, compaction kéo dài.
- API bị tranh I/O, p99 tăng.
- Cả hai cùng xảy ra.

Không thể suy ra p99 cụ thể bằng phép trừ băng thông. Hãy đo **latency histogram, queue depth, offered vs achieved throughput và timeout** trong một thử nghiệm thực.

## 12. Tác động lên p99: tại sao mức trung bình không đủ?

Một bảng giả định cùng tải API:

| Trạng thái | Achieved throughput | p50 ghi | p99 ghi | Timeout |
| --- | ---: | ---: | ---: | ---: |
| Compaction nhẹ, steady state | 10.000 req/s | 7 ms | 35 ms | 0,01% |
| Compaction I/O cao | 9.900 req/s | 9 ms | 130 ms | 0,15% |
| Backlog lớn, write slowdown | 8.700 req/s | 20 ms | 550 ms | 3,20% |
| Background bị throttle quá mức | 10.000 req/s trong ngắn hạn | 8 ms | 42 ms | 0,02% |

Nhìn một đoạn 10 phút, hàng cuối có thể tưởng tốt nhất. Nhưng nếu trong 24 giờ backlog tăng, cấu hình đó không bền vững.

**Đánh giá phải kết hợp độ trễ hiện tại với xu hướng công việc chưa xử lý**. Chỉ số foreground cần có p50/p95/p99, error, retries, throughput và đỉnh per-node; background cần pending bytes, file count, reclaimed bytes và tốc độ xử lý.

### 12.1. Tail latency và ảnh hưởng cache

Compaction có thể làm p99 tăng ngay cả khi CPU/IO tổng chưa chạm 100% do:

- Cache bị đẩy bởi scan lớn.
- Một disk queue rất dài ở node đang giữ hot key.
- Lock/flush coordination và write stall.
- JVM GC pause hoặc memory pressure.
- File nhiều khiến một phần nhỏ query phải đọc nhiều nơi.

Vì vậy cần xem **latency theo endpoint, shard/partition, node và loại truy vấn**, không chỉ p99 trung bình của cả cluster.

## 13. Công cụ quan sát theo từng hệ thống

Các sản phẩm đặt tên metric khác nhau; bảng sau chỉ nêu **nhóm metric** cần tìm trong đúng version đang dùng.

| Hệ thống | Tác vụ nền cần hiểu | Nguồn quan sát điển hình |
| --- | --- | --- |
| Cassandra | SSTable flush, compaction, tombstone, repair | Compaction statistics, pending tasks, SSTable metrics, read/write latency, repair status |
| HBase | MemStore flush, HFile compaction, region split, TTL/version cleanup | RegionServer metrics, StoreFile count, compaction queue, HDFS I/O |
| RocksDB | L0 files, levels, compaction, write stalls | Properties/statistics cho pending compaction bytes, compaction read/write bytes, stall counters |
| MongoDB | TTL monitor, document/index deletion, reusable storage, WiredTiger maintenance | TTL/delete metrics, collection/index/storage statistics, cache và operation latency |
| Redis | Key expiry, eviction, allocator behavior | INFO stats, INFO memory, latency và expired/evicted counters |
| DynamoDB | TTL asynchronous deletion, background quản lý lưu trữ bởi dịch vụ | TTL/deletion và latency/throttling/storage metrics do dịch vụ cung cấp |
| Search engine | Segment merge, deleted docs, refresh, snapshot | Merge/segment/indexing stats, query latency và storage |

Không phải mọi managed service đều cho phép tự điều chỉnh compaction hoặc xem toàn bộ I/O nội bộ. Trong trường hợp đó, dùng **metric được công bố**, thử nghiệm end-to-end và mô hình năng lực được nhà cung cấp hỗ trợ, không đoán cơ chế ẩn.

### 13.1. Những câu hỏi cần có trên dashboard

**Độ bền và trạng thái lưu trữ:**

- WAL/commit log đã được flush/checkpoint đến đâu?
- Số lượng file/SSTable/segment theo level/tier/window?
- Dung lượng live, obsolete, free/reusable, allocated và snapshot-held?
- Các snapshot, reader hoặc replica đang giữ file cũ?

**Công việc nền:**

- Compaction bytes read/written mỗi giây?
- Pending jobs/bytes và tuổi công việc cũ nhất?
- Tốc độ flush, repair, cleanup, rebalance?
- Write slowdown/stall time, I/O throttling?

**Tác động người dùng:**

- p95/p99 của point lookup, range scan, insert và update?
- Offered/achieved RPS, timeout, retry, lỗi?
- Disk I/O latency/queue, CPU, JVM GC nếu có, RAM/cache và network?
- Node/shard nào có tải nền hoặc disk usage cao nhất?

### 13.2. Counter có thể bị reset hoặc đếm khác phạm vi

Một metric tích lũy **bytes_compacted_total** có thể tăng từ khi process khởi động rồi reset sau restart. Muốn tính GiB/giờ phải dùng delta theo thời gian và phát hiện reset. Tương tự:

- GiB theo binary (1024 MiB) khác GB theo decimal (1000 MB).
- Byte logic chưa nén khác byte vật lý sau nén.
- Node-local metric khác tổng cluster.
- Read/write của engine khác I/O ở tầng block device.
- Có thể double-count khi tổng hợp replica và storage layers.

**Định nghĩa đơn vị và phạm vi đo là một phần của thiết kế metric**, không phải chuyện trang trí dashboard.

## 14. Ví dụ kỹ thuật: kiểm tra workload Cassandra và RocksDB

### 14.1. Cassandra với TTL

Giả sử bảng CQL đã tồn tại:

~~~~sql
INSERT INTO telemetry.events_by_device (
    device_id, day_bucket, event_time, event_id, temperature
) VALUES (
    'device-42',
    '2026-11-14',
    '2026-11-14T08:00:00Z',
    550e8400-e29b-41d4-a716-446655440000,
    24.3
) USING TTL 2592000;
~~~~

TTL 2.592.000 giây tương đương 30 ngày. Khi item hết hạn, nó không được xem là dữ liệu sống theo TTL, nhưng **việc file SSTable mất byte cũ cần chờ điều kiện compaction/an toàn**.

Một người vận hành có thể quan sát compaction và dung lượng SSTable bằng công cụ/metric phù hợp với phiên bản Cassandra, kết hợp:

~~~~text
Compaction pending tasks
Bytes compacted / compaction throughput
SSTable count và disk usage mỗi table
Tombstone scanned per query
Repair health và node trạng thái replica
Read/write latency p95/p99
~~~~

Đặc biệt với TTL đều theo time-series, cần xem chiến lược compaction theo thời gian có phù hợp không; với cập nhật nhiều vào ngày cũ, dữ liệu có thể rơi vào những window không mong muốn.

### 14.2. RocksDB: một mô hình điều khiển compaction

Một ứng dụng nhúng dùng RocksDB có thể cần cấu hình cơ chế compaction và giới hạn tác vụ nền. Ví dụ **pseudo-configuration**, không phải API Java có thể copy chạy trực tiếp:

~~~~yaml
storageEngine: RocksDB
compaction:
  style: level
  backgroundConcurrency: bounded
  inputOutputRateLimit: configured
  writeStallThresholds: workload_based
observability:
  - pendingCompactionBytes
  - level0FileCount
  - writeStallCountAndDuration
  - compactionBytesRead
  - compactionBytesWritten
  - pointLookupP99
~~~~

Tên tùy chọn và cách cấu hình thực cần tra đúng phiên bản RocksDB/Java binding. Mục tiêu là **đo được các biến tác động tới stall** trước khi tăng threads hoặc giảm throttle.

### 14.3. MongoDB: TTL monitor và không gian tái sử dụng

Một TTL index theo thời điểm hết hạn:

~~~~javascript
db.events.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
~~~~

**expiresAt** phải thuộc kiểu ngày phù hợp (thường BSON Date). TTL monitor có thể xóa nền sau deadline chứ không cam kết đúng từng giây. Sau khi xóa, storage engine có thể giữ vùng trống cho lần ghi tiếp theo.

Không thấy kích thước file nhỏ lại không đủ để kết luận TTL/cleanup không hoạt động. Kiểm tra **document count, TTL deletions, reusable bytes, index size và disk headroom** theo metric engine hỗ trợ.

### 14.4. Redis: expiration/eviction và memory GC

~~~~redis
SET cache:product:P-42 "{\"priceMinor\":1390000}" EX 300
TTL cache:product:P-42
INFO stats
INFO memory
~~~~

Key có TTL nhưng có thể bị evict trước khi hết hạn khi bộ nhớ thiếu và policy cho phép. **expired_keys** khác **evicted_keys**; RSS của tiến trình có thể không giảm tương ứng với số key hết hạn vì allocator/fragmentation. Không gọi hiện tượng này là SSTable compaction.

## 15. Chính sách retention và GC: khi nào nên chia theo thời gian?

Dữ liệu time-series có TTL đồng đều thường phù hợp để xem xét **time bucketing**, nhưng phải chọn theo cả truy vấn, hot partition, dữ liệu đến muộn và chiến lược compaction.

| Cách tổ chức | Lợi ích tiềm năng | Chi phí/rủi ro |
| --- | --- | --- |
| Một logical partition rất dài | Query theo một thiết bị đơn giản | Partition lớn, nhiều tombstone, khó dọn |
| Partition theo ngày | Kiểm soát kích thước lịch sử | Query dài phải đọc nhiều partition |
| Theo ngày + hash bucket | Phân phối ghi cho thiết bị/tenant nóng | Fan-out và merge kết quả |
| Segment/time-window theo engine hỗ trợ | Có thể loại file cũ theo nhóm | Late writes và TTL khác nhau làm giảm hiệu quả |
| Xóa từng row | Linh hoạt cho nhiều deadline khác nhau | Tạo nhiều delete/index operations, compaction debt |

### 15.1. Retention logic và thu hồi vật lý không trùng nhau

Một bản ghi hết hạn lúc 09:00 có thể cần bị loại khỏi API ngay, trong khi file chứa nó chỉ được dọn sau khi toàn bộ nhóm dữ liệu đủ điều kiện. **Đường đọc phải giữ đúng hợp đồng retention**, không đợi GC vật lý nếu deadline là bắt buộc.

### 15.2. Dữ liệu đến muộn

Event được tạo lúc 23:58 ngày D nhưng server nhận lúc 00:05 ngày D+1:

- Nếu retention theo **eventTime**, nó có thể thuộc bucket ngày D.
- Nếu retention theo **ingestionTime**, nó thuộc bucket ngày D+1.
- Nếu ghi vào window đã đóng, có thể tạo file mới và compaction bổ sung cho dữ liệu lịch sử.

Phải quyết định thời điểm có thẩm quyền và cách xử lý event đã quá hạn ngay khi tới, không dùng timestamp client không tin cậy làm điều kiện xóa dữ liệu nhạy cảm mà không kiểm tra.

### 15.3. Snapshot giữ file cũ lâu hơn TTL

Một snapshot hợp lệ có thể giữ SSTable hoặc block chứa dữ liệu đã hết hạn logic. Thời gian file được thu hồi phụ thuộc vòng đời snapshot và backup, **không chỉ giá trị TTL**.

Khi tính dung lượng cần tách:

~~~~text
Live data
Obsolete values/tombstones
Compaction output tạm
Index và WAL
Snapshot-held file/block
Backup/object store
Replica copies
~~~~

## 16. Thiết kế thử nghiệm compaction/GC có đối chứng

Không thể benchmark compaction bền vững bằng cách nạp một vài nghìn bản ghi rồi kết luận sau 5 phút. Một workload đại diện cần:

- Đủ thời gian tạo **nhiều level/window/file**.
- Tỷ lệ **insert/update/delete/TTL** giống thực tế.
- Distribution của key, hot key và kích thước value.
- Point lookup, range scan và truy vấn phải qua tombstone.
- Thời gian giữ snapshot/reader nếu production có.
- Replica, repair/rebalance và sự cố có thể xảy ra.

### 16.1. Các giai đoạn

1. **Baseline steady state:** ghi/đọc ở tải bình thường cho tới khi số file/queue tương đối ổn định.
2. **Tạo workload cũ:** ghi nhiều version/TTL/delete theo mô hình có kiểm soát.
3. **Compaction/GC phase:** đo khi công việc nền xử lý backlog trong lúc API tiếp tục hoạt động.
4. **Recovery phase:** đo p99 và headroom sau khi công việc lớn kết thúc.
5. **Repeat:** chạy lại với cấu hình khác, cùng dataset seed và offered load.

### 16.2. Ma trận thử nghiệm

| Kịch bản | Thay đổi | Kết quả cần thu |
| --- | --- | --- |
| Append-only baseline | Ghi mới, đọc point/range | File growth, read/write p99, WA |
| Heavy overwrite | Cập nhật cùng một tập key | Old versions, compaction I/O, WA |
| Sparse deletes | Xóa nhiều row xen kẽ live data | Tombstone scan, reclaim lag, read p99 |
| TTL đồng loạt | Nhiều key hết hạn cùng cửa sổ | Cleanup peak, disk I/O, p99 |
| TTL phân tán | Deadline phân bố theo policy hợp lệ | Backlog, mức đỉnh, tổng chi phí |
| Snapshot pinning | Một snapshot/read iterator kéo dài | Reclaimed bytes, disk headroom |
| Late data | Ghi vào cửa sổ thời gian cũ | Compaction thêm, kết quả truy vấn |
| Repair overlap | Compaction + repair/rebalance | CPU/IO/network contention |
| Compaction throttle | Các mức giới hạn nền | p99 ngắn hạn và backlog dài hạn |
| High concurrency | Tăng background worker | Throughput merge, cache và p99 |
| Low disk headroom | Chạy thử ở môi trường an toàn | Fail-safe, write stall, khả năng khôi phục |
| Process crash | Crash khi output/manifest đang thay đổi | Dữ liệu không mất, file tạm được dọn |

### 16.3. Đặc tả benchmark mẫu

~~~~yaml
experiment: compaction-gc-background-impact
dataset:
  keys: 100000000
  averageValueBytes: 1024
  retentionDays: 30
  replicationFactor: 3
  hotKeySharePercent: 20
workload:
  offeredWritesPerSecond: 12000
  offeredReadsPerSecond: 24000
  updateSharePercent: 30
  deleteSharePercent: 10
  readPatterns:
    - point_lookup
    - latest_100_by_device
    - range_last_24_hours
maintenance:
  scenarios:
    - steady_state
    - compaction_backlog
    - ttl_wave
    - sparse_delete
    - snapshot_pinned
    - repair_overlap
    - crash_during_compaction
measure:
  - foreground_p50_p95_p99
  - offered_versus_achieved_throughput
  - timeout_retry_stall_rate
  - files_per_level_and_read
  - compaction_bytes_read_written
  - pending_compaction_bytes_and_age
  - reclaimed_reusable_physical_bytes
  - disk_IOPS_latency_queue
  - CPU_RAM_JVM_GC_if_applicable
  - snapshot_and_replica_health
  - correctness_after_restart_repair
~~~~

Đây là **mẫu mô tả thử nghiệm**, không phải tệp cấu hình chạy trực tiếp. Các con số và tên metric cần điều chỉnh theo driver, engine, topology, compression, index và SLO.

### 16.4. Kết quả minh họa

| Cấu hình/kịch bản giả định | p99 ghi | p99 đọc | Compaction output | Pending work | Điều cần cân nhắc |
| --- | ---: | ---: | ---: | ---: | --- |
| Steady state | 55 ms | 45 ms | 250 GiB/h | Ổn định | Baseline |
| Tăng compaction concurrency | 170 ms | 135 ms | 420 GiB/h | Giảm | Dọn nhanh, API bị tranh I/O |
| Throttle compaction mạnh | 40 ms | 50 ms | 110 GiB/h | Tăng | p99 tốt trước mắt, rủi ro backlog |
| Snapshot giữ file cũ | 75 ms | 60 ms | 250 GiB/h | Ổn định | Byte vật lý chưa được giải phóng |
| Heavy overwrite/delete | 230 ms | 210 ms | 380 GiB/h | Tăng | WA và tombstone pressure |

**Số liệu hoàn toàn giả định**. Không chọn cấu hình chỉ vì p99 thấp trong một giờ nếu pending work tăng mỗi ngày; cũng không tăng concurrency tới mức phá SLO chỉ để dọn nhanh.

## 17. Tính đúng sau crash, delete và replica repair

Compaction/GC không chỉ là bài toán hiệu năng. Một thử nghiệm đúng phải bảo đảm:

1. **Không mất dữ liệu đã được ACK** theo hợp đồng durability của engine.
2. **Không lộ dữ liệu chưa commit** sau một crash hoặc quá trình rebuild.
3. **Không khôi phục phiên bản cũ** khi phiên bản mới đã commit và được phục vụ theo hợp đồng.
4. **DELETE không bị hồi sinh** khi replica cũ trở lại.
5. **Snapshot/read iterator** còn đọc được trạng thái được bảo đảm trong khi compaction chạy.
6. **Index, checksum và manifest** còn hợp lệ sau khi dừng giữa chừng.
7. **Dữ liệu còn hạn** không bị xóa nhầm; dữ liệu hết hạn không xuất hiện ở đường đọc theo policy.
8. **Backup/restore** hoạt động theo RPO/RTO và policy xóa dữ liệu được xác định.

### 17.1. Thử crash giữa compaction

Một kịch bản kiểm chứng:

~~~~text
T0: Seed dữ liệu và xác nhận write ACK
T1: Chạy update/delete, tạo nhiều file
T2: Khởi chạy compaction
T3: Dừng đột ngột process trong môi trường thử
T4: Khởi động lại
T5: Đọc/scan checksum tập dữ liệu mong đợi
T6: Xác minh không mất bản đã ACK, không lộ bản chưa commit
T7: Kiểm tra recovery dọn output tạm và tiếp tục compaction an toàn
~~~~

Đừng mô phỏng lỗi kiểu này trên production. Các ACK phải được diễn giải đúng write concern/replication/durability; một ghi chưa có xác nhận bền vững không thể đòi bảo đảm giống ghi đã commit theo hợp đồng.

### 17.2. Thử replica nhận delete trễ

~~~~text
Replica A nhận DELETE K.
Replica B offline trước DELETE.
A dọn dữ liệu cũ theo cơ chế engine.
B trở lại, thực hiện repair/sync.
~~~~

Kết quả phải phù hợp với quy tắc tombstone và repair. Nếu A xóa marker quá sớm khi B còn bản cũ có khả năng được chấp nhận, đó là vấn đề correctness nghiêm trọng.

### 17.3. Thử snapshot cũ

Giữ một snapshot/read iterator từ trước khi cập nhật K; trong lúc đó ghi version mới và cho compaction chạy. Xác minh **reader cũ vẫn đọc đúng dữ liệu theo snapshot semantics** và file cũ chỉ được GC khi đủ an toàn.

## 18. Runbook: p99 tăng và compaction queue tích tụ

Khi xuất hiện lỗi, tránh phản xạ **force compaction** hoặc chỉnh tất cả tham số cùng lúc.

### Bước 1 — Phân loại triệu chứng

- p99 đọc hay ghi tăng?
- Throughput giảm do chậm I/O hay **write stalls**?
- Chỉ một node/shard hay toàn cluster?
- Số file, pending bytes và disk queue thay đổi khi nào?
- JVM GC pause hoặc backup/repair có tăng cùng lúc không?

### Bước 2 — Xác định công việc nền

- Compaction strategy và số worker hiện tại?
- Bytes read/write per second, backlog tăng hay giảm?
- Flush có sinh file nhanh hơn compaction xử lý?
- TTL/tombstone có tạo một đợt dữ liệu chết lớn?
- Có snapshot/read iterator giữ file lâu?
- Có repair/rebalance/index rebuild đang trùng giờ cao điểm?

### Bước 3 — Kiểm tra an toàn và headroom

- Disk free ở node xấu nhất?
- Có đủ chỗ cho compaction output, WAL và recovery?
- Replica/repair có đang khỏe để dọn tombstone?
- Backup/snapshot vẫn đáp ứng chính sách?
- Có khách hàng/tenant nóng gây mất cân bằng dữ liệu?

### Bước 4 — Giảm tải có kiểm soát

- Hoãn backfill/reindex không cấp thiết.
- Giới hạn batch delete hoặc nhập liệu phụ không bắt buộc.
- Điều chỉnh throttle/concurrency ở ngưỡng đã thử, theo dõi p99 và backlog.
- Bổ sung năng lực disk/node nếu maintenance không thể theo kịp.
- Sửa snapshot/reader leak hoặc repair bị kẹt.
- Xem xét thay chiến lược compaction/layout cho dữ liệu tương lai theo kế hoạch migration.

### Bước 5 — Xác nhận sau thay đổi

Thành công không phải chỉ “p99 giảm trong 10 phút”. Cần chứng minh:

- Pending work ổn định hoặc giảm dưới workload thực tế.
- Disk headroom không tiếp tục cạn.
- p99/error đạt SLO vào giờ đỉnh.
- Không phát sinh zombie data, mất dữ liệu hoặc lỗi snapshot/restore.
- Chi phí CPU/IO/năng lực dọn phù hợp kế hoạch dài hạn.

## 19. Những sai lầm cần tránh

1. **“Compaction và GC là một.”** Compaction tổ chức/hợp nhất dữ liệu; GC loại những đối tượng/phiên bản không còn cần. Chúng có thể kết hợp nhưng không đồng nghĩa.
2. **“JVM GC dọn SSTable.”** JVM GC thu hồi object Java; file/block lưu trữ cần cơ chế riêng.
3. **“Xóa xong là trả đĩa ngay.”** Có thể còn tombstone, version cũ, snapshot hoặc vùng trống nội bộ.
4. **“Compaction chỉ chạy khi có DELETE.”** Nhiều lượt chạy để giảm file overlap và read amplification ngay cả khi không có xóa.
5. **“Write amplification là số byte đã xóa.”** WA tính byte ghi vật lý so với ghi logic; có nhiều thành phần.
6. **“Tăng compaction worker luôn tốt.”** Có thể bão hòa SSD và làm p99 tăng.
7. **“Giảm compaction tối đa sẽ tốt cho người dùng.”** Backlog có thể tăng tới lúc write stall.
8. **“Không còn pending task là mọi dữ liệu cũ đã được xóa.”** Snapshot, replica và backup vẫn có thể giữ file.
9. **“Có TTL thì không cần lọc hạn ở API.”** Một số dịch vụ xóa nền trễ; hợp đồng read phải được bảo đảm riêng.
10. **“Bỏ tombstone sớm giúp an toàn hơn.”** Có thể làm dữ liệu xóa hồi sinh sau khi replica cũ quay lại.
11. **“Disk used trung bình cluster còn thấp nên không sao.”** Node/shard nóng nhất có thể đầy trước.
12. **“Kích thước file không giảm tức GC không làm gì.”** Có thể đã có vùng trống tái sử dụng.
13. **“Compaction thành công là không thể mất dữ liệu.”** Còn phụ thuộc atomic metadata install, WAL, ACK và crash recovery.
14. **“Benchmark chỉ cần throughput.”** Cần p99, stalls, pending work, I/O và tính đúng sau lỗi.
15. **“Chiến lược leveled/time-window luôn tốt hơn size-tiered.”** Mỗi chiến lược đổi read/write/space amplification theo workload.
16. **“Giữ snapshot miễn phí khi đã compaction.”** Snapshot có thể pin file và ngăn reclaim vật lý.

## 20. Bài tập thực hành: hệ thống sự kiện IoT

Một nền tảng lưu sự kiện từ 80.000 thiết bị. Giả định:

- Mỗi ngày ghi **40 triệu event**, mỗi event trung bình **1 KiB** trước nén và metadata.
- **Replication factor = 3**.
- Retention dữ liệu nóng **14 ngày**.
- API đọc **100 event mới nhất theo thiết bị** và truy vấn **24 giờ gần nhất**.
- Tải ghi cao điểm gấp **3 lần** bình thường.
- 10% event có thể đến muộn tới 12 giờ.
- p99 đọc phải dưới **150 ms**; p99 ghi dưới **200 ms**.
- Cụm có snapshot hằng ngày và repair định kỳ.

Sau khi chạy một tuần:

~~~~text
SSTable count tăng.
Pending compaction bytes tăng 150 GiB/ngày.
Disk used ở node nóng nhất tăng từ 72% lên 86%.
p99 ghi tăng từ 60 ms lên 280 ms trong giờ đỉnh.
Một snapshot cũ vẫn được giữ vì quy trình backup.
~~~~

### Phần A — Giải thích hiện tượng

Phân biệt **flush**, **compaction**, **storage GC** và **JVM GC**. Với mỗi hiện tượng, chỉ ra metric cần xem và vì sao chỉ số disk used 86% chưa đủ xác định nguyên nhân.

### Phần B — Tính dung lượng payload

Với 40 triệu event/ngày × 1 KiB:

\[
B_{\text{daily}}=
40.000.000\times1.024
=40.960.000.000\text{ byte}
\]

Hãy đổi thành GiB/ngày, tính 14 ngày và nhân replication factor 3. Sau đó liệt kê những phần **chưa tính**: compression, index, key metadata, WAL, tombstone, compaction temp, snapshot và chênh lệch dung lượng giữa node.

**Gợi ý:** khoảng **38,15 GiB payload/ngày**; 14 ngày khoảng **534,1 GiB logic**; ba replica khoảng **1.602,2 GiB**, tức khoảng **1,56 TiB payload nhân bản** trước overhead/nén.

### Phần C — Tính I/O compaction

Một đợt compaction đo được:

~~~~text
Read:                 900 GiB
Write:                700 GiB
Obsolete bytes gone:  200 GiB
Duration:               4 giờ
~~~~

Tính:

- Tổng I/O.
- I/O trung bình MiB/s.
- I/O cost trên 1 GiB obsolete data đã loại.
- Vì sao **obsolete bytes gone** có thể khác **physical bytes freed** khi snapshot còn giữ file?

**Gợi ý:** tổng I/O **1.600 GiB**; trung bình **(1600 × 1024)/(4 × 3600) ≈ 113,8 MiB/s**; chi phí **8 GiB I/O/1 GiB obsolete data gone**.

### Phần D — Backlog và throttle

Pending compaction bytes tăng 150 GiB/ngày. Nếu không thay đổi, sau 7 ngày có thể tăng thêm bao nhiêu theo mô hình tuyến tính? Nếu giảm compaction threads khiến p99 ghi xuống 100 ms nhưng backlog tăng 250 GiB/ngày, quyết định đó đã đạt mục tiêu vận hành dài hạn chưa?

### Phần E — Thiết kế compaction strategy

So sánh **size-tiered, leveled và time-window** trong trường hợp:

1. Ghi append và đọc range 24 giờ.
2. Update nhiều event cũ.
3. TTL tương đối đồng đều.
4. Có 10% late events.
5. Đĩa còn ít headroom.

Chỉ ra yếu tố phải xác minh với engine cụ thể, không chỉ chọn một chiến lược theo tên.

### Phần F — Crash recovery và zombie data

Thiết kế hai phép thử:

1. Kill tiến trình giữa khi compaction đang tạo file output/manifest; restart và xác minh tất cả write được ACK theo durability contract vẫn tồn tại, metadata không trỏ tới file hỏng.
2. Một replica bị offline trước khi DELETE được thực hiện, sau đó quay lại sau nhiều đợt compaction; xác minh dữ liệu đã xóa không hồi sinh.

Nêu thêm một trường hợp snapshot/iterator kéo dài ngăn file cũ được GC và cách phát hiện.

### Phần G — Benchmark và runbook

Lập dashboard đo **compaction bytes read/written, pending work, files per level, JVM GC nếu có, disk I/O latency, p99 API, timeout, reclaimed bytes, snapshot-held bytes và replica/repair status**. Đề xuất một thay đổi có thể thử nghiệm an toàn, tiêu chí thành công và điều kiện rollback.

### Hướng giải

Không có một lệnh **force compaction** nào thay thế được hiểu biết về đường ghi, compaction debt, snapshot pinning và an toàn xóa. Một kế hoạch có thể cân nhắc chọn time-window cho dữ liệu có TTL đồng đều nếu engine/workload phù hợp; giảm update vào window cũ; kiểm soát repair/snapshot; dành headroom cho compaction; và tune concurrency ở mức **dọn được backlog dài hạn nhưng không phá p99**. Mỗi bước phải được kiểm chứng với dữ liệu đến muộn, replica và khả năng khôi phục.

**Kết luận:** Compaction và storage garbage collection là các cơ chế nền giúp NoSQL duy trì **khả năng đọc hiệu quả, khả năng tái sử dụng dung lượng và trạng thái lưu trữ đúng qua cập nhật, xóa và crash**. Chúng gắn trực tiếp với **WAL, snapshot, replica, tombstone và ranh giới durability**, không chỉ với tối ưu đĩa. Đánh giá đúng phải đồng thời đo **read/write/space amplification, compaction backlog, disk/CPU/RAM/network, headroom, p99 và tính đúng sau lỗi**. Một hệ thống bền vững cần **công suất dọn nền theo kịp công việc phát sinh** mà vẫn bảo vệ dữ liệu và SLO người dùng.
