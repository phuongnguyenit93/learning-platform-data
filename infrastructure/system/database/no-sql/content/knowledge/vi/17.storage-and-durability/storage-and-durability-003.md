# Write-ahead log/commit log và khả năng phục hồi sau sự cố

Một cơ sở dữ liệu NoSQL có thể trả lời truy vấn chỉ sau vài mili giây, nhưng tốc độ không đủ để bảo đảm dữ liệu tồn tại sau khi tiến trình bị dừng, máy mất điện hoặc một node chết đột ngột. Giả sử client gửi thao tác cập nhật số dư, máy chủ trả kết quả thành công, rồi ổ đĩa hoặc tiến trình gặp sự cố trước khi cấu trúc dữ liệu chính kịp được ghi ra lưu trữ bền vững. Khi khởi động lại, hệ thống lấy đâu ra trạng thái đã được xác nhận?

Đó là một trong những vấn đề mà **write-ahead log (WAL)** hoặc **commit log** giúp giải quyết. Thay vì chỉ cập nhật cấu trúc dữ liệu đang nằm trong RAM hoặc ghi lại toàn bộ file dữ liệu sau mỗi thay đổi, hệ thống ghi một **bản ghi có thể dùng để phục hồi** vào log theo một thứ tự đã xác định. Khi cấu hình độ bền yêu cầu, log phải đạt mốc lưu bền cần thiết trước khi hệ thống được phép coi giao dịch hoặc thao tác ghi là đã commit.

Tuy nhiên, phát biểu “có WAL thì không bao giờ mất dữ liệu” là sai. Độ bền thực tế còn phụ thuộc **thứ tự ghi, fsync, chính sách ACK, ổ đĩa, replication, checkpoint, compaction, sao lưu và quy trình khôi phục**. WAL cũng không mặc nhiên là một transaction log phân tán, một bản backup, hoặc một cơ chế đảm bảo mọi hiệu ứng bên ngoài chỉ chạy một lần.

Bài học này đi từ nguyên lý tới triển khai NoSQL, nêu rõ các mốc bền vững, cách replay khi crash, những sai lầm thường gặp và quy trình kiểm thử thực tế.

## 1. Vấn đề WAL giải quyết

Hãy xét một node đang giữ các bản ghi:

~~~text
Order O-100:
  status = PENDING
  version = 7

Client:
  confirmOrder(O-100)

Server:
  cập nhật status = CONFIRMED trong RAM
  trả ACK
  mất điện trước khi ghi file dữ liệu
~~~

Nếu RAM là nơi duy nhất có trạng thái mới, sau khi node khởi động lại, file trên đĩa có thể vẫn chứa `PENDING`. Client đã nhận thành công nhưng dữ liệu lại bị mất. Trong nhiều hệ thống, điều này vi phạm cam kết **durability** của thao tác.

Một hướng giải quyết là lưu đủ thông tin để **làm lại** thay đổi đó:

~~~text
Log record:
  orderId = O-100
  operation = setStatus(CONFIRMED)
  expectedVersion = 7
  newVersion = 8
~~~

Ở một thiết kế WAL phù hợp, bản ghi này được ghi và đạt mức bền cần thiết trước khi server ACK theo chính sách durability đã công bố. Sau crash, hệ đọc log, nhận ra thay đổi nào cần được áp dụng hoặc phát lại, rồi dựng lại trạng thái.

### 1.1. Mục đích thường gặp của WAL

- **Phục hồi sau crash:** khôi phục thay đổi đã được chấp nhận nhưng chưa vào file dữ liệu ổn định.
- **Giảm random write:** append bản ghi log thường thuận lợi hơn ghi đồng bộ nhiều data page rải rác.
- **Duy trì thứ tự thay đổi:** log sequence/order hỗ trợ replay, checkpoint và một số cơ chế replication.
- **Bảo vệ atomicity:** trong các engine giao dịch, log có thể ghi nhận begin/update/commit/abort để xử lý thao tác dở dang.
- **Hỗ trợ point-in-time recovery:** khi có kiến trúc log archiving và snapshot nhất quán, các log liên tục có thể giúp phục hồi tới mốc thời gian hoặc sequence mong muốn.

Không phải mọi NoSQL dùng WAL vì cùng một mục đích hoặc cùng một định dạng. Cần hiểu **invariant mà storage engine phải bảo vệ**, thay vì chỉ tìm cấu hình có tên `commitlog`.

## 2. Các thành phần: RAM, log và cấu trúc dữ liệu chính

Trong một engine kiểu LSM-tree, đường ghi thường liên quan:

~~~mermaid
flowchart TD
    CLIENT["Client write"] --> ENGINE["Storage engine"]
    ENGINE --> WAL[("WAL / commit log trên storage")]
    ENGINE --> MEM["Memtable trong RAM"]
    MEM --> FLUSH["Flush"]
    FLUSH --> SST[("SSTable bất biến")]
    SST --> COMP["Compaction"]
    COMP --> SST2[("SSTable mới")]
    WAL --> REPLAY["Crash recovery / replay"]
    REPLAY --> MEM
~~~

Các bộ phận:

| Thành phần | Vai trò | Sau crash có còn không? |
|---|---|---|
| **Client request** | Mang ý định ghi | Client có thể không biết outcome nếu timeout |
| **WAL/commit log buffer** | Gom bản ghi log trước khi flush | RAM có thể mất |
| **WAL file/segment** | Lưu lịch sử thay đổi phục vụ recovery | Phụ thuộc mức ghi và độ bền thiết bị |
| **Memtable** | Cấu trúc ghi/đọc nhanh trong RAM | Thường mất khi tiến trình chết |
| **SSTable/data file** | Dữ liệu đã được flush theo cấu trúc bền | Thường được giữ sau crash nếu ghi hoàn tất |
| **Manifest/metadata** | Cho biết file/segment nào cấu thành state hợp lệ | Phải được ghi và phục hồi an toàn |
| **Replica** | Bản sao trên node khác | Phụ thuộc replication và ACK |
| **Backup/archive** | Bản sao dùng cho phục hồi độc lập | Có retention và mục tiêu khác WAL live |

Memtable giúp tăng tốc ghi; WAL cho phép phục hồi các update chưa kịp biến thành SSTable hoặc dữ liệu chính bền vững. Khi một memtable được flush thành công và metadata xác nhận dữ liệu mới đã bền, phần WAL tương ứng có thể trở nên không còn cần cho replay.

### 2.1. WAL không bắt buộc dùng cùng format với data file

WAL thường thiên về **append tuần tự**, còn data file/index được tổ chức cho truy vấn. Một log record có thể chứa key, value, mutation, transaction ID hoặc redo/undo data. Không thể suy rằng WAL là một bản sao JSON đầy đủ của toàn bộ collection.

### 2.2. WAL không luôn đi trước thay đổi trong RAM

Quy tắc “write-ahead” cốt lõi thường yêu cầu **thông tin phục hồi phải được lưu bền trước khi data page chứa thay đổi tương ứng được ghi bền**, và trước ACK nếu durability contract yêu cầu. Một số engine có thể cập nhật memtable trong RAM trước hoặc song song với thao tác buffer/append log, nhưng phải quản lý thứ tự, visibility và thời điểm commit đúng. Không nên diễn giải tên WAL thành “mọi byte RAM luôn bị sửa sau mọi byte log” cho mọi engine.

## 3. Nguyên tắc write-ahead

Nguyên tắc tổng quát:

**Trước khi một phiên bản data page cần được coi là bền vững, hệ phải có log record bền vững đủ để tái tạo hoặc xử lý thay đổi chứa trong page đó.**

Trong engine có transaction, còn có quy tắc liên quan commit: trước khi báo transaction đã commit theo mức durability yêu cầu, các log record và thông tin commit cần thiết phải đạt mốc bền phù hợp.

Một sequence khái niệm:

~~~text
T0: Nhận update K từ V0 -> V1.
T1: Tạo log record LSN=105 mô tả update.
T2: Append LSN=105 vào log buffer/file.
T3: Đồng bộ log tới mức lưu bền đã cam kết.
T4: Đánh dấu thao tác committed và ACK theo chính sách.
T5: Dữ liệu trong memtable/page được flush về sau.
T6: Checkpoint xác định mốc không cần replay một phần log cũ.
~~~

Thứ tự T3/T4 là điểm phân biệt quan trọng. Nếu ACK ở T2 trong khi dữ liệu mới chỉ nằm ở **OS page cache**, hệ có thể chấp nhận mất một phần ghi khi mất điện hoặc kernel crash, tùy durability policy.

### 3.1. Một diagram thể hiện ranh giới ACK

~~~mermaid
sequenceDiagram
    participant C as Client
    participant DB as NoSQL Engine
    participant L as Log/Storage
    participant M as Memtable
    participant F as SSTable
    C->>DB: Write K=V1
    DB->>L: Append WAL record
    DB->>L: Flush/sync theo durability policy
    L-->>DB: Bền theo mức đã yêu cầu
    DB->>M: Apply mutation trong RAM
    DB-->>C: ACK
    Note over DB,F: Về sau, flush memtable
    M->>F: Tạo data file ổn định
~~~

Đây là **mô hình minh họa**, không phải trình tự chính xác của mọi engine. Một sản phẩm có thể cập nhật memtable trước log sync, hoặc ACK theo policy yếu hơn; điểm cần đọc trong tài liệu là **ACK xác nhận tới mức nào**.

### 3.2. Write-ahead rule giúp giải quyết điều gì?

Nếu dữ liệu trong RAM mất nhưng log đã bền, recovery có thể tái tạo update. Nếu data page đã được ghi ra storage mà transaction chưa commit, một hệ giao dịch cần biết cách **undo/rollback** hoặc nhận ra page chưa thuộc trạng thái hợp lệ. Cách xử lý tùy mô hình engine.

## 4. Phân biệt append, flush, sync, commit và ACK

Nhiều lỗi thiết kế xảy ra vì những từ này bị coi là đồng nghĩa.

| Mốc | Ý nghĩa có thể gặp | Có nghĩa “không mất sau mất điện” không? |
|---|---|---|
| **Enqueue log entry** | Mutation được đưa vào hàng đợi RAM | Không |
| **Write/append syscall** | Bytes có thể đã vào page cache của OS | Chưa chắc |
| **Flush user-space buffer** | Bytes từ buffer ứng dụng được gửi xuống lớp dưới | Chưa chắc |
| **fsync/fdatasync hoặc tương đương** | Yêu cầu OS/storage đồng bộ dữ liệu theo semantics được hỗ trợ | Mạnh hơn, nhưng còn phụ thuộc thiết bị và hệ thống |
| **Database commit** | Engine xác nhận điều kiện commit nội bộ | Phải xét cấu hình durability/replication |
| **Client ACK** | Response trả về người gọi | Chỉ mạnh bằng chính sách và mốc ACK thực tế |
| **Replica ACK** | Một replica xác nhận theo protocol của hệ | Có thể là nhận RAM, ghi log hay durable sync tùy protocol |

### 4.1. OS page cache không phải ổ đĩa đã bền

Một lệnh write() thành công thường có thể mới chuyển bytes sang page cache. Nếu tiến trình bị kill nhưng kernel vẫn chạy, kernel có thể tiếp tục flush. Nhưng mất điện hoặc kernel crash có thể làm mất những bytes chưa được đồng bộ. Vì thế không thể kiểm thử durability chỉ bằng cách kill một tiến trình rồi kết luận đã chịu được mất điện.

### 4.2. fsync cũng cần hiểu storage stack

Một lời gọi sync đã hoàn thành có nghĩa gì phụ thuộc OS, filesystem, loại thiết bị, cache controller, môi trường ảo hóa và việc storage thực hiện đúng lệnh flush/barrier hay không. Thiết bị có volatile write cache không được bảo vệ hoặc cấu hình sai có thể làm suy yếu cam kết.

Khi đổi tên file log/manifest bằng atomic rename, trên một số filesystem cần quan tâm cả việc **đồng bộ thư mục** để bảo đảm metadata thay đổi sống sót sau crash. Không nên chỉ xem dữ liệu trong file đã sync mà bỏ qua trình tự cập nhật file name và manifest.

### 4.3. Commit không nhất thiết đồng nghĩa replica đã có

Một hệ có thể ACK sau khi leader ghi vào log local, trong khi hệ khác đợi quorum hoặc đợi các replica đạt mốc nhất định. Hai cấu hình đều có thể gọi “commit” ở tài liệu, nhưng fault tolerance khác nhau. Luôn gắn từ commit với **write concern/consistency/durability setting cụ thể**.

## 5. Cấu trúc của một WAL record

WAL cần đủ thông tin để xác định thứ tự, phát hiện bản ghi lỗi và khôi phục một cách đúng đắn.

Ví dụ định dạng **khái niệm**:

~~~json
{
  "recordType": "UPDATE",
  "logSequenceNumber": 105,
  "transactionId": "tx-290",
  "collectionId": "orders",
  "key": ["T-10", "O-100"],
  "previousVersion": 7,
  "newVersion": 8,
  "mutation": {
    "status": "CONFIRMED"
  },
  "schemaVersion": 3,
  "checksum": "<checksum of serialized record>"
}
~~~

Đây không phải format thực của một engine cụ thể. Nhiều engine dùng **binary framing** cùng length, type, sequence và checksum thay vì JSON. Một WAL transactional có thể chứa redo/undo record; commit log của LSM thường ghi mutation cần replay.

### 5.1. Log sequence number (LSN)

**LSN** hoặc sequence number nhận diện vị trí/thứ tự tương đối trong log. Nó có thể là offset byte, số tăng, hoặc vị trí gồm segment và offset.

~~~text
segment-0042:
  LSN 100 -> PUT K1=V1
  LSN 101 -> DELETE K2
  LSN 102 -> PUT K3=V2
  LSN 103 -> COMMIT tx-290
~~~

LSN giúp:

- Xác định mốc checkpoint.
- Phát hiện record nào đã được apply.
- Giữ thứ tự replay.
- Gắn dữ liệu chính với thay đổi đã commit.
- Theo dõi replication/backup log.

**LSN cục bộ của một node không tự có nghĩa là thứ tự toàn cầu trên mọi node/partition.** Khi hệ phân tán có nhiều leader/partition, phải xem sequence có scope ở đâu.

### 5.2. Segment và offset

Thay vì một file WAL lớn vô hạn, engine thường chia thành **segment**:

~~~text
wal-000018.log
wal-000019.log
wal-000020.log
~~~

Segment giúp rotate, checkpoint, archive hoặc xóa log cũ sau khi an toàn. Nhưng không được xóa một segment chỉ vì nó “đã cũ”; trước tiên phải chứng minh mọi thay đổi cần thiết đã được flush/replicate/backup theo chính sách.

### 5.3. Length và checksum

WAL dạng binary thường cần framing (độ dài bản ghi) và checksum để phân biệt:

- Một record hoàn chỉnh, hợp lệ.
- Record cuối bị ghi dang dở khi mất điện.
- Bytes bị hỏng do lỗi storage.
- Dữ liệu không thuộc đúng định dạng hoặc phiên bản log.

Nếu đang replay mà gặp record lỗi **ở đuôi log**, một số engine có thể bỏ đoạn đuôi chưa được commit theo protocol an toàn. Nếu checksum lỗi **ở giữa một đoạn log đã được coi là bền**, tình huống nghiêm trọng hơn: không được tự bỏ qua rồi tuyên bố phục hồi thành công nếu làm mất những mutation đã ACK.

## 6. Các loại thông tin ghi vào log

Không phải WAL nào cũng ghi cùng loại dữ liệu:

| Loại | Ý tưởng | Khi phù hợp |
|---|---|---|
| **Physical redo** | Ghi thông tin về page/offset/bytes cần khôi phục | Engine định hướng page |
| **Logical redo** | Ghi mutation như put/delete hoặc thao tác logic đủ xác định | Engine key–value/LSM hoặc replication log |
| **Undo information** | Cho phép đảo thay đổi chưa commit | Engine có transaction và dirty page |
| **Commit/abort marker** | Phân biệt transaction hoàn tất hoặc bị hủy | Transactional log |
| **Checkpoint/manifest record** | Gắn trạng thái log với data file ổn định | Recovery và dọn log |

### 6.1. Redo và undo khác nhau

**Redo:** áp dụng lại một thay đổi đã commit nhưng chưa hiện diện đầy đủ trong data file.  
**Undo:** hoàn tác thay đổi của transaction chưa commit đã ảnh hưởng tới dữ liệu được lưu.

Trong các engine kiểu ARIES, recovery có thể gồm analysis, redo và undo với page LSN/transaction log record. Nhưng không nên áp mô hình ARIES trực tiếp cho mọi NoSQL; một LSM engine ghi mutation vào WAL và chỉ flush memtable chứa trạng thái hợp lệ có thể chủ yếu cần **replay mutation đã được chấp nhận** thay vì cơ chế undo page như RDBMS.

### 6.2. Mutation log không thay thế domain transaction

Một commit log có thể chứa nhiều mutation của nhiều key, nhưng điều đó không chứng minh nhóm mutation thuộc cùng **transaction nguyên tử**. Nếu API chỉ bảo đảm thao tác một item, cần giữ bất biến nghiệp vụ trong phạm vi đó hoặc dùng transaction/workflow riêng.

## 7. Đường ghi LSM-tree: WAL, memtable, SSTable

Với nhiều NoSQL dạng wide-column hoặc key–value dùng LSM-tree, đường ghi khái niệm là:

1. Nhận mutation.
2. Ghi thông tin phục hồi vào WAL/commit log.
3. Cập nhật memtable trong RAM.
4. ACK khi đạt mức durability/consistency cấu hình.
5. Khi memtable đầy hoặc tới ngưỡng, freeze và flush thành SSTable.
6. Cập nhật metadata/manifest để nhận diện SSTable mới.
7. Khi biết các mutation cần thiết đã được lưu bền ở SSTable, đánh dấu WAL segment tương ứng có thể tái sử dụng hoặc xóa.
8. Compaction hợp nhất SSTable theo các quy tắc storage engine.

~~~mermaid
flowchart TD
    W["PUT K=V"] --> LOG[("Append WAL")]
    W --> MT["Memtable"]
    LOG --> ACK["Durability boundary / ACK"]
    MT --> IMM["Immutable memtable"]
    IMM --> SST[("SSTable trên disk")]
    SST --> MAN["Manifest/checkpoint cập nhật"]
    MAN --> SAFE["WAL cũ đủ điều kiện dọn"]
    SST --> COMPACT["Compaction"]
~~~

Sơ đồ không xác định một thứ tự byte-level bắt buộc giữa mọi nhánh, vì từng engine có thể buffer và flush khác nhau. Điều bắt buộc là trình tự bền vững **không tạo lỗ hổng khiến data file và WAL đồng thời không có mutation đã ACK**.

### 7.1. Memtable mất sau restart

Memtable nằm trong RAM nên không thể tự dùng làm bằng chứng durability. Nếu node chết trước khi flush, WAL còn phù hợp sẽ được replay để dựng lại state chưa vào SSTable.

### 7.2. Flush khác với compaction

**Flush** tạo SSTable từ memtable. **Compaction** hợp nhất/sắp xếp lại các SSTable và có thể thu hồi tombstone hoặc version cũ khi điều kiện an toàn. WAL cần được giữ cho tới khi dữ liệu đã có cấu trúc bền phù hợp; nó không nhất thiết phải chờ mọi compaction kết thúc.

### 7.3. Manifest quan trọng ngang dữ liệu

Nếu SSTable mới đã được ghi nhưng metadata còn chỉ tới SSTable cũ, engine phải biết file mới đã thuộc một trạng thái commit hợp lệ hay chưa. Một số engine dùng MANIFEST, CURRENT file, atomic rename và thứ tự sync để tạo trạng thái có thể phục hồi sau crash.

Nếu metadata nói SSTable mới đã tồn tại nhưng file chưa được ghi bền, recovery có thể thất bại. Vì thế thiết kế **write ordering của file và metadata** là một phần của durability, không chỉ log dữ liệu.

### 7.4. Xóa WAL segment phải xét nhiều memtable/column family

Một WAL segment có thể chứa mutation cho nhiều bảng hoặc column family. Nếu chỉ một bảng đã flush còn bảng khác chưa, segment vẫn có thể cần để phục hồi bảng còn lại. Điều kiện thu hồi log cần dựa trên **mốc bền của mọi nguồn dữ liệu được log chứa**, không chỉ tuổi segment hoặc một checkpoint đơn lẻ.

## 8. Checkpoint: làm ngắn thời gian phục hồi

Nếu mỗi lần restart phải replay toàn bộ WAL kể từ khi database được tạo, thời gian khởi động có thể tăng không giới hạn. **Checkpoint** ghi nhận một mốc trạng thái đủ bền để recovery không cần phát lại những log đã được bao phủ đầy đủ.

~~~text
WAL:
  LSN 100 -> ...
  LSN 101 -> ...
  LSN 102 -> ...
  LSN 103 -> ...
  LSN 104 -> ...
  LSN 105 -> ...

Checkpoint cho biết dữ liệu <= LSN 103 đã an toàn.

Recovery có thể cần replay phần log sau mốc liên quan,
theo semantics cụ thể của engine.
~~~

### 8.1. Checkpoint không nhất thiết chặn mọi ghi

Có engine dùng checkpoint nhất quán có tạm dừng một số hoạt động; có engine hỗ trợ **fuzzy checkpoint** khi ghi vẫn tiếp tục. Một checkpoint chỉ có ý nghĩa nếu metadata và dữ liệu nó tham chiếu được lưu theo protocol có thể phục hồi.

### 8.2. Thứ tự dọn WAL

Một quy trình khái niệm:

~~~text
1. Chọn dữ liệu/memtable đủ điều kiện flush.
2. Ghi data file và kiểm tra ghi bền.
3. Commit metadata/manifest chỉ tới file mới.
4. Cập nhật recovery watermark/checkpoint.
5. Tính các WAL segment không còn cần.
6. Chỉ sau đó rotate/recycle/delete segment theo policy.
~~~

Không đảo trình tự xóa log lên trước khi data file đã được xác nhận. Nếu crash giữa bước 2–3, hệ phải có quy tắc xử lý orphan file hoặc replay lại, không làm mất mutation.

### 8.3. Checkpoint và recovery time

Checkpoint quá ít có thể khiến WAL cần replay dài, tăng restart time. Checkpoint/flush quá thường xuyên có thể tăng I/O, write amplification và compaction pressure. Đây là tradeoff giữa **throughput khi chạy** và **thời gian phục hồi**.

## 9. Crash recovery: từ phát hiện sự cố đến phục vụ lại

Một quy trình phục hồi ở mức khái niệm:

~~~mermaid
flowchart TD
    START["Node restart"] --> META["Đọc manifest/checkpoint"]
    META --> FILES["Xác định data files hợp lệ"]
    FILES --> LOGS["Mở WAL segments cần replay"]
    LOGS --> VALID{"Record hợp lệ và thuộc phạm vi replay?"}
    VALID -->|Có| REPLAY["Replay theo thứ tự/transaction semantics"]
    REPLAY --> VALID
    VALID -->|Không hoặc hết| CHECK["Kiểm tra ranh giới cuối và consistency"]
    CHECK --> READY["Khôi phục service theo trạng thái hợp lệ"]
~~~

Sơ đồ giản lược. Một engine có thể chạy recovery analysis, redo, undo, xây lại index/memtable, repair metadata và điều phối replica trước khi mở ghi/đọc.

### 9.1. Xác định trạng thái bền gần nhất

Recovery không đơn giản bắt đầu từ log đầu tiên. Nó thường cần:

- Xác định data file hợp lệ từ manifest/snapshot/checkpoint.
- Kiểm tra log segment còn cần và thứ tự của chúng.
- Phát hiện những file mới chưa được commit vào metadata.
- Xác định transaction/mutation nào đã được commit.
- Xử lý record cuối bị ghi dở mà không làm mất record đã cam kết.

### 9.2. Replay phải đúng thứ tự và có thể lặp an toàn

Với mutation có quan hệ thứ tự:

~~~text
LSN 105: SET K=10
LSN 106: SET K=11
LSN 107: DELETE K
~~~

Replay sai thứ tự có thể làm bản ghi đã xóa xuất hiện trở lại. Engine thường dùng sequence/LSN và metadata để đảm bảo kết quả đúng theo model của nó.

Một replay có thể gặp record đã được áp dụng một phần trước crash. Bởi vậy recovery thường được thiết kế **idempotent hoặc có cách kiểm tra đã áp dụng theo sequence**, chứ không đơn thuần chạy lại mọi hiệu ứng phụ.

### 9.3. Redo lệnh “tăng 1” phải cẩn trọng

Nếu log chứa một thao tác `INCREMENT balance by 1` và recovery áp dụng hai lần mà không xác định record đã được áp dụng, kết quả sai. Cần dựa vào LSN, version, page LSN hoặc idempotent replay protocol. Trong một số thiết kế, log ghi **kết quả mới** thay vì lệnh cộng tùy ý để giảm nguy cơ.

### 9.4. Phân biệt replay storage với xử lý lại request

Replay WAL giúp dựng lại **trạng thái lưu trữ nội bộ**. Nó không có nghĩa hệ nên:

- Gửi lại email xác nhận mỗi khi restart.
- Gọi lại payment gateway không có idempotency.
- Phát event nghiệp vụ trùng không được kiểm soát.
- Trừ kho thêm lần nữa.

Các hiệu ứng bên ngoài cần workflow/outbox, command ID, consumer idempotency và đối soát riêng.

## 10. Những tình huống crash thường gặp

| Điểm xảy ra crash | Trạng thái có thể gặp | Điều cần thiết để recovery đúng |
|---|---|---|
| Trước khi tạo log record | Chưa có mutation được ghi | Không ACK sai như đã commit |
| Sau append vào RAM buffer | Log chưa bền; có thể mất | Đúng với mức durability đã chọn, không hứa mạnh hơn |
| Sau write vào OS cache, trước sync | Bytes có thể mất khi power failure | ACK phải theo durability policy |
| Sau log sync, trước memtable update | Log bền, RAM chưa phản ánh | Replay hoặc tiếp tục apply |
| Sau memtable update, trước SSTable flush | RAM mất khi crash | Replay log còn cần |
| Đang ghi SSTable | File có thể chưa hoàn tất | Checksum/manifest và orphan-file handling |
| Sau SSTable sync, trước manifest commit | Có thể có orphan SSTable | Manifest cũ + WAL còn đủ để khôi phục |
| Sau manifest commit, trước dọn WAL | Có data file và log cùng chứa mutation | Replay tránh double apply; sau đó dọn an toàn |
| Đang rotate log segment | Log tail hoặc metadata dang dở | Framing, checksum, recovery ordering |
| Sau ACK, trước replica nhận | Local durability có thể mạnh hơn replication | Recovery/failover theo write concern thực |

### 10.1. Process crash khác host crash

Kill tiến trình có thể giữ kernel và OS page cache còn sống; reboot cưỡng bức hoặc mất điện kiểm tra một lớp khác. Khi làm chaos test, phải gọi tên rõ loại fault, vì “đã sống sót sau process kill” không chứng minh “đã sống sót sau sudden power loss”.

### 10.2. Torn write và record bị cắt

Một ghi log có thể bị dừng giữa chừng, để lại phần đầu hợp lệ và phần đuôi thiếu. Length/checksum giúp phát hiện và xử lý theo protocol. Không nên chỉ parse đến đâu được đến đó rồi tự tuyên bố mọi dữ liệu đã ACK được khôi phục.

### 10.3. Hỏng log giữa file

Checksum sai ở giữa đoạn log đã đồng bộ có thể do corruption. Đây không chỉ là “bản ghi cuối chưa hoàn tất”. Cần cảnh báo nghiêm trọng, tìm bản sao/backup phù hợp và tránh tự động bỏ một dải mutation đã commit.

## 11. WAL, durability và consistency không đồng nghĩa nhau

Một node có WAL bền không có nghĩa các replica đều đã nhận trạng thái mới. Ngược lại, một ghi có thể được truyền tới nhiều node nhưng chỉ nằm ở RAM của họ, nên vẫn có rủi ro nếu các node mất điện đồng thời.

### 11.1. Ba câu hỏi riêng

1. **Durability:** sau lỗi nào thì thay đổi đã ACK còn tồn tại?
2. **Consistency/visibility:** reader thấy dữ liệu gì, ở thời điểm nào?
3. **Availability/failover:** node nào có thể tiếp tục phục vụ khi leader hoặc một vùng lỗi?

WAL thường tập trung vào **durability và crash recovery của storage engine**. Các giao thức replica/consensus giải quyết thêm câu hỏi về nhiều bản sao và thứ tự commit phân tán.

### 11.2. Các mốc ghi có thể khác nhau

~~~text
Leader:
  accepted -> appended -> locally durable

Replica:
  received -> appended -> locally durable -> applied

Cluster:
  replicated to quorum -> committed under consensus rule
~~~

Một protocol có thể định nghĩa commit khi log được lưu ở quorum, rồi áp dụng vào state machine sau. **Log committed** và **state applied** là hai mốc khác nhau trong nhiều hệ replication.

### 11.3. Không nhầm local ACK với quorum ACK

Nếu leader trả ACK ngay khi log local đã bền, nhưng node chết vĩnh viễn trước khi replicate, dữ liệu đó có thể không còn trong cluster còn sống. Nếu hệ đợi quorum có lưu log theo protocol, fault tolerance thường mạnh hơn với lỗi một node, đổi lại latency và availability khi quorum không đạt.

### 11.4. Quorum không phải phép màu

Quorum cần hiểu theo kiến trúc thực: số replica, các failure domain, điều kiện commit, durable vs volatile ACK, cùng quy tắc election/leader. Đa số phiếu trên cùng một nguồn điện hoặc một storage domain không thay thế được khả năng chịu lỗi vùng độc lập.

## 12. Log consensus khác WAL của engine như thế nào?

Trong một hệ sử dụng Raft hoặc một giao thức consensus tương tự, **replicated log** ghi các command được thống nhất thứ tự giữa node. Mỗi node có thể đồng thời dùng một WAL riêng để bảo vệ storage engine.

~~~mermaid
flowchart TD
    APP["Write request"] --> LEADER["Leader / consensus layer"]
    LEADER --> RLOG["Replicated log entry"]
    RLOG --> Q["Commit theo quy tắc quorum"]
    Q --> SM["Apply state machine"]
    SM --> ENGINE["Local storage engine"]
    ENGINE --> WAL[("Local WAL hoặc journal")]
~~~

Không phải mọi hệ có đủ hai log hoặc sắp xếp đúng thứ tự trên. Một số hệ tái sử dụng cùng cơ chế persistence; một số dùng log replication độc lập. Cần phân biệt **mục tiêu của log**:

- **WAL của engine:** bảo vệ cập nhật data file và phục hồi local.
- **Replication/consensus log:** đồng bộ thứ tự thay đổi giữa các node và phục hồi follower.
- **Change Data Capture/event log:** phân phối thay đổi tới consumer.
- **Audit log:** lưu dấu hoạt động phục vụ điều tra/kiểm toán.

Chúng có thể liên quan nhưng không tự đồng nghĩa.

### 12.1. Leader failover và những write đã ACK

Khi leader chết, hệ phải biết các entry nào đã được commit theo protocol, replica mới cần catch up ra sao và entry chưa commit có thể bị rollback như thế nào.

Nếu API công bố ACK mạnh hơn mức log/replica thực có, client có thể mất dữ liệu đã tưởng là thành công. Cần định nghĩa rõ khi nào hệ được phép trả thành công.

### 12.2. Follower đọc dữ liệu cũ

Một follower có thể đã nhận log entry nhưng chưa apply vào state machine, hoặc chưa nhận entry mới nhất. WAL bền của follower không tự bảo đảm **read-your-writes** hoặc linearizable read. Các cơ chế đọc cần protocol/consistency riêng.

## 13. Commit log trong một số họ NoSQL

Tên và cơ chế thay đổi giữa sản phẩm:

| Họ công nghệ | Mẫu thường gặp | Điểm cần xác minh |
|---|---|---|
| **Cassandra/ScyllaDB** | Commit log + memtable + SSTable | Sync mode, ACK/consistency, segment lifecycle, replay |
| **RocksDB và hệ dựa trên LSM** | WAL + memtable + SSTable/manifest | WriteOptions sync, disableWAL, flush/recovery và DB options |
| **MongoDB với WiredTiger** | Journal/transaction log hỗ trợ crash recovery | Journaling, write concern, majority semantics, checkpoint |
| **Redis** | AOF có thể ghi các lệnh thay đổi, ngoài RDB snapshot | AOF fsync policy, rewrite, durability khi lỗi, replication |
| **Hệ dùng replicated log** | Log consensus/replication và persistence local | Commit index, applied index, bền của replica, election |

Đây là **so sánh về kiến trúc**, không phải cam kết mọi phiên bản hoặc configuration hoạt động y hệt. Không nên xem các tên WAL, journal, commit log và AOF là hoàn toàn tương đương.

### 13.1. Cassandra-style commit log

Trong mô hình Cassandra, mutation thường được ghi vào commit log và memtable. Memtable được flush về SSTable; những đoạn commit log không còn cần cho recovery có thể được thu hồi theo ranh giới lưu trữ tương ứng.

Các cấu hình đồng bộ log và consistency level của write ảnh hưởng trực tiếp tới điểm ACK và khả năng sống sót sau lỗi. **Consistency level như quorum không tự định nghĩa toàn bộ semantics fsync local**; phải xem cả cấu hình và bảo đảm của phiên bản triển khai.

### 13.2. RocksDB-style WAL

RocksDB có WAL phục vụ phục hồi các write chưa flush ra SSTable. Tùy WriteOptions, thao tác có thể yêu cầu sync hoặc chọn bỏ WAL cho một số workload. Bỏ WAL có thể tăng throughput nhưng mở ra rủi ro mất thay đổi chưa được flush khi crash.

Phải đánh giá các lựa chọn sync, flush và multiple column families theo contract thực. Không nên bật disableWAL cho dữ liệu nghiệp vụ mà vẫn công bố durability như cũ.

### 13.3. MongoDB journaling

MongoDB với WiredTiger dùng cơ chế journal/recovery riêng. Chế độ write concern và yêu cầu journaling/majority ảnh hưởng kết quả ACK. Không nên tự suy từ một lần client nhận OK rằng ghi đã được durable trên quorum nếu application chưa xác định đúng write concern và cấu hình liên quan.

### 13.4. Redis AOF

AOF (*append-only file*) có thể lưu những lệnh ghi để khôi phục; RDB snapshot là một cơ chế khác. Các lựa chọn fsync của AOF có tradeoff giữa throughput và cửa sổ dữ liệu có thể mất. AOF rewrite và khôi phục khi file bị cắt cũng có semantics riêng.

Không nên coi một hệ dùng AOF là có transaction nhiều key bền vững giống nhau trong mọi topology, đặc biệt khi replication/failover và external effects tham gia.

## 14. WAL không tự bảo vệ toàn bộ transaction nghiệp vụ

Xét checkout:

~~~text
1. Update Order = CONFIRMED.
2. Decrement Inventory.
3. Call Payment gateway.
4. Send confirmation email.
~~~

WAL của database A có thể bảo vệ ghi Order tại A. Nó không tự commit nguyên tử Inventory ở database B, cuộc gọi Payment gateway và email.

### 14.1. Transaction đa mục chỉ trong phạm vi hỗ trợ

Một số NoSQL hỗ trợ transaction nhiều document/item. Khi dùng, phải xác định rõ:

- Những mục nào tham gia cùng transaction?
- Isolation và atomicity có bảo vệ invariant mong muốn không?
- Log/replication được đồng bộ đến mức nào trước ACK?
- Timeout giữa chừng được xử lý thế nào?
- Transaction đụng nhiều partition/region có giới hạn gì?

### 14.2. Transactional outbox

Một vấn đề phổ biến: Order đã commit, nhưng worker chết trước khi phát event `OrderConfirmed`.

~~~text
Trong transaction nguồn (nếu được hỗ trợ):
    update Order
    insert OutboxEvent(OrderConfirmed, eventId)
COMMIT

Publisher:
    đọc outbox đã commit
    phát event có thể lặp

Consumer:
    xử lý event idempotently
~~~

WAL giúp database bảo vệ transaction chứa Order và outbox trong phạm vi của nó. Nó **không** khiến publisher gửi message đúng một lần tuyệt đối, nên consumer cần idempotency.

### 14.3. Saga và recovery

Một workflow nhiều hệ có thể lưu trạng thái bền (`RESERVING`, `PAYING`, `CANCELING`) và replay command/event theo idempotency. Sau crash, phục hồi WAL giúp dựng lại trạng thái workflow, rồi orchestration tiếp tục những bước chưa hoàn tất. Recovery storage và recovery nghiệp vụ là **hai lớp riêng nhưng phải phối hợp**.

## 15. Idempotency và tính đúng đắn khi replay

Client có thể gửi cùng request hai lần vì mất ACK. Node cũng có thể replay WAL sau crash. Hai trường hợp cần phân biệt:

1. **Replay nội bộ storage:** áp dụng log record để dựng lại state đã được commit đúng một lần về mặt logic.
2. **Retry command từ bên ngoài:** cùng yêu cầu nghiệp vụ có thể được gửi lặp, phải nhận diện bằng idempotency key hoặc transaction ID.

### 15.1. Một command có định danh ổn định

~~~json
{
  "commandId": "reserve-7281",
  "sku": "SKU-A",
  "quantity": 2,
  "orderId": "O-100"
}
~~~

Tại Inventory, nguồn có thẩm quyền cần ghi nhận kết quả commandId cùng thay đổi số lượng hoặc dùng một transaction/giao thức tương đương.

~~~text
reserve(commandId, sku, qty):
    if commandId already committed:
        return recordedResult

    atomically if available >= qty:
        decrease available
        record commandId -> RESERVED
        return RESERVED

    return INSUFFICIENT_STOCK
~~~

Nếu ghi reservation result và giảm số tồn nằm trên hai record nhưng không được bảo vệ chung, retry sau crash vẫn có thể gây sai. Có WAL không tự sửa được lỗ hổng transaction nghiệp vụ này.

### 15.2. LSN không thay thế commandId

LSN nhận diện record trong log storage. Một command bị gửi lại có thể tạo **hai log record với hai LSN khác nhau**. Vì vậy cần idempotency ở tầng domain nếu hai log record biểu diễn cùng một ý định.

### 15.3. Replay không phải re-execute external side effects

Nếu log lưu `OrderConfirmed`, recovery không được mặc nhiên gọi lại gateway thu tiền. Cần sử dụng kết quả paymentId đã lưu hoặc truy vấn đối soát gateway theo idempotency key.

## 16. WAL retention, segment rotation và dọn log

WAL chiếm không gian và không thể tăng mãi. Engine thường rotate và thu hồi segment khi đủ điều kiện.

### 16.1. Điều kiện an toàn để dọn

Tùy engine, cần tính:

- Mutation đã được flush thành data file bền.
- Checkpoint/manifest đã commit đúng.
- Transaction còn mở có cần log cũ không?
- Backup/PITR cần giữ log đến mốc nào?
- Replica nào còn phụ thuộc vào log để catch up?
- Change stream/CDC có retention riêng không?

Nếu một replica bị offline lâu, nguồn có thể không thể giữ log vô hạn. Khi log cần thiết đã bị dọn, replica có thể phải nhận snapshot/repair thay vì catch up từng entry.

### 16.2. Không nhầm TTL dữ liệu với TTL log

Một record nghiệp vụ hết TTL không nhất thiết khiến log entry liên quan được xóa ngay. Ngược lại, WAL entry có thể được thu hồi sau khi dữ liệu đã flush, dù bản ghi nghiệp vụ cần giữ nhiều năm.

**Vòng đời của log** phụ thuộc nhu cầu crash recovery, checkpoint, replication và backup; **vòng đời của dữ liệu** phụ thuộc quy tắc nghiệp vụ/retention.

### 16.3. Disk full và write stall

Nếu ổ chứa WAL đầy, hệ không nên tiếp tục ACK các write mà không còn chỗ lưu bền theo contract. Nó có thể từ chối ghi, backpressure hoặc chuyển sang chế độ chỉ đọc tùy thiết kế.

Những nguyên nhân khiến WAL không dọn được:

- Flush/compaction bị chậm.
- Storage throughput thấp hơn tốc độ ingest.
- Checkpoint không tiến.
- Replica/cơ chế backup giữ log lâu.
- Transaction hoặc snapshot lâu làm pin retention.
- Lỗi dọn segment hoặc permissions.

Khi xử lý disk full, **không xóa thủ công WAL segment có vẻ cũ** nếu chưa được engine xác nhận an toàn. Hành động đó có thể phá recovery.

## 17. WAL, snapshot và point-in-time recovery

WAL live chủ yếu phục vụ **khôi phục node/engine sau crash**. Muốn phục hồi sau xóa nhầm, corruption hoặc sự cố toàn cluster, cần **backup/snapshot độc lập** và có thể cần archive log liên tục.

Một chiến lược PITR khái niệm:

~~~text
T0: Snapshot nhất quán với mốc log S0.
T1: Archive đầy đủ log sau S0.
T2: Có sự cố/xóa nhầm.
T3: Khôi phục snapshot T0.
T4: Replay các log cần thiết tới mốc mục tiêu T*.
T5: Kiểm chứng trạng thái và mở service.
~~~

~~~mermaid
flowchart LR
    SNAP["Consistent snapshot @ S0"] --> RESTORE["Restore snapshot"]
    LOG["Archived WAL segments S0..S*"] --> REPLAY["Replay to target point"]
    RESTORE --> REPLAY
    REPLAY --> VERIFY["Verify data and application invariants"]
    VERIFY --> OPEN["Reopen service"]
~~~

### 17.1. Snapshot phải tương thích log

Nếu snapshot không ghi lại chính xác log position/transaction boundary, replay có thể thiếu hoặc áp dụng trùng mutation. Với hệ phân tán nhiều partition, cần bảo đảm snapshot và các log stream có ranh giới nhất quán theo protocol sản phẩm.

### 17.2. Không được có lỗ hổng trong chuỗi log

Để phục hồi từ S0 tới S*, cần có các log segment liên tục, đúng thứ tự và hợp lệ. Nếu thiếu một phần, không thể đơn giản nhảy qua rồi coi trạng thái là chính xác.

### 17.3. WAL live không phải backup

Nếu WAL và data files nằm trên cùng thiết bị bị hỏng, cả hai có thể mất. Một bản backup cần nằm ở failure domain phù hợp, có mã hóa, phân quyền, retention và kiểm thử restore.

### 17.4. Restore có thể hồi sinh dữ liệu đã xóa hợp lệ

Nếu backup ở thời điểm trước một deletion request, khôi phục backup cũ có thể đưa lại record đã xóa. Cần quy trình áp dụng lại quyết định xóa, deletion ledger/tombstone phù hợp và kiểm tra trước khi mở dữ liệu cho truy cập rộng.

## 18. RPO, RTO và durability contract

**RPO (Recovery Point Objective)** là mức mất dữ liệu tối đa chấp nhận được theo mốc thời gian hoặc trạng thái. **RTO (Recovery Time Objective)** là thời gian khôi phục dịch vụ mục tiêu.

Ví dụ hai sản phẩm:

| Trường hợp | Mục tiêu | Thiết kế cần cân nhắc |
|---|---|---|
| Session cache có thể tạo lại | Có thể mất một phần state khi node chết | Durability có thể nhẹ, TTL và regeneration |
| Order/Inventory đã ACK | Không được mất những thay đổi theo cam kết | Durable log + write concern/failover phù hợp |
| Telemetry có thiết bị gửi lại | Có thể chấp nhận cửa sổ dữ liệu cần replay từ nguồn | Log sync và ingest retry theo contract |
| Audit trail bắt buộc giữ | RPO rất chặt, cần phục hồi và kiểm toán | Durable writes, replication, backup, access controls |

### 18.1. Số liệu chỉ minh họa

Giả sử hệ sync log mỗi khoảng 1 giây và ACK trước sync. Khi mất điện, **có thể** mất các thao tác gần thời điểm crash nằm trong cửa sổ chưa bền; nhưng không thể khẳng định chính xác “mất tối đa 1 giây” chỉ từ cấu hình mà không xem scheduler, backlog, filesystem và ACK semantics.

Nếu mỗi write phải đợi sync/replication đạt mốc cần thiết trước ACK, cửa sổ rủi ro với lỗi tương ứng có thể nhỏ hơn, đổi lại latency và availability.

### 18.2. Recovery time phụ thuộc kích thước log và việc rebuild

RTO không chỉ là thời gian process restart. Nó có thể gồm:

~~~text
Restart / leader election
  + đọc checkpoint/manifest
  + replay WAL
  + rebuild memtable/index cần thiết
  + catch up replica
  + kiểm tra consistency
  + làm ấm cache
  + cho traffic trở lại
~~~

WAL replay dài hoặc disk I/O chậm có thể khiến RTO tăng đáng kể. Vì vậy cần đo **khởi động từ trạng thái crash thật**, không chỉ đo thời gian chạy command khởi động service.

## 19. Tradeoff hiệu năng: sync, batching và group commit

Ghi log tuần tự vẫn có chi phí I/O và đồng bộ. Cơ chế durability mạnh hơn thường khiến mỗi lần ghi phải chờ nhiều hơn.

### 19.1. Flush từng request

Với mỗi request:

~~~text
append log -> sync log -> ACK
~~~

Điều này có thể giảm cửa sổ ghi chưa bền, nhưng nếu mỗi request chịu một sync riêng, throughput bị giới hạn bởi chi phí flush.

### 19.2. Group commit

Thay vì sync riêng từng request, engine có thể gom nhiều log record:

~~~text
Request A -> append LSN 100
Request B -> append LSN 101
Request C -> append LSN 102

Sync log tới >= LSN 102

ACK A, B, C theo protocol
~~~

Một lần sync phục vụ nhiều request, giảm chi phí trung bình. Đánh đổi là thời gian chờ batch, scheduler, queue depth và p99. **Group commit không nhất thiết làm durability yếu đi** nếu các ACK chỉ được gửi sau mốc sync/commit mà policy yêu cầu.

### 19.3. Sync theo chu kỳ

Một số cấu hình cho phép ACK trước sync và đồng bộ theo khoảng thời gian. Cách này có thể tăng throughput nhưng tạo cửa sổ dữ liệu đã ACK chưa bền khi gặp host/power failure. Phải công bố đúng RPO và kiểm thử.

### 19.4. Bỏ WAL

Một số engine cho phép disable WAL cho một workload, ví dụ dữ liệu có thể tạo lại hoặc ingestion đã có nguồn replay khác. Đây là một lựa chọn **đánh đổi độ bền lấy throughput**, không phải tối ưu “miễn phí”.

Nếu dữ liệu nghiệp vụ không thể tạo lại, tắt WAL mà vẫn trả ACK như đã durable là sai contract.

### 19.5. Tốc độ append không chỉ phụ thuộc disk MB/s

Các yếu tố ảnh hưởng:

- Kích thước mỗi log record.
- Tần suất sync/flush.
- Group commit batch size và wait time.
- Số writer/partition/hot key.
- Checksum và serialization cost.
- Compression/encryption.
- Replication round-trip.
- Backpressure khi flush/compaction.
- Storage latency p95/p99 và controller cache.

Benchmark phải nhìn cả **throughput lẫn tail latency và khả năng phục hồi**, không chỉ số write/s ở trạng thái ổn định.

## 20. Dữ liệu sai và corruption: WAL không phải giải pháp tuyệt đối

WAL bảo vệ trước một số dạng crash, không làm biến mất mọi lỗi dữ liệu.

### 20.1. Logic sai vẫn có thể được log bền

Nếu ứng dụng ghi sai giá tiền hoặc cập nhật nhầm tenant và thao tác đã commit, WAL sẽ giúp giữ sai sót ấy bền vững. Khôi phục từ WAL không tự sửa logic nghiệp vụ.

### 20.2. Corruption trên log và data file

Khi thiết bị lưu trữ lỗi, WAL hoặc SSTable đều có thể hỏng. Cần checksum, cảnh báo, replica/backup và quy trình repair. Không nên coi WAL là bản sao độc lập hoàn toàn khi nó cùng nằm trên thiết bị với data files.

### 20.3. Silent data corruption

Một lỗi phần cứng hoặc phần mềm có thể làm sai bytes mà không crash ngay. Checksum ở record/file, scrubbing, backup verification và replication repair giúp phát hiện hoặc phục hồi tùy kiến trúc.

### 20.4. Malware/ransomware và xóa nhầm

Nếu một tiến trình có quyền ghi phá cả WAL và data file, WAL cục bộ chưa đủ. Cần backup ở failure domain và quyền khác, chính sách retention/versioning và kiểm thử phục hồi.

## 21. Bảo mật và vòng đời dữ liệu trong log

WAL có thể chứa **dữ liệu nhạy cảm đã bị cập nhật hoặc xóa khỏi bảng chính**. Ví dụ thay email người dùng từ địa chỉ cũ sang mới, log vẫn có thể chứa mutation liên quan địa chỉ cũ trong một thời gian.

### 21.1. Mã hóa log và backup

Cần đánh giá:

- Encryption at rest cho WAL, snapshot và archive.
- Mã hóa khi truyền log tới replica/backup.
- Quyền đọc log, file permissions và audit.
- Quản lý khóa và rotation.
- Chính sách xử lý log khi xóa subject.
- Ngăn log debug hoặc crash dump ghi lộ payload nhạy cảm.

Không nên cho rằng dữ liệu đã xóa khỏi document hiện tại thì không còn ở WAL, backup hoặc replica.

### 21.2. TTL dữ liệu khác retention log

Dữ liệu session có TTL 15 phút nhưng log hoặc snapshot có thể tồn tại lâu hơn theo chính sách lưu. Hệ cần quy định thời hạn và cơ chế bảo vệ phù hợp, không mặc định TTL của bản ghi sẽ tự xóa mọi bản sao.

### 21.3. WAL và cryptographic erasure

Trong một số hệ có mã hóa theo đơn vị phù hợp, hủy khóa có thể giảm khả năng giải mã ciphertext còn lưu. Nhưng điều này chỉ có ý nghĩa khi không còn plaintext/key copy khác và chính sách quản lý khóa hỗ trợ. Nó không thay thế việc kiểm kê log, backup và các bản dẫn xuất.

## 22. Thiết kế khả năng quan sát WAL và recovery

Một hệ có WAL nhưng thiếu observability có thể phát hiện quá muộn rằng log đang tăng vô hạn hoặc recovery sau crash mất hàng giờ.

| Nhóm | Chỉ số nên theo dõi | Ý nghĩa |
|---|---|---|
| Log write | WAL append throughput, bytes/s, records/s | Tải ghi log |
| Sync | fsync/fdatasync p50/p95/p99, sync backlog | Độ trễ durability |
| ACK | Write latency và write concern failures | Client được xác nhận ở mốc nào |
| Segments | Số segment, tổng bytes, oldest needed LSN | Log có tăng bất thường không |
| Checkpoint | Tuổi checkpoint, durable watermark | Recovery phải replay bao xa |
| Flush | Memtable flush duration, pending flush | Dữ liệu chính có theo kịp ingest |
| Compaction | Backlog, write amplification, disk headroom | Áp lực storage |
| Replay | Records replayed, recovery duration, replay failures | Khả năng phục hồi thực |
| Corruption | Checksum errors, truncated records, disk faults | Rủi ro mất tính đúng đắn |
| Replication | Leader/follower log lag, committed vs applied index | Bản sao có theo kịp không |
| Backup | Archived log gaps, snapshot age, restore drill | PITR có khả thi không |
| Capacity | WAL disk free, write stalls, ENOSPC | Tránh mất khả năng ghi |

### 22.1. Cảnh báo theo xu hướng, không chỉ dung lượng hiện tại

Nếu WAL sinh 100 GB/giờ nhưng chỉ thu hồi 50 GB/giờ, dung lượng sẽ tăng mãi dù hôm nay còn nhiều đĩa. Nên giám sát **tốc độ sinh, tốc độ dọn, segment già nhất và dự đoán thời gian đầy đĩa**.

### 22.2. Recovery time phải được đo

Chạy restore/crash test có kiểm soát để đo:

- Thời gian từ restart đến trạng thái ready.
- Số log record/byte phải replay.
- Có thiếu/dư mutation đã ACK không.
- Có orphan file/manifest error không.
- Replica cần catch up bao lâu.
- Cache warming có làm tăng latency sau khi lên không.

### 22.3. Không log dữ liệu bí mật để debug WAL

Log engine hoặc ứng dụng có thể chứa key/value nhạy cảm. Metric thường chỉ cần kích thước, LSN, checksum state, aggregate ID đã được bảo vệ, chứ không cần in toàn bộ payload cá nhân/token.

## 23. Một ví dụ Java về hợp đồng durability

Để nhấn mạnh API chứ không tự viết một storage engine production, ta mô hình hóa kết quả ghi:

~~~java
public record WriteRequest(
    String tenantId,
    String key,
    String value,
    String commandId
) {}

public enum DurabilityLevel {
    MEMORY_ACK,
    LOCAL_DURABLE,
    REPLICATED_DURABLE
}

public record WriteReceipt(
    String commandId,
    long sequence,
    DurabilityLevel achieved
) {}

public interface DurableKeyValueStore {
    WriteReceipt put(
        WriteRequest request,
        DurabilityLevel required
    ) throws StorageUnavailableException;
}

class StorageUnavailableException extends Exception {
    StorageUnavailableException(String message) {
        super(message);
    }
}
~~~

Interface này chỉ là **mẫu để thảo luận hợp đồng**, không khẳng định các database hiện có hỗ trợ đúng ba level đó hoặc mọi cluster có thể ACK theo `REPLICATED_DURABLE`.

### 23.1. Tại sao cần receipt?

Một response có thể chứa commandId, sequence và mốc durability đã đạt để ứng dụng biết điều gì được cam kết. Nhưng **receipt không phải bằng chứng tuyệt đối nếu implementation trả sai**; giá trị của nó phụ thuộc protocol DB và kiểm thử lỗi thực.

### 23.2. Pseudocode một log writer đơn giản

~~~text
write(command):
    validate command and idempotency
    append framed record with sequence and checksum
    request sync according to required durability
    await required durable/replication boundary
    apply/confirm mutation in state machine
    return receipt
~~~

Đây là mô hình khái niệm. Một storage engine thật còn phải xử lý concurrent writers, ordering, group commit, checkpoint, transaction record, crash recovery, checksum, metadata atomicity, disk full và corruption. **Không nên dùng pseudocode này để tự triển khai WAL production.**

### 23.3. Thao tác có điều kiện vẫn cần riêng

WAL không thay thế CAS:

~~~text
UPDATE Inventory
IF available >= requestedQty
THEN decrease available
~~~

Ngay cả khi cả hai write được lưu log bền, nếu logic không kiểm tra điều kiện nguyên tử thì hệ vẫn có thể bền vững lưu lại một trạng thái sai.

## 24. Case study: sự cố mất điện giữa ghi Order

Giả sử một dịch vụ Order dùng engine LSM với WAL. Lúc 10:00:00:

~~~text
Order O-100:
    status = PENDING
    version = 7
~~~

Client gửi:

~~~json
{
  "commandId": "confirm-9001",
  "orderId": "O-100",
  "expectedVersion": 7,
  "action": "CONFIRM"
}
~~~

Một trình tự khái niệm:

| Mốc | Sự kiện |
|---|---|
| T1 | Engine kiểm tra version/status theo transaction/conditional write |
| T2 | Append mutation vào WAL |
| T3 | WAL đạt mốc durability cần thiết |
| T4 | Mutation hiện diện trong memtable/state machine |
| T5 | ACK với commandId và version 8 |
| T6 | Mất điện trước khi memtable flush ra SSTable |
| T7 | Restart, recovery replay log cần thiết |
| T8 | Order trở lại CONFIRMED version 8 |

Nếu mô hình durability đã yêu cầu local sync trước ACK, một **process/host crash thuộc fault model được hỗ trợ** sau T5 phải để lại đủ log hoặc state để dựng lại update. Nếu hệ ACK ngay ở log buffer thì có thể mất update khi mất điện; đó là khác biệt về cam kết, không thể che bằng câu “database có commit log”.

### 24.1. Client không nhận ACK

Nếu mất điện ngay sau T3/T4 nhưng trước T5, client không biết lệnh đã commit chưa. Khi thử lại cùng commandId, Order service cần idempotency hoặc một kết quả đối soát:

~~~text
confirm-9001 đã được thực hiện:
    return existing confirmation

confirm-9001 chưa được thực hiện:
    evaluate state and attempt command safely
~~~

Version 8 chỉ cho biết state đã thay đổi, không mặc nhiên cho biết *chính command nào* đã thực hiện thay đổi nếu hệ không lưu commandId.

### 24.2. Saga còn Payment/Inventory

Khôi phục Order CONFIRMED không có nghĩa Payment gateway đã hoàn tất hoặc Inventory được giữ. Cần lưu trạng thái workflow riêng và đối soát từng aggregate. WAL chỉ giúp nguồn Order phục hồi phần state nó đã commit.

## 25. Case study: ingest telemetry cần throughput cao

Một hệ nhận 100.000 event/s. Nguồn thiết bị có thể gửi lại sự kiện trong 24 giờ, và dữ liệu được chuyển vào durable queue trước khi ghi NoSQL.

Có hai hướng kiến trúc cần đánh giá:

1. **NoSQL write đòi durability mạnh trước ACK:** ít rủi ro mất dữ liệu tại tầng NoSQL, nhưng sync/replication có thể tăng latency và giảm throughput.
2. **NoSQL write được ACK ở mốc yếu hơn, có durable upstream log:** có thể tăng throughput nhưng phải có giao thức replay, idempotency và cách đối soát để không mất sự kiện trong khoảng lỗi.

Không thể chọn phương án 2 chỉ bằng câu “upstream đã có queue”. Cần chứng minh:

- Queue ACK có bảo đảm bền và retention phù hợp.
- Consumer checkpoint chỉ tiến sau mốc ghi NoSQL phù hợp.
- Replay cùng eventId không tạo duplicate logical event.
- NoSQL không ACK sai khi downstream chưa đủ bền.
- Có khả năng catch up sau thời gian downtime lớn nhất.

### 25.1. Checkpoint của consumer khác checkpoint storage

Consumer offset trong message broker chỉ cho biết đã xử lý đến đâu theo workflow ingestion. Storage checkpoint/WAL LSN cho biết data file được bảo vệ tới mốc nào. Hai thứ cần phối hợp theo contract, không tự đồng nhất.

### 25.2. Nếu noSQL mất phần dữ liệu đã ACK

Khi replay từ durable queue, phải biết event nào còn thiếu. Dùng eventId stable, conditional insert/idempotency và đối soát sequence có thể giúp tái tạo, nhưng chỉ khi queue còn dữ liệu và checkpoint consumer không đi quá mức an toàn.

## 26. Kiểm thử sự cố: đừng chỉ test happy path

Một bộ kiểm thử durability cần nêu rõ fault model. Các tình huống:

### 26.1. Process kill trước và sau ACK

1. Ghi N record với unique commandId.
2. Kill tiến trình tại thời điểm ngẫu nhiên trước/sau ACK.
3. Restart và đếm record được khôi phục.
4. Đảm bảo mọi thao tác **đã ACK ở mức durability tương ứng** còn tồn tại trong fault model hỗ trợ.
5. Những thao tác chưa ACK có thể hoặc không có; ứng dụng phải hỗ trợ unknown outcome.

### 26.2. Host reboot/power failure

Process kill không đủ kiểm tra fsync. Cần môi trường test có thể mô phỏng reboot cưỡng bức hoặc mất điện một cách an toàn, trong giới hạn hạ tầng test. So sánh kết quả với contract theo từng sync policy.

### 26.3. Crash giữa flush và manifest update

Thử kill sau khi SSTable được ghi nhưng trước khi metadata commit, và ngược lại theo các điểm chèn lỗi engine cho phép. Recovery không được mất mutation đã ACK hoặc nhận file chưa hoàn chỉnh là hợp lệ.

### 26.4. WAL tail bị cắt

Mô phỏng một record cuối chưa hoàn chỉnh. Recovery cần phát hiện qua framing/checksum và xử lý theo protocol. Không được mất những record đã commit trước đó.

### 26.5. Corruption giữa segment

Mô phỏng checksum sai ở giữa vùng log đã được xem là bền. Hệ phải báo lỗi/khôi phục từ replica hoặc backup nếu có, không âm thầm bỏ qua.

### 26.6. Disk full

Làm đầy ổ WAL trên test node. Kiểm tra hệ ngừng ACK theo mức durability nếu không thể lưu bền, xử lý lỗi rõ ràng và phục hồi khi có dung lượng trở lại.

### 26.7. Flush/compaction backlog

Giới hạn I/O để memtable flush chậm. Theo dõi WAL growth, write stalls và recovery time. Xác minh hệ dùng backpressure thay vì dọn segment khi chưa an toàn.

### 26.8. Replica chết và leader failover

Cho leader ACK theo write concern đã chọn, rồi làm node chết. Kiểm tra leader mới còn tất cả thao tác phải được giữ theo fault model, và follower catch up đúng thứ tự.

### 26.9. PITR với log archive bị thiếu một segment

Restore snapshot cùng log thiếu một khoảng. Hệ không được tuyên bố đã khôi phục chính xác tới target time khi log chain không đủ. Cần báo giới hạn RPO hoặc chọn snapshot/log khác.

### 26.10. Restore sau deletion request

Khôi phục bản backup trước khi một user bị xóa hợp lệ. Kiểm tra workflow xử lý deletion ledger/retention và chặn dữ liệu bị xóa xuất hiện lại trái chính sách.

## 27. Những ngộ nhận thường gặp

### “Đã bật WAL thì không thể mất bất kỳ ghi nào”

Độ bền phụ thuộc mốc ACK, sync mode, storage, replication và fault model. Ghi chỉ nằm trong buffer vẫn có thể mất khi crash.

### “write() thành công nghĩa là đã ở đĩa”

Không nhất thiết. Bytes có thể mới nằm trong OS page cache. Cần hiểu fsync hoặc cơ chế tương đương.

### “fsync một file bảo đảm mọi metadata rename cũng bền”

Không mặc định trên mọi hệ; thứ tự sync file/directory/manifest cần đúng.

### “WAL luôn được ghi trước khi memtable RAM thay đổi”

Quy tắc write-ahead nói về ranh giới dữ liệu bền và recovery. Một số engine buffer hoặc sửa RAM trước log sync nhưng vẫn quản lý commit/visibility an toàn.

### “Dữ liệu đã flush ra SSTable thì có thể xóa mọi WAL ngay”

Không nếu metadata chưa commit, các memtable khác còn phụ thuộc segment, transaction/replica/backup cần log hoặc checkpoint chưa an toàn.

### “Compaction và flush là một”

Flush chuyển memtable thành data file; compaction hợp nhất data file và quản lý version/tombstone.

### “WAL là backup đầy đủ”

Không. WAL live có thể cùng failure domain với data file và không bao phủ mọi lỗi/xóa nhầm. PITR cần snapshot phù hợp và log chain liên tục.

### “Có quorum thì mọi replica đã apply dữ liệu”

Một consensus log có thể committed trước khi state machine apply ở mọi follower. Read consistency là quyết định riêng.

### “Có local durable ACK thì failover luôn giữ được ghi”

Nếu leader chết vĩnh viễn trước khi replicate và contract chỉ yêu cầu local durability, dữ liệu có thể không có trên node còn sống.

### “WAL replay gửi lại email cũng không sao”

Replay storage không được tự thực thi external side effects. Email/payment cần idempotency và workflow.

### “LSN chính là idempotency key nghiệp vụ”

Retry một command có thể tạo nhiều log entries/LSN; cần commandId riêng.

### “Dùng TTL 7 ngày thì WAL chứa record đó cũng bị xóa đúng ngày 7”

Retention log phục vụ recovery/replication/backup, không đồng nghĩa TTL của business record.

### “Không cần test power loss vì kill process đã đủ”

Process kill có thể để OS page cache tồn tại. Hai fault model khác nhau.

### “Chỉ cần thêm node là ghi WAL nhanh hơn”

Một hot partition hoặc một storage device bị giới hạn sync/IOPS vẫn có thể là bottleneck. Phải đo tail latency và điểm nghẽn.

### “Recovery thành công nghĩa là mọi dữ liệu đúng”

Engine có thể khôi phục bền một update sai nghiệp vụ. Cần validation, constraints, đối soát và backup.

## 28. Quy trình thiết kế durability cho một NoSQL workload

1. **Xác định loại dữ liệu:** có thể tạo lại không? Mất một bản ghi đã ACK gây hậu quả gì?
2. **Định nghĩa fault model:** process crash, host mất điện, disk failure, node permanent loss, region outage.
3. **Chốt RPO/RTO:** cửa sổ mất dữ liệu và thời gian phục hồi được chấp nhận.
4. **Chọn mốc ACK:** append, local sync, replica ACK hay quorum durable theo tính năng thực.
5. **Xác minh WAL/commit log:** format, sync policy, segment rotation và phạm vi transaction.
6. **Thiết kế data file/checkpoint:** flush, manifest, LSN watermark và retention log.
7. **Thiết kế replication:** consistency, failure domain, leader failover, catch-up và rollback.
8. **Thiết kế idempotency:** commandId, duplicate detection, unknown outcome.
9. **Thiết kế backup/PITR:** snapshot nhất quán, log archive, restore và retention.
10. **Bảo vệ bảo mật:** encryption, quyền truy cập log, retention của dữ liệu nhạy cảm.
11. **Benchmark:** throughput và p95/p99 của append/sync/write/restore.
12. **Fault injection:** kiểm thử crash ở các ranh giới ACK/flush/checkpoint.
13. **Giám sát production:** disk headroom, oldest needed log, checkpoint lag và recovery metrics.

### 28.1. Mẫu bản ghi quyết định

~~~text
Data category: order_events
Owner: Order Service
Source of truth: Order aggregate store
Business invariant: confirmed state cannot be silently lost

Durability:
  requiredAckBoundary = per deployed DB write concern
  supportedFaultModel = process/host crash plus selected node failures
  WAL enabled = yes
  sync/replication policy = explicitly configured and verified

Storage:
  WAL segments rotated by engine
  memtable flush -> SSTable
  manifest/checkpoint updates verified before log deletion

Recovery:
  replay from safe checkpoint
  records checked for corruption/truncation
  commandId used for external retries
  outbox/consumer idempotency for downstream effects

Backup/PITR:
  separate snapshot and archived logs
  periodic restore tests and log-chain verification

Monitoring:
  WAL bytes, oldest LSN needed, fsync p99
  flush backlog, replay duration, replication lag
  disk headroom and unknown-outcome writes
~~~

Không sao chép mẫu này máy móc cho cache hoặc một hệ NoSQL cụ thể; các giá trị RPO/RTO và mốc ACK phải dựa vào nhu cầu cùng bảo đảm sản phẩm.

## 29. Bài tập thực hành

### Bài 1 — ACK trước sync

Một engine append WAL vào OS page cache rồi trả ACK. Cứ khoảng 500 ms nó mới sync log.

Yêu cầu:

1. Phân biệt process kill và power failure.
2. Giải thích vì sao ACK không đồng nghĩa đã bền qua mất điện.
3. Đề xuất cách tăng durability và tác động tới p99 latency.
4. Vì sao không thể khẳng định chính xác RPO chỉ từ cấu hình chu kỳ sync?

### Bài 2 — Crash trước flush

Order O-100 version 7 được cập nhật thành version 8, WAL đạt mốc bền yêu cầu và client đã ACK. Memtable chưa flush thì node chết.

Hãy mô tả các bước recovery, điều kiện replay và kết quả mong đợi sau restart.

### Bài 3 — Flush thành công nhưng chưa cập nhật manifest

Một SSTable mới đã ghi ra disk, nhưng worker chết trước khi manifest trỏ tới nó.

Giải thích vì sao không thể xóa WAL sớm, cách xử lý orphan SSTable và cách xác định mốc checkpoint an toàn.

### Bài 4 — WAL segment chứa nhiều column family

Segment 42 chứa mutation cho collection A và B. A đã flush đầy đủ, B chưa flush.

Có được xóa segment 42 không? Hãy nêu điều kiện cần kiểm tra và cách theo dõi oldest needed LSN.

### Bài 5 — Transaction và replay

Transaction ghi hai record, nhưng engine chết sau khi ghi một phần thay đổi vào data file và trước commit marker.

Phân tích khi nào cần undo/redo, và vì sao một engine LSM có thể tổ chức recovery khác engine định hướng page.

### Bài 6 — Group commit

Có 1.000 request/s, mỗi request tạo log record nhỏ. Một cấu hình sync mỗi request, cấu hình khác group commit 20 request rồi sync.

Hãy so sánh chi phí fsync trung bình, latency batch, ảnh hưởng tail latency và điều kiện để cả hai cùng đạt durability mạnh.

### Bài 7 — Local durability vs quorum

Leader ghi log bền local và ACK, nhưng chưa replicate. Leader sau đó hỏng vĩnh viễn.

Hãy phân tích khả năng mất write trên cluster còn lại. Thiết kế ACK khác nếu muốn chịu lỗi một node theo topology phù hợp.

### Bài 8 — Timeout sau commit

Client gửi ReserveStock với reservationId R-1. Database đã commit và ghi WAL nhưng response timeout, client thử lại.

Vì sao WAL không tự ngăn trừ kho hai lần? Thiết kế idempotency dựa trên reservationId và cách đối soát outcome.

### Bài 9 — PITR thiếu log segment

Có snapshot tại LSN 1000, log archive từ 1001 đến 1200, nhưng segment chứa 1100–1120 bị mất. Hãy giải thích vì sao không thể tuyên bố phục hồi chính xác tới 1200 và đề xuất các biện pháp phát hiện/tránh log-gap.

### Bài 10 — Corruption giữa WAL

Recovery gặp một record checksum sai ở giữa segment có các entry đã ACK. Tại sao không nên bỏ qua record rồi tiếp tục? Khi nào có thể phục hồi từ replica/backup và cần báo trạng thái gì?

### Bài 11 — Hotspot và disk full

Một node tạo WAL 150 MB/s nhưng flush/cleanup chỉ giải phóng trung bình 90 MB/s.

Hãy xác định xu hướng dung lượng, các metric cần cảnh báo, biện pháp backpressure và vì sao xóa thủ công log cũ có thể phá recovery.

### Bài 12 — Dữ liệu nhạy cảm

Một user đã yêu cầu xóa profile. Document chính đã xóa nhưng WAL archive và backup cũ có thể chứa thông tin đó.

Hãy xây dựng data inventory các bản sao, xác định cơ chế giữ/xóa theo policy áp dụng và giải thích giới hạn của soft delete hoặc crypto-erasure.

---

**Kết luận:** Write-ahead log/commit log là một trong những nền tảng giúp NoSQL **khôi phục những thay đổi đã được chấp nhận khi dữ liệu chính chưa kịp ghi bền**. Nhưng bảo đảm thực sự không nằm ở chữ “WAL”; nó nằm ở **thứ tự ghi, mốc sync và ACK, cách commit, checkpoint, replay, retention log, replication và quy trình backup/restore**. Thiết kế đúng phải phân biệt **log trong RAM với log đã bền, crash recovery với point-in-time recovery, LSN với idempotency key, local durability với distributed commit**, và phải kiểm thử những ranh giới đó dưới lỗi thực tế. Khi các mốc được định nghĩa và đo lường rõ, hệ thống mới có thể đưa ra cam kết đáng tin về dữ liệu sau sự cố.
