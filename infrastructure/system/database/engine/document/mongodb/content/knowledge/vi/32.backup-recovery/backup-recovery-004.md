# Sao lưu bằng snapshot và yêu cầu phối hợp với storage engine trong MongoDB

## 1. Bài toán: sao lưu một hệ thống vẫn đang ghi dữ liệu

Một nền tảng cho thuê nhà dùng MongoDB để lưu:

- **listings**: hàng trăm nghìn tin đăng.
- **bookings**: yêu cầu đặt lịch xem và thuê nhà.
- **payments**: trạng thái thanh toán và đối soát.
- **auditEvents**: lịch sử thay đổi.

Database hoạt động liên tục. Cứ vài giây lại có insert, update và transaction. Đội vận hành muốn tạo bản sao lưu đủ nhanh để không phải dừng API nhiều giờ và đủ tin cậy để khôi phục khi ổ đĩa bị hỏng.

Họ cân nhắc chụp một **snapshot của volume** đang chứa MongoDB:

~~~text
MongoDB mongod
      |
      v
WiredTiger storage engine
      |
      +--> Data files / indexes / metadata
      +--> Checkpoints
      +--> Journal
      |
      v
Filesystem / block device / cloud volume
      |
      v
     SNAPSHOT
      |
      v
 Backup storage / restore volume
~~~

Vấn đề là câu lệnh snapshot ở tầng storage có thể chạy đúng nhưng bản sao lưu vẫn không dùng được nếu:

1. Các file quan trọng của MongoDB nằm trên **nhiều volumes** được chụp vào những thời điểm khác nhau.
2. Copy từng file từ thư mục dữ liệu **trong lúc mongod đang ghi**, không có ảnh chụp nhất quán.
3. Bỏ sót **journal, metadata hoặc các files cần cho WiredTiger recovery**.
4. Snapshot một **secondary** đang bị trễ replication nhưng tưởng rằng dữ liệu mới ngang primary.
5. Sao lưu các shard và config server **không phối hợp** rồi giả định có một thời điểm nhất quán cho toàn sharded cluster.
6. Chỉ lưu data volume mà quên **encryption keys, cấu hình, chứng chỉ, backup manifest**.
7. Có snapshot nhưng chưa từng thử **restore**.

Một snapshot hợp lệ phải đồng thời trả lời được hai câu hỏi:

> **Storage có thể phục hồi các file MongoDB thành một trạng thái nhất quán không?**

> **Bản sao lưu này có đáp ứng mục tiêu khôi phục của cả hệ thống, gồm thời điểm dữ liệu, topology và các dependencies hay không?**

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt **filesystem/block-volume snapshot**, **database-consistent backup** và **point-in-time recovery (PITR)**.
2. Hiểu vai trò **WiredTiger**, **checkpoint**, **journal** và **crash recovery**.
3. Giải thích vì sao snapshot phải bảo đảm **atomic point-in-time** cho toàn bộ file/volume liên quan.
4. So sánh **cold snapshot**, **fsyncLock + storage snapshot**, **snapshot của secondary** và **backup do công cụ MongoDB quản lý**.
5. Lập runbook dùng **fsyncLock/fsyncUnlock** có giới hạn thời gian và đường khôi phục nếu gặp lỗi.
6. Phân tích **replication lag, oplog window, majority-acknowledged writes, RPO/RTO**.
7. Hiểu tại sao **sharded cluster backup** cần phối hợp trên nhiều components.
8. Thiết kế việc lưu backup, encryption/KMS, access control và retention.
9. Xây quy trình **restore drill**: cô lập môi trường, kiểm tra dữ liệu, integrity và workload.
10. Nhận diện những lỗi phổ biến: live file copy, multi-volume skew, missing journal, mixed snapshots và khôi phục sai version.

> **Phạm vi và an toàn:** Đây là tài liệu trong **Database Engine Document MongoDB → Sao lưu và phục hồi**. Các thao tác lock writes, stop mongod, snapshot volumes và restore đều có thể ảnh hưởng dữ liệu/dịch vụ. Chỉ chạy các quy trình minh họa trên môi trường lab được phép quản trị. Bài học không yêu cầu thay đổi cluster production. Cú pháp và khả năng của snapshot APIs, backup cursor, Ops Manager/Atlas, fsyncLock và storage engines phụ thuộc phiên bản và deployment; luôn tham chiếu tài liệu đúng môi trường.

## 2. Định nghĩa snapshot trong ngữ cảnh database

### 2.1. Volume snapshot

Một **volume snapshot** là trạng thái của một block device/volume tại một mốc logic. Nhiều hệ thống storage triển khai bằng copy-on-write, redirect-on-write hoặc cơ chế riêng. Việc tạo mốc snapshot có thể nhanh hơn sao chép toàn bộ các bytes; dữ liệu sau đó được nhân bản/chuyển tới nơi lưu backup theo chính sách provider.

~~~text
Volume tại thời điểm T0
    [A][B][C][D]
          |
       Snapshot T0
          |
Ứng dụng tiếp tục ghi B' tại T1
          |
Volume hiện tại: [A][B'][C][D]
Snapshot T0:     [A][B ][C][D]
~~~

Điều quan trọng không phải chỉ tốc độ tạo snapshot, mà là **những blocks nào được chụp cùng thời điểm** và liệu tập blocks đó đủ cho storage engine recovery.

### 2.2. Snapshot không đồng nghĩa sao chép từng file

So sánh:

~~~text
Copy từng file trên dbPath khi mongod đang ghi:
  File A copy lúc 10:00:00
  File B copy lúc 10:00:08
  File C copy lúc 10:00:25

Volume snapshot atomic:
  Blocks của cùng volume được tham chiếu
  tại một mốc logic nhất quán T0
~~~

Copy file theo thứ tự có thể ghép các phiên bản **chưa từng cùng tồn tại** trong một trạng thái storage hợp lệ. Ngay cả khi tất cả file copy xong mà không có thông báo lỗi I/O, MongoDB vẫn có thể không khởi động được từ tập file đó.

Một snapshot **atomic trên một volume** khác với một tập ảnh được chụp **lần lượt trên nhiều volumes**. Với multi-volume, phải có cơ chế **consistency group/đồng bộ** hoặc quy trình phối hợp đáp ứng yêu cầu storage engine.

### 2.3. Crash-consistent

Một snapshot **crash-consistent** mô phỏng trạng thái storage sau khi máy mất nguồn bất ngờ tại một thời điểm:

- Một số data pages đã được ghi.
- Một số thay đổi mới có thể đang trong journal.
- Các thao tác đã được xác nhận durability theo đúng guarantees của hệ thống phải được xem trong phạm vi cấu hình.
- Storage engine cần chạy **crash recovery** khi mở bộ data files.

Crash-consistent **không có nghĩa mỗi file đã ở trạng thái “clean shutdown”**. Nó có nghĩa các blocks tạo thành một hình ảnh tương đương một sự cố tại cùng một điểm, để recovery có thể dùng checkpoint/journal.

### 2.4. Application-consistent

Một bản sao lưu **application-consistent** có sự phối hợp với ứng dụng/storage engine để bảo đảm trạng thái dữ liệu mong muốn, ví dụ flush/chặn ghi hoặc một cơ chế backup tích hợp.

Nó có thể:

- Giảm khoảng chênh giữa files và journal khi snapshot.
- Làm rõ thời điểm đóng băng writes.
- Giúp tăng độ tin cậy khi các data components trải nhiều volumes.
- Cần nhiều bước và có thể ảnh hưởng latency/availability.

**Không phải mọi crash-consistent snapshot đều hỏng**, vì WiredTiger được thiết kế để recover sau crash. Nhưng cũng **không nên gọi một tập ảnh chụp nhiều volumes lệch thời điểm là crash-consistent** chỉ vì từng volume tự tạo snapshot thành công.

### 2.5. Snapshot, full backup và incremental backup

**Full backup** là một bộ dữ liệu đủ để khôi phục mà không cần những backup thế hệ trước, ngoại trừ metadata/keys được quy định. **Incremental backup** lưu những phần thay đổi so với baseline và cần chuỗi phụ thuộc để restore.

Volume snapshot có thể là:

- Logical full view tại mỗi thời điểm.
- Physical storage incremental/deduplicated bên trong provider.
- Bản chụp chỉ dùng được khi những snapshot/blocks phụ thuộc còn tồn tại.

Không suy luận “provider chỉ tính phí phần blocks thay đổi” đồng nghĩa một file restore độc lập không cần chain hoặc metadata.

### 2.6. Snapshot khác MongoDB read concern snapshot

Từ **snapshot** còn xuất hiện trong **readConcern: "snapshot"** hoặc transaction snapshot isolation. Đó là cách một transaction/query thấy dữ liệu nhất quán về mặt logic.

Nó **không phải** API tạo bản sao lưu vật lý filesystem. Một MongoDB transaction đọc snapshot không tự lưu dbPath, journal, cấu hình hay công cụ để phục hồi toàn database.

## 3. RPO, RTO và thời điểm backup

### 3.1. Recovery Point Objective (RPO)

**RPO** là mức mất dữ liệu tối đa mà doanh nghiệp chấp nhận, thường đo bằng thời gian.

Ví dụ:

~~~text
Snapshot gần nhất: 10:00
Sự cố:             10:37
Restore được tới:  10:00

Khoảng dữ liệu không thể phục hồi:
  gần 37 phút
~~~

Nếu không có PITR/oplog archiving hoặc nguồn khác, snapshot mỗi giờ có thể dẫn tới mất gần một giờ dữ liệu.

### 3.2. Recovery Time Objective (RTO)

**RTO** là thời gian chấp nhận để khôi phục dịch vụ:

~~~text
Phát hiện sự cố
 + quyết định restore
 + lấy snapshot
 + provision storage/compute
 + mở MongoDB và recovery
 + validate
 + chuyển ứng dụng sang hệ mới
 = Recovery Time
~~~

Một bản snapshot tạo nhanh trong vài giây **không có nghĩa restore cũng chỉ mất vài giây**. Restore volume hàng terabyte, dựng sharded topology và kiểm tra nghiệp vụ có thể mất nhiều giờ.

### 3.3. RPO và RTO không do một câu lệnh quyết định

| Thành phần | Tác động RPO | Tác động RTO |
| --- | --- | --- |
| Tần suất snapshot | Càng dày càng giảm khoảng cách giữa điểm backup | Có thể tăng chi phí backup |
| Secondary replication lag | Snapshot secondary có thể cũ hơn primary | Cần xác minh điểm phục hồi |
| Oplog/PITR archive | Có thể đưa thời điểm phục hồi gần sự cố hơn | Replay có thể tốn thời gian |
| Kích thước dữ liệu | Không trực tiếp định nghĩa điểm phục hồi | Ảnh hưởng thời gian copy/restore |
| Sẵn có key/KMS/secrets | Không thay điểm dữ liệu | Có thể khiến restore bị kẹt |
| Restore drill | Không thay dữ liệu snapshot | Giảm thời gian phát hiện lỗi/runbook sai |
| Sharded cluster coordination | Quyết định tính nhất quán toàn cluster | Restore nhiều thành phần phức tạp |

### 3.4. Ví dụ lựa chọn backup policy

Giả sử:

~~~text
RPO mong muốn: <= 5 phút
RTO mong muốn: <= 45 phút
Dataset:       2 TiB
Replica set:   3 thành viên
~~~

Một snapshot mỗi 60 phút **không đủ để cam kết RPO 5 phút** nếu không có cơ chế backup log/PITR hoặc những bản phục hồi khác. Đồng thời, restore 2 TiB và validate trong 45 phút cần được **chứng minh bằng drill** hoặc dùng kiến trúc phục hồi phù hợp hơn.

## 4. WiredTiger là storage engine và tại sao phải phối hợp?

### 4.1. Storage engine làm gì?

**WiredTiger** là storage engine phổ biến/mặc định của MongoDB hiện đại. Nó chịu trách nhiệm nhiều chi tiết lưu trữ như:

- Tổ chức data files/indexes.
- Caching và ghi dữ liệu xuống disk.
- Quản lý checkpoints.
- Journaling/durability.
- Crash recovery.
- Các cấu trúc nội bộ cần thiết cho giao dịch, lịch sử dữ liệu và metadata.

Ứng dụng nhìn thấy documents và collections; storage engine phải duy trì một **tập file vật lý có quan hệ nhất quán**.

### 4.2. In-memory writes khác durable state

Khi một client chạy:

~~~javascript
db.bookings.updateOne(
  { _id: "booking-1" },
  { $set: { status: "confirmed" } }
);
~~~

MongoDB có thể xử lý thay đổi qua cache, journal và checkpoint theo các cơ chế của WiredTiger. Thời điểm client nhận ACK và mức độ durability còn phụ thuộc **write concern** và cấu hình deployment.

Không thể suy luận:

~~~text
updateOne trả OK
=> mọi data file trên filesystem đã chứa ngay
   toàn bộ giá trị mới ở dạng checkpoint hoàn chỉnh.
~~~

### 4.3. Checkpoint

**Checkpoint** là một trạng thái lưu trữ nhất quán mà WiredTiger ghi xuống storage theo cơ chế của nó. Checkpoint giúp:

- Có một mốc dữ liệu mà engine có thể khởi động từ đó.
- Giới hạn lượng journal/recovery work cần thiết.
- Duy trì một cấu trúc file có thể phục hồi khi crash.

Checkpoint **không phải backup độc lập**. Nó thường nằm trong cùng tập storage và có thể bị mất cùng volume bị hỏng, bị mã hóa bởi ransomware hoặc bị người có quyền xóa.

### 4.4. Journal

**Journal** giúp WiredTiger phục hồi những thay đổi cần thiết sau checkpoint theo durability guarantees. Khái niệm tổng quát:

~~~text
Checkpoint C0
    |
    +--> Transaction T1 được ghi journal
    +--> Transaction T2 được ghi journal
    +--> Sự cố tại thời điểm C1 chưa hoàn thành checkpoint mới
    |
    v
Restart:
  Dùng checkpoint hợp lệ + journal recovery
  để lấy lại trạng thái dữ liệu nhất quán
~~~

Chi tiết chính xác về journal flush, commit và recovery phụ thuộc MongoDB/WiredTiger version, journaling/write concern và topology. Hình trên là mô hình trực giác, không phải thứ tự thao tác I/O cố định của mọi phiên bản.

### 4.5. Snapshot phải chứa toàn bộ file engine cần

Một physical snapshot backup cần chứa **mọi file thuộc cùng bản backup vật lý**:

- Data và index files.
- WiredTiger metadata và các nội bộ liên quan.
- Journal, khi được đặt ở vị trí tương ứng.
- Các file trong **dbPath** cần để khởi động và recovery.
- Các volumes bổ sung nếu cấu hình storage engine liên quan tới chúng.

Không được chỉ chọn một số file có tên collection dễ nhận biết và bỏ những file tên hệ thống. Schema vật lý có thể khác giữa phiên bản và không phải hợp đồng dành cho thao tác copy thủ công.

### 4.6. Crash recovery không tự thay thế snapshot đúng

WiredTiger có thể phục hồi sau một **crash-consistent volume image** hợp lệ. Nhưng nó không thể đảm bảo sửa được:

~~~text
File A lấy từ 10:00
File B lấy từ 10:07
Journal lấy từ 10:12
Metadata lấy từ 10:03
~~~

nếu những file đó vốn không tạo thành một trạng thái crash-consistent. Trộn thành phần của nhiều snapshot có thể dẫn tới metadata mismatches, missing data hoặc storage corruption.

### 4.7. Durable does not mean “mọi thứ đã được backup”

Write concern, journal, majority acknowledgement và backup point là **các lớp bảo đảm khác nhau**:

~~~text
Write concern:
  Một write được xác nhận theo mức durability/replication nào?

Snapshot point:
  Những bytes và database state nào tồn tại
  trong ảnh chụp tại mốc backup?

Restore:
  Engine có thể phục hồi ảnh chụp đó
  thành database nhất quán hay không?
~~~

Một write được majority-acknowledged ở primary nhưng **secondary dùng để snapshot đang lag** có thể chưa có write đó. Không nên dùng thời điểm tạo backup làm lời hứa rằng nó chứa tất cả writes được primary ACK cho tới cùng đồng hồ tường.

## 5. Atomic snapshot: một thời điểm cho tất cả files

### 5.1. Atomic point-in-time trên một volume

Khi **dbPath** và các thành phần cần thiết nằm trên cùng volume, một snapshot storage có semantics atomic/crash-consistent có thể đóng băng hình ảnh của toàn volume ở một thời điểm.

~~~text
Volume V gồm:
  /data/db/
      WiredTiger...
      collection...
      index...
      journal/...

Snapshot(V, T0) -> tất cả blocks của V ở T0
~~~

Sau đó hệ thống có thể tiếp tục ghi vào volume sống. Việc export/copy dữ liệu **từ snapshot đã tạo** có thể kéo dài mà không cần giữ mongod đứng yên suốt thời gian copy, miễn storage provider bảo đảm snapshot point đã cố định.

### 5.2. Multi-volume: tình huống nguy hiểm

Giả sử:

~~~text
Volume V1: /data/db/data
Volume V2: /data/db/journal

Snapshot(V1) tại T0 = 10:00:00
Snapshot(V2) tại T1 = 10:00:18
~~~

Hai snapshot này **không mặc nhiên là một crash-consistent image của MongoDB**. 18 giây chênh có thể chứa rất nhiều writes/checkpoints.

**Giải pháp:** dùng cơ chế **consistency group/multi-volume atomic snapshot** được storage hỗ trợ, hoặc một quy trình dừng/khóa ghi phối hợp với storage engine mà bạn đã xác minh đủ điều kiện.

### 5.3. Không phải mọi cloud snapshot API là consistency group

Một provider có thể cung cấp:

- Snapshot một volume độc lập.
- Snapshot nhiều volumes thuộc cùng một instance.
- Application-consistent snapshot theo integration cụ thể.
- Snapshot group có mốc consistency chung.

Không suy luận chỉ từ việc API chấp nhận nhiều volume IDs rằng **mọi volume được chụp tại cùng một thời điểm ứng dụng nhất quán**. Phải kiểm tra hợp đồng API và storage provider của đúng sản phẩm/phiên bản.

### 5.4. Filesystem freeze khác database freeze

Một filesystem có thể có chức năng **freeze/thaw** để làm ổn định metadata/I/O tại mốc snapshot. Nhưng filesystem freeze **không tự biết** transaction/checkpoint/journal semantics của WiredTiger.

Khi cần application-consistent backup, phải kết hợp đúng:

~~~text
MongoDB write coordination
      +
Filesystem/storage coordination
      +
Atomic snapshot mechanism
      +
Restore validation
~~~

Không coi một thao tác filesystem bất kỳ là bằng chứng đã tạo MongoDB-consistent backup.

## 6. Bốn chiến lược snapshot thường gặp

| Chiến lược | Cơ chế | Điểm mạnh | Hạn chế |
| --- | --- | --- | --- |
| **Cold backup** | Dừng mongod sạch sẽ rồi snapshot/copy | Dễ giải thích tính nhất quán của files | Có downtime ở node bị dừng |
| **fsyncLock + snapshot** | Phối hợp mongod flush/lock writes rồi tạo snapshot storage | Có thể rút ngắn thời gian phải khóa ghi | Làm chậm/queue writes, cần unlock an toàn |
| **Snapshot một secondary** | Dùng replica set member không phục vụ writes ứng dụng chính | Giảm tác động lên primary | Phải kiểm tra replication lag, member health |
| **Backup platform tích hợp** | Atlas/Ops Manager/Cloud Manager/công cụ hỗ trợ | Có metadata, scheduling, PITR/coordination theo tính năng | Điều kiện hỗ trợ, chi phí, kiểm tra retention và restore |

Các lựa chọn có thể kết hợp: ví dụ **fsyncLock trên một secondary rồi chụp atomic volume snapshot**. Nhưng việc kết hợp phải có runbook và đánh giá ảnh hưởng tới replication.

### 6.1. Cold backup

Quy trình:

~~~text
Chọn node được phép dừng
      |
      v
Shutdown mongod sạch sẽ
      |
      v
Xác nhận tiến trình đã dừng
      |
      v
Tạo volume snapshot/copy dữ liệu đầy đủ
      |
      v
Khởi động lại node
      |
      v
Xác nhận health và replication
~~~

Ưu điểm là không có concurrent MongoDB writes trong lúc sao chép. Tuy nhiên, **cold backup một member** chỉ là bản sao node đó, chưa tự tạo point-in-time backup nhất quán của cả sharded cluster.

### 6.2. Snapshot nóng phối hợp với fsyncLock

MongoDB cung cấp cơ chế **fsyncLock/fsyncUnlock** trong môi trường/phiên bản hỗ trợ để phối hợp flush và ngăn writes trong quá trình tạo backup filesystem.

Mẫu thao tác:

~~~text
Kiểm tra node có thể khóa ghi
      |
      v
fsyncLock
      |
      v
Storage snapshot atomic
      |
      v
fsyncUnlock
      |
      v
Kiểm tra node tiếp tục nhận/apply writes
~~~

**Chỉ giữ lock đến khi storage đã cố định điểm snapshot**, không phải giữ lock suốt thời gian provider chuyển toàn bộ dữ liệu backup vào vùng lưu trữ lâu dài, nếu provider xác nhận snapshot point đã an toàn.

### 6.3. Snapshot trên secondary

Một replica set có thể dùng secondary chuyên cho tác vụ backup:

~~~text
                  Replica set

Primary --------------------------> App writes
  |
  +--> Secondary A ----------------> HA/read traffic
  |
  +--> Secondary B ----------------> Backup snapshot
                                      |
                                      v
                              Backup storage
~~~

Backup secondary giúp giảm tác động tới primary. Nhưng phải biết:

- Secondary B có **replication lag** bao lâu?
- Member này có đủ khỏe để phục hồi không?
- Có đang rollback hoặc initial sync không?
- Khi fsyncLock, **oplog application có bị gián đoạn** và oplog window còn đủ không?
- Node có thể được nâng thành primary trong lúc backup không? Cần topology policy phù hợp.

### 6.4. Managed backup

Nếu dùng một dịch vụ backup tích hợp với MongoDB, nó có thể quản lý snapshots, trạng thái replica set/shards, oplog, backup catalogs và restore workflows theo khả năng sản phẩm.

Không nên tự tái tạo một hệ thống tương đương chỉ bằng vài cron scripts nếu doanh nghiệp cần **PITR, backup nhất quán toàn sharded cluster và restore SLA nghiêm ngặt**.

## 7. fsyncLock và fsyncUnlock: ý nghĩa và tác động

### 7.1. Lệnh trong mongosh

Trên một **mongod lab** đã xác thực với quyền phù hợp:

~~~javascript
const admin = db.getSiblingDB("admin");

// Bắt đầu khoảng phối hợp backup.
printjson(admin.fsyncLock());

// Tại đây: quản trị viên/storage API phải tạo
// snapshot theo đúng quy trình đã được xác minh.

// Kết thúc khoảng phối hợp ngay khi snapshot point đã cố định.
printjson(admin.fsyncUnlock());
~~~

**Đoạn trên không tự tạo snapshot.** Nó chỉ cho thấy vị trí của MongoDB operations trong runbook. Không chạy fsyncLock trên server production bằng cách copy/paste mà không có quy trình unlock, quyền hạn và giám sát tác động.

### 7.2. fsyncLock khác read lock đơn thuần

Mục đích của fsyncLock trong backup là phối hợp trạng thái files/storage engine và **chặn thêm writes** trong khoảng thao tác. Tùy phiên bản và topology, các lệnh ghi có thể bị queue/đình trệ trong lúc lock.

Hệ quả:

- Write latency có thể tăng mạnh.
- Client có thể timeout.
- Replication application trên secondary có thể chậm.
- Các jobs phụ thuộc writes có thể bị ảnh hưởng.
- Tác động có thể lan sang availability nếu nhầm member hoặc giữ lock quá lâu.

Vì thế, **fsyncLock là thao tác vận hành cần kiểm soát**, không phải câu lệnh vô hại để chạy thường xuyên.

### 7.3. fsyncLock phải được ghép với unlock chắc chắn

Một runbook không nên chỉ có:

~~~text
1. fsyncLock
2. Chạy script snapshot
3. fsyncUnlock
~~~

vì nếu bước 2 lỗi, bước 3 có thể không chạy. Tối thiểu cần:

- **try/finally** hoặc trap cleanup tương ứng.
- Watchdog/timeout cho khoảng lock.
- Cơ chế kiểm tra node còn bị lock hay không.
- Một đường **manual unlock** do operator có quyền thực hiện.
- Alert khi lock vượt SLA.
- Hướng xử lý nếu kết nối điều khiển lock bị rớt hoặc process restart.

### 7.4. Pseudocode orchestration an toàn hơn

Đây là **pseudocode**, không phải công cụ backup sẵn chạy production:

~~~javascript
async function snapshotWithCoordinatedLock(
  adminDb,
  storageProvider,
  volumeGroup
) {
  let locked = false;
  let snapshot;

  try {
    await adminDb.command({ fsync: 1, lock: true });
    locked = true;

    // Hàm này do hệ thống storage cung cấp;
    // phải đảm bảo mốc snapshot cho mọi volume liên quan.
    snapshot = await storageProvider
      .createConsistentGroupSnapshot(volumeGroup);

    // Điều kiện success phải khẳng định điểm snapshot
    // đã được cố định, không chỉ nhận request ID.
    if (!snapshot || !snapshot.pointInTimeEstablished) {
      throw new Error(
        "Không xác minh được snapshot consistency point"
      );
    }

    return snapshot;
  } finally {
    if (locked) {
      try {
        await adminDb.command({ fsyncUnlock: 1 });
      } catch (unlockError) {
        // Phải phát alert và kích hoạt runbook manual unlock.
        // Không giả định node đã được unlock.
        throw unlockError;
      }
    }
  }
}
~~~

**Chú ý:** storageProvider và pointInTimeEstablished là **giao diện minh họa tự định nghĩa**, không phải MongoDB API hay thuộc tính của cloud provider. Code sản xuất còn phải xử lý timeout, cancellation, credential expiry, kiểm tra node/lock state và ghi manifest.

Trong một số trường hợp, việc **throw lỗi unlock trong finally** có thể che lỗi snapshot ban đầu; hệ thống orchestration thực phải log cả hai lỗi và ưu tiên trạng thái an toàn. Không coi pseudocode là một triển khai backup được chứng nhận.

### 7.5. Bước unlock không được quên

Nếu snapshot API tạo điểm ảnh chụp xong nhưng job upload mất 45 phút, thông thường **không cần giữ write lock 45 phút** nếu semantics storage snapshot bảo đảm blocks mốc T0 không thay đổi trong quá trình upload. Giữ lock kéo dài có thể làm queue writes tăng, client timeout và replication lag.

### 7.6. Với primary có rủi ro cao hơn

fsyncLock trên primary có thể ngăn phần lớn writes ứng dụng. Nếu không có lý do đặc biệt, cân nhắc backup từ secondary chuyên dụng hoặc backup service hỗ trợ. Nhưng secondary cũng không miễn rủi ro: nó vẫn là member tham gia replication và có thể bị chậm hoặc mất khả năng bắt kịp oplog.

## 8. Cần phối hợp với filesystem và cloud volumes như thế nào?

### 8.1. Kiểm kê mọi đường dẫn

Trước khi thiết kế snapshot, inventory:

~~~text
mongod process
  storage.dbPath
  journal path
  filesystem mount points
  volumes/block devices
  encryption layer
  backup agent path
  logging/config/certs needed for restore
~~~

Không đoán từ tên thư mục. Trên triển khai mặc định, WiredTiger files và journal thường nằm dưới **dbPath**, nhưng topology storage, symlinks, separate mounts và host-level configuration có thể khác.

### 8.2. One-volume example

~~~text
Volume /dev/volumeA
   |
   +-- /var/lib/mongodb/
         WiredTiger metadata
         data/index files
         journal/

Snapshot /dev/volumeA tại T0
~~~

Nếu snapshot provider bảo đảm ảnh chụp atomic/crash-consistent và phần files cần thiết đều ở đây, nó là nền tảng hợp lý cho physical recovery.

### 8.3. Multiple-volume example

~~~text
Volume A: /var/lib/mongodb/data
Volume B: /var/lib/mongodb/journal
Volume C: auxiliary WiredTiger files or dependencies
~~~

Phải bảo đảm một **consistent group snapshot** hoặc phối hợp khiến các thành phần không thay đổi giữa những snapshot points theo yêu cầu của engine. Chụp A vào 10:00 rồi B vào 10:05 không được coi là tương đương chụp A+B ở cùng một thời điểm.

### 8.4. Local filesystem snapshot khác remote replicated storage

Một số storage systems có:

- RAID.
- Replication block storage.
- Object storage snapshots.
- Cross-region copies.
- Immutable snapshots.

Không phải tính năng nào cũng bảo đảm **application consistency**. RAID/replication tăng availability hoặc khả năng chịu hỏng phần cứng, nhưng **không thay thế backup**: thao tác xóa nhầm hoặc mã hóa dữ liệu có thể được nhân bản ngay lập tức sang replica.

### 8.5. LVM snapshot minh họa

Trong một Linux lab có LVM, administrator có thể tạo snapshot logic volume bằng command tương tự:

~~~bash
# Chỉ minh họa trên lab LVM đã được cấu hình.
# /dev/vg_lab/mongo_data là ví dụ, không phải tên volume cần dùng.
sudo lvcreate \
  --snapshot \
  --name mongo_snap_lab_343 \
  --size 4G \
  /dev/vg_lab/mongo_data
~~~

**Không chạy command này nếu chưa biết chính xác volume và dung lượng COW/snapshot.** LVM snapshot có những yêu cầu capacity và cơ chế riêng; nếu vùng chứa thay đổi đầy, snapshot có thể bị vô hiệu. Đây cũng chỉ là snapshot **một logical volume**, không tự giải quyết nhất quán giữa nhiều LVs.

### 8.6. AWS/EBS hoặc cloud snapshot

Các cloud providers thường có API snapshot volumes, có thể thêm cơ chế **multi-volume snapshots** hoặc quiesce application tùy sản phẩm. Quy trình đúng:

1. Xác định exact volume IDs thuộc MongoDB.
2. Xác nhận consistency guarantee của API.
3. Phối hợp mongod nếu yêu cầu.
4. Yêu cầu snapshot.
5. Chỉ unlock khi đã xác nhận **snapshot point** được thiết lập.
6. Theo dõi quá trình snapshot/upload tới hoàn tất.
7. Kiểm tra manifest và thực hiện restore drill.

Không chỉ dựa trên trạng thái **request accepted** để kết luận backup đã sẵn sàng cho restore. Provider có thể cần thời gian để snapshot hoàn tất hoặc copy sang region khác.

## 9. Snapshot trên replica set: chọn thành viên nào?

### 9.1. Tại sao backup secondary?

Một replica set phục vụ high availability. Backup trên **secondary** thường tránh khóa trực tiếp primary đang nhận writes từ ứng dụng.

~~~text
Client writes
     |
     v
  Primary -------- oplog --------> Secondary A
                               \
                                \--> Secondary B
                                       |
                                       v
                               Snapshot backup
~~~

Secondary B có thể là member chuyên cho backup theo thiết kế topology. Điều này giúp giảm tác động read/copy I/O lên primary, nhưng vẫn phải bảo vệ tính sẵn sàng của replica set.

### 9.2. Chọn một member khỏe mạnh

Trước snapshot cần kiểm tra:

- Member **SECONDARY** hợp lệ, không đang initial sync/recovering bất thường.
- Replication lag trong giới hạn RPO.
- Disk, IOPS, memory, CPU đủ cho backup.
- Không có rollback đang diễn ra.
- Oplog window đủ cho thời gian member bị chậm và bắt kịp.
- Membership/election/voting policy không khiến lock/cold shutdown gây mất majority.

### 9.3. Replication lag

Ví dụ:

~~~text
Primary optime:  10:30:00
Secondary optime:10:27:40
Snapshot ở secondary tạo lúc 10:30:05
~~~

Mặc dù backup có timestamp tường **10:30:05**, dữ liệu snapshot có thể phản ánh trạng thái secondary quanh **10:27:40**, tùy member state và quy tắc backup. Nếu business yêu cầu RPO 1 phút, lag 2 phút 20 giây đã là vấn đề cần xem xét.

**Timestamp tạo snapshot không phải timestamp của write cuối cùng đã được phục hồi.**

### 9.4. Quan sát replica set

Trên connection có quyền phù hợp:

~~~javascript
printjson(rs.status());
~~~

Output có thông tin member state và các mốc optime theo phiên bản. Không code cứng một field position như hợp đồng bất biến giữa mọi versions; cần xác định member backup và đọc những chỉ số replication thực tế.

Có thể lấy cluster time/last applied optime qua các command/monitoring APIs phù hợp. **rs.status() không có nghĩa một snapshot backup đã được tạo**; nó là thông tin hỗ trợ chọn thời điểm/member.

### 9.5. fsyncLock trên secondary ảnh hưởng replication

Khi secondary bị write-locked, việc apply replicated changes có thể chậm hoặc tạm dừng theo tính năng/version. Nếu giữ lock lâu:

~~~text
Primary tiếp tục ghi
Secondary backup chưa apply kịp
Replication lag tăng
Oplog trên primary vẫn quay vòng
~~~

Nếu oplog window không đủ để secondary bắt kịp sau unlock, member có thể phải resync hoặc cần can thiệp vận hành. Do đó, phải có **giới hạn lock duration**, giám sát lag, oplog và cơ chế hủy backup/giải phóng lock.

### 9.6. Hidden/dedicated backup member

Có thể dùng secondary chuyên backup với các thuộc tính phù hợp (ví dụ hidden/non-electable theo cấu hình replica set) để giảm nguy cơ phục vụ read traffic hoặc trở thành primary trong lúc backup.

Tuy nhiên, một member vẫn có thể ảnh hưởng majority/voting và storage footprint tùy cấu hình. Không đổi priority, votes hoặc hidden flags trong production mà không đánh giá availability và quorum.

### 9.7. Snapshot một member khác snapshot toàn replica set

Với replica set không sharded, một physical snapshot **hợp lệ của một member** thường là nền tảng để phục hồi dữ liệu của member/replica set theo quy trình phù hợp.

Nhưng không được:

- Lấy data files từ member A rồi journal từ member B.
- Trộn snapshots các members ở nhiều thời điểm thành một dbPath.
- Tự thay dữ liệu của một member đang chạy trong replica set bằng old snapshot mà không có thủ tục recovery.
- Giả định old snapshot có thể reintegrate an toàn vào replica set hiện tại mà không cần xét rollback/resync/oplog.

Khôi phục member và khôi phục **toàn bộ replica set** là hai công việc vận hành khác nhau.

## 10. Snapshot và write concern majority

### 10.1. Ý nghĩa majority acknowledgement

Trong replica set, **writeConcern: { w: "majority" }** yêu cầu acknowledgement liên quan đến số members cần thiết theo replica set majority. Cấu hình durability/journaling và server version ảnh hưởng chi tiết bảo đảm khi ACK.

Ví dụ ứng dụng:

~~~javascript
db.getSiblingDB("mongo_backup_lab_343")
  .getCollection("events")
  .insertOne(
    {
      _id: "event-majority-001",
      kind: "booking_confirmed",
      createdAt: new Date()
    },
    { writeConcern: { w: "majority" } }
  );
~~~

Mẫu này minh họa mong muốn acknowledgement majority trên một replica set. Nếu đang dùng standalone hoặc cấu hình không cho phép, semantics thực tế phải kiểm tra deployment.

### 10.2. Majority không buộc mọi secondary có write

Trong replica set 3 members, một write được majority-acknowledged có thể đã có trên primary và Secondary A, nhưng **Secondary B đang lag** chưa apply write đó.

Nếu chụp Secondary B ngay lúc này, snapshot của B có thể không chứa write dù primary đã ACK majority.

Đó là lý do backup member cần theo dõi optime và thời điểm dữ liệu, thay vì suy luận từ majority write concern của ứng dụng.

### 10.3. Các write không đủ durable

Nếu một workload dùng write concern yếu hoặc cấu hình làm giảm durability, một sự cố có thể khiến một số writes gần thời điểm snapshot không xuất hiện sau recovery. Không cam kết “snapshot có mọi thao tác mà client từng thấy ACK” mà không xét write concern, journaling và storage semantics.

### 10.4. Backup consistency khác business consistency bên ngoài MongoDB

Giả sử transaction trong MongoDB cập nhật booking và thêm audit event, nhưng service sau đó gọi một hệ thống thanh toán bên ngoài. Một snapshot hợp lệ của MongoDB **không đồng bộ rollback** hệ thống thanh toán bên ngoài.

Nếu restore MongoDB về trước khi external payment completed, cần reconciliation, idempotency, saga/outbox hoặc quy trình vận hành để cân bằng lại trạng thái giữa các hệ thống.

## 11. Point-in-time recovery (PITR) cần gì thêm?

### 11.1. Base snapshot và log liên tục

Snapshot lúc T0 tạo một điểm khôi phục. Nếu muốn restore tại T1 > T0, thường cần **chuỗi thay đổi** được lưu liên tục và cơ chế replay tương thích, ví dụ oplog archival trong giải pháp backup MongoDB được hỗ trợ.

~~~text
T0                                       T1
|----------------------------------------|
Base snapshot                     Failure / target
   \------ oplog/change archive --------/
          không được có khoảng hở
~~~

Quy trình PITR phải chứng minh:

- Có **base backup** hợp lệ.
- Có những log segments cần thiết và liên tục.
- Có checkpoint/restore token/timestamp phù hợp.
- Có công cụ áp dụng log đúng thứ tự và semantics.
- Target timestamp nằm trong khoảng PITR thực sự được hỗ trợ.

### 11.2. Không tự coi oplog trong snapshot là đủ PITR

Một physical snapshot của secondary có thể chứa oplog local tại thời điểm backup. Nhưng oplog ấy không mặc nhiên bao gồm **các writes sau snapshot** hoặc lịch sử liên tục cho mọi thời điểm muốn restore.

Không thể chỉ khôi phục snapshot, rồi chạy một vài lệnh copy thủ công trên **local.oplog.rs** để tạo một giải pháp PITR production an toàn.

### 11.3. Oplog window

Oplog là một vùng dữ liệu hữu hạn với cơ chế duy trì lịch sử. Nếu backup/archive pipeline chậm, những entries cũ có thể bị loại theo policy trước khi được lưu.

Ví dụ:

~~~text
Oplog window: 8 giờ
Backup job lỗi không thu được logs: 10 giờ

=> Có nguy cơ xuất hiện khoảng hở PITR.
~~~

Với managed backup, cần theo dõi **backup freshness/PITR availability** chứ không chỉ tình trạng các volume snapshots.

### 11.4. Timestamp mục tiêu

Khi chọn restore đến thời điểm “14:25”, cần biết:

- Dùng timestamp theo timezone nào?
- Mong muốn bao gồm hay loại write tại boundary?
- Các transaction nhiều collections được xử lý thế nào?
- Hệ thống ngoài MongoDB (message bus/payment) cần đối soát đến mốc nào?

Không lấy timestamp từ UI mà quên múi giờ, rồi tuyên bố đã restore đúng thời điểm nghiệp vụ.

### 11.5. Không áp dụng máy móc mongorestore --oplogReplay

**mongodump/mongorestore** là công cụ logic backup/restore, có các cờ liên quan tới oplog trong điều kiện được hỗ trợ. Chúng **không tự là cơ chế PITR ghép tùy ý với một physical snapshot WiredTiger**.

Nếu muốn PITR từ volume snapshots, dùng quy trình backup/restore được sản phẩm hỗ trợ và đã diễn tập. Không nối các tools khác loại bằng giả định “đều chứa dữ liệu MongoDB nên replay được”.

## 12. Sharded cluster: snapshot từng shard chưa phải backup nhất quán

### 12.1. Các thành phần của sharded cluster

Một sharded cluster điển hình:

~~~text
                 Applications
                      |
                    mongos
                      |
            +---------+---------+
            |                   |
        Config Server         Shards
        Replica Set        +----+----+
                           |         |
                         Shard A   Shard B
                           RS        RS
~~~

Dữ liệu có thể nằm trên nhiều shards. **Config servers** giữ thông tin routing/chunk metadata cần cho cluster hoạt động.

### 12.2. Lệch snapshot times gây hậu quả

Giả sử một chunk di chuyển từ Shard A sang Shard B:

~~~text
10:00  Snapshot Shard A
10:02  Chunk migration A -> B
10:05  Snapshot Shard B
10:08  Snapshot Config Server
~~~

Các bản chụp ở ba thời điểm không tự bảo đảm một trạng thái cluster nhất quán. Tùy migration/cấu hình, restore có thể phải giải quyết dữ liệu và metadata không đồng bộ.

### 12.3. Phải phối hợp toàn cluster

Với sharded cluster, cần:

- Backup tất cả relevant shards và config server components.
- Một chiến lược đảm bảo **consistent recovery point**.
- Phối hợp **balancer/chunk migration** theo runbook và phiên bản khi cần.
- Quản lý oplog/PITR và transaction semantics trên nhiều shards.
- Backup manifests liên kết những bản chụp thuộc cùng một thế hệ.
- Restore procedures đặc thù của sharded deployment.

Không coi việc dừng balancer là **đủ một mình** để tạo backup nhất quán, vì các application writes và distributed transactions vẫn có thể tiếp diễn.

### 12.4. Không chỉ backup mongos

**mongos** là query router, không lưu toàn bộ data và catalog như một shard replica set hoặc config server. Snapshot một host chạy mongos không phải backup dữ liệu sharded cluster.

### 12.5. Khi nào dùng managed backup?

Nếu cluster sharded có nhiều shards, workload giao dịch và RPO chặt, backup platform được MongoDB hỗ trợ (ví dụ Atlas/Cloud Manager/Ops Manager tùy deployment) thường phù hợp hơn việc tự orchestration snapshots theo scripts đơn giản.

Tính năng full snapshot, continuous backup/PITR, copy region và thời hạn lưu **phụ thuộc tiers, version và policy**; phải xác minh trong tài liệu sản phẩm.

## 13. Atlas, Ops Manager và tự quản khác nhau

### 13.1. MongoDB Atlas

Atlas có các tính năng backup/snapshot và PITR tùy loại cluster/tier, cấu hình và subscription. Một người vận hành cần xác minh:

- Cluster có **backup enabled** chưa?
- Lịch snapshot và retention policy.
- Có PITR hay chỉ snapshot định kỳ?
- Có thể restore sang cluster mới/target nào?
- Có cross-region/cross-project restore hoặc copy không?
- Encryption/KMS cần gì tại nơi restore?
- Thời gian hoàn tất backup và backup health.

Không giả định mọi Atlas free/shared tier đều có cùng khả năng với dedicated cluster.

### 13.2. Ops Manager/Cloud Manager

Các hệ thống quản lý MongoDB có thể có backup integration, automation và restore workflows. Chúng cần cấu hình agent, storage, quyền và chính sách theo phiên bản.

Một lệnh fsyncLock thủ công **không thay thế** toàn bộ chức năng backup catalog và recovery orchestration.

### 13.3. Self-managed

Với self-managed, đội vận hành chịu trách nhiệm đầy đủ cho:

~~~text
Snapshot API + consistency group
    |
Backup catalogs/manifest
    |
Offsite encrypted storage
    |
Retention & immutability
    |
Periodic restore drills
    |
Monitoring / incident response
~~~

Ưu điểm là quyền kiểm soát cao; đổi lại đòi hỏi chuyên môn storage engine, filesystem, cloud/KMS, replica set/sharding và security.

## 14. Mã hóa, quyền truy cập và backup retention

### 14.1. Backup chứa cả dữ liệu nhạy cảm

Physical snapshot có thể chứa dữ liệu khách hàng, users, bookings, trạng thái tài chính và authentication metadata. **Backup phải được bảo vệ ít nhất tương đương production data**.

Nguyên tắc:

- Encryption at rest cho snapshot/backup objects.
- Encryption in transit khi chuyển dữ liệu.
- Identity chỉ có quyền backup/restore cần thiết.
- Audit các thao tác tải/xóa/khôi phục.
- Không công khai bucket/object URLs.
- Phân chia quyền backup operator và application operator.

### 14.2. Encryption keys và KMS

Một snapshot của volume mã hóa có thể **không thể restore** nếu mất key hoặc quyền giải mã.

Phải có kế hoạch:

- Key ownership và rotation.
- Khả năng truy cập key tại target restore.
- KMS key policy và cross-region/account permissions.
- Backup/recovery của material cần thiết theo đúng sản phẩm.
- Không lưu plaintext keys ngay cùng bản snapshot.

**Tệp snapshot không đủ nếu thiếu chìa khóa để giải mã.**

### 14.3. TLS certificates và application secrets

dbPath không phải toàn bộ hệ thống. Sau restore còn có thể cần:

- mongod configuration phù hợp.
- TLS certificates, CA chain, internal authentication material.
- Secrets cho services.
- DNS/connection strings/network policies.
- Trạng thái cấu hình backup agent.
- Monitoring/audit integrations.

Những thành phần này có thể được lưu riêng trong configuration management/secret vault. **Không** chèn secrets plaintext vào backup manifest.

### 14.4. Immutable/offsite copies

Nếu ransomware hoặc một user root của cloud account có thể xóa cả production volume lẫn mọi snapshots, backup không còn là tuyến phòng thủ độc lập.

Phòng ngừa:

- Offsite/cross-account backup khi cần.
- Immutable/object lock theo chính sách.
- Tách backup deletion permissions.
- Retention theo RPO, quy định và chi phí.
- Thử restore từ vị trí offsite, không chỉ từ cùng availability zone.

### 14.5. Retention policy

Ví dụ:

~~~text
Hourly snapshots:  giữ 48 giờ
Daily snapshots:   giữ 30 ngày
Weekly snapshots:  giữ 12 tuần
Monthly snapshots: giữ 12 tháng
~~~

Đây là ví dụ chính sách, không phải chuẩn MongoDB. Retention thực phải phù hợp với compliance, data lifecycle, storage cost và khả năng điều tra sự cố muộn.

### 14.6. Data deletion và privacy

Khi ứng dụng xóa một document vì yêu cầu privacy, dữ liệu đó có thể còn trong snapshots cũ theo retention policy. Cần chính sách xóa/giới hạn truy cập backup theo luật và yêu cầu tổ chức; không thể suy luận deleteOne trên production sẽ xóa bytes khỏi mọi bản sao lưu ngay lập tức.

## 15. Backup manifest: biết chính xác mình đã chụp gì

### 15.1. Vì sao cần manifest?

Sau ba tháng, một thư mục tên:

~~~text
mongo-backup-final-v2/
~~~

không đủ cho biết nó thuộc replica set nào, MongoDB version nào, có journal không, oplog position nào, encryption key nào và đã restore test chưa.

Một **backup manifest** gắn bản backup với metadata cần thiết để phục hồi có kiểm soát.

### 15.2. Ví dụ manifest logic

~~~yaml
backupId: "mongo-343-2026-01-15T10:00Z"
backupKind: "volume-snapshot"
environment: "lab"
mongodb:
  deploymentKind: "replica-set"
  replicaSetName: "rsLab"
  sourceMember: "mongo-secondary-b.lab:27017"
  serverVersion: "RECORD_ACTUAL_VERSION"
  fcv: "RECORD_ACTUAL_FCV"
  storageEngine: "wiredTiger"
snapshot:
  requestedAtUtc: "2026-01-15T10:00:00Z"
  pointEstablishedAtUtc: "RECORD_ACTUAL_TIME"
  consistencyMode: "coordinated-snapshot"
  volumeGroupId: "RECORD_ACTUAL_GROUP"
  volumeSnapshotIds:
    - "RECORD_REAL_SNAPSHOT_ID"
  completionState: "RECORD_ACTUAL_STATE"
replication:
  sourceAppliedOptime: "RECORD_ACTUAL_OPTIMETIME"
  sourceMajorityCommittedOptime: "IF_AVAILABLE"
security:
  encryptionKeyReference: "KMS_KEY_REFERENCE_NOT_SECRET"
  backupAccessPolicy: "backup-restore-team"
validation:
  restoreDrillPassed: false
  restoreDrillTimestampUtc: null
~~~

Các field trên là **schema minh họa do đội vận hành tự định nghĩa**, không phải định dạng manifest bắt buộc của MongoDB hoặc cloud provider.

### 15.3. Các thông tin nên ghi

| Nhóm | Thông tin |
| --- | --- |
| Identity | Backup ID, owner, environment, ticket/job ID |
| Topology | Standalone/replica set/sharded, member/shard/config |
| Engine | WiredTiger, MongoDB version, FCV |
| Storage | dbPath, volume IDs, mount points, snapshot IDs |
| Consistency | Snapshot mode, lock/stop coordination, group checkpoint |
| Replication | Source optime/lag, oplog continuity nếu có |
| Security | Encryption type và key reference (không phải secret) |
| Lifecycle | Created/completed time, retention, immutable flag |
| Validation | Integrity checks, restore drill history, result |

### 15.4. Hash/Checksum

Nếu backup được xuất thành archive/object files, checksum có thể xác nhận transfer integrity. Với block snapshots do provider quản lý, dùng integrity checks và metadata mà provider hỗ trợ.

**Checksum khớp chỉ chứng minh dữ liệu không thay đổi so với nguồn được hash**; nó không chứng minh nguồn được chụp đã là một MongoDB-consistent image. Vẫn cần restore drill.

## 16. Restore: cách nghĩ đúng trước khi đụng đến dbPath

### 16.1. Không restore đè production đang chạy

Một quy trình cần bắt đầu bằng:

1. Xác định target restore **cô lập**.
2. Xác định backup ID và mốc dữ liệu mong muốn.
3. Xác nhận topology, MongoDB version/FCV và encryption keys.
4. Lấy đúng toàn bộ snapshots/volume group của **cùng thế hệ**.
5. Đảm bảo target mongod **đã dừng** trước khi thay files vật lý.
6. Restore/mount toàn bộ filesystem theo policy.
7. Bảo đảm owner/permission/path đúng.
8. Khởi động MongoDB bằng cấu hình tương thích để engine recovery.
9. Validate và quyết định có dùng làm hệ phục hồi hay không.

**Không copy những WiredTiger files từ snapshot vào dbPath của mongod đang chạy.** Data files đang được engine mở/ghi, việc thay một phần có thể gây corruption nghiêm trọng.

### 16.2. Không trộn backup generations

Sai:

~~~text
data files  -> Snapshot 2026-01-15 10:00
journal     -> Snapshot 2026-01-15 11:00
metadata    -> Snapshot 2026-01-14 10:00
~~~

Đúng:

~~~text
Toàn bộ files/volumes
  từ cùng một consistency point
  theo manifest và quy trình provider xác nhận
~~~

### 16.3. Journal recovery khi mở snapshot

Nếu snapshot là crash-consistent, WiredTiger có thể thực hiện recovery từ checkpoint/journal. Quá trình khởi động có thể lâu hơn so với clean shutdown và ghi log recovery.

Đừng tự xóa journal chỉ để khởi động nhanh hoặc bỏ qua thông báo consistency mismatch. Nếu recovery không thành công, **giữ nguyên backup gốc**, ghi nhận log và thử trên một bản sao target khác sau khi hiểu nguyên nhân.

### 16.4. Version và FCV

Physical backup gắn với storage files của một MongoDB version/feature compatibility context. Không mặc nhiên copy data files cũ vào bất kỳ phiên bản mongod mới hơn hoặc cũ hơn.

Trước restore:

- Ghi lại binary version của nguồn.
- Ghi lại **Feature Compatibility Version (FCV)**.
- Kiểm tra supported upgrade/downgrade/restore paths.
- Khôi phục vào version được hỗ trợ trước khi thực hiện nâng cấp nếu cần.

Một bản backup hợp lệ nhưng không có runtime binaries/KMS keys phù hợp vẫn có thể **không thể phục hồi nhanh**.

### 16.5. Replica set restore không giống standalone restore

Một data directory vật lý từ replica set chứa metadata/local state của member. Nếu mount nó vào một cluster đang hoạt động mà không có quy trình rõ, có thể tạo conflicts về identity, oplog timeline hoặc rollback.

Để **kiểm tra backup**, nên khôi phục vào môi trường **cô lập** theo thủ tục chính thức phù hợp topology. Để **khôi phục production**, xác định chiến lược cluster-wide rollback/rebuild/seed member rồi thực thi đúng runbook.

Không tự sửa collection **local** hoặc **config** để “ép” member vào replica set.

### 16.6. Sharded cluster restore

Phải phục hồi shards và config server metadata theo **coordinated backup generation** và restore workflow được hỗ trợ. Không chỉ restore Shard A rồi restart mongos và hy vọng B/config tự suy ra phần còn thiếu.

### 16.7. Restore vào region hoặc account khác

Các blockers ngoài MongoDB có thể gồm:

- Snapshot chưa copy xong.
- Thiếu quyền KMS ở region đích.
- Disk type/size không tương thích.
- Missing security group/firewall routes.
- Hostname/TLS certificate mismatches.
- Không có secret manager access.
- Thiếu backup catalog metadata.

RTO phải tính cả thời gian giải quyết những dependencies này.

## 17. Restore drill: bản backup chỉ đáng tin khi đã phục hồi được

### 17.1. Mục đích

Một **restore drill** là bài thực hành tái tạo dịch vụ từ backup trong môi trường an toàn để chứng minh:

- Snapshot tồn tại và có thể đọc.
- Những files cần thiết đầy đủ và nhất quán.
- WiredTiger có thể khởi động và recovery thành công.
- Collections/indexes/users cần thiết được khôi phục theo phạm vi.
- Dữ liệu tại restore point đúng kỳ vọng.
- Ứng dụng có thể chạy những truy vấn quan trọng.
- Thời gian restore phù hợp mục tiêu RTO.

### 17.2. Checklist sau khi mongod khởi động

| Kiểm tra | Câu hỏi |
| --- | --- |
| Process readiness | mongod mở storage engine không lỗi? |
| Logs | WiredTiger recovery kết thúc hợp lệ? |
| Collections | Các namespace chủ chốt còn? |
| Counts | Số document có phù hợp restore point? |
| Indexes | Index definitions chính có còn? |
| Sample documents | Các sự kiện nghiệp vụ chuẩn có đúng? |
| Transactions | Không thấy trạng thái giao dịch dở dang bất thường? |
| DB auth | Database users/roles và các secrets liên quan hoạt động? |
| Application smoke tests | API quan trọng có truy vấn được? |
| Performance | Latency/storage sau restore có chấp nhận được? |
| Time | RPO/RTO thực tế được ghi nhận? |

### 17.3. Ví dụ mongosh smoke checks

Sau khi restore **trong lab cô lập**, chạy bằng user có quyền phù hợp:

~~~javascript
const restored = db.getSiblingDB("mongo_backup_lab_343");

printjson({
  collections: restored.getCollectionNames(),
  eventCount: restored.getCollection("events").countDocuments({}),
  latestEvents: restored.getCollection("events")
    .find({}, { _id: 1, kind: 1, createdAt: 1 })
    .sort({ createdAt: -1 })
    .limit(5)
    .toArray(),
  indexes: restored.getCollection("events").getIndexes()
});
~~~

Các lệnh liệt kê collections/indexes cần quyền metadata thích hợp. Nếu reader hẹp không được chạy getIndexes, dùng một **auditor/restore validation identity** được cấp quyền theo quy trình, không mở root cho API.

### 17.4. validate collection

Trong **lab restore** có thể cân nhắc command **validate**:

~~~javascript
const lab = db.getSiblingDB("mongo_backup_lab_343");

printjson(lab.runCommand({
  validate: "events"
}));
~~~

Lệnh này có thể tốn tài nguyên và cần privileges phù hợp; không chạy validate toàn bộ một cluster production lớn như bước kiểm tra vô hại sau mỗi snapshot. Nó cũng không thay thế kiểm tra nghiệp vụ, transaction và RPO.

### 17.5. Tính actual RPO

Ví dụ:

~~~text
Latest known committed business event: 10:45:30
Latest event found after restore:       10:40:00

Actual observed data gap:
  khoảng 5 phút 30 giây
~~~

Muốn đo chính xác, cần **watermark nghiệp vụ/optime** đáng tin cậy, không chỉ lấy max(createdAt) nếu application clock có sai lệch hoặc dữ liệu đến muộn.

### 17.6. Tính actual RTO

~~~text
10:50:00 bắt đầu failover/restore decision
11:08:00 volumes đã sẵn sàng
11:14:00 mongod recovered
11:21:00 smoke checks đạt
11:25:00 API được đưa vào phục vụ

Actual recovery service duration:
  35 phút
~~~

Tùy định nghĩa nội bộ, RTO clock bắt đầu từ detection hay disaster declaration, nhưng phải **định nghĩa thống nhất trước khi đo**.

## 18. Lab logic: dữ liệu mẫu và mốc snapshot

### 18.1. Lưu ý về bản chất lab

Lab dưới đây tạo một **dataset mongosh có kiểm soát** để người học mô phỏng các mốc dữ liệu. Nó **không tạo physical snapshot bằng MongoDB**. Muốn thực sự kiểm tra storage snapshot phải có LVM/cloud volumes/backup platform được cấu hình trên môi trường riêng.

Mục tiêu là hiểu:

- Một backup có **restore point**.
- Những writes đến sau restore point **không tự có trong snapshot**.
- Checkpoint/journal và PITR có vai trò khác.
- Restore validation phải biết dữ liệu nào được kỳ vọng ở mốc đó.

### 18.2. Seed database lab

Chạy trong mongosh; không drop database:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_backup_lab_343");
  const events = lab.getCollection("events");

  const base = [
    {
      _id: "b343-e001",
      labTag: "snapshot343-v1",
      kind: "booking_created",
      bookingId: "booking-100",
      amountCents: 1200000,
      createdAt: ISODate("2026-01-15T10:00:00Z"),
      phase: "before-snapshot"
    },
    {
      _id: "b343-e002",
      labTag: "snapshot343-v1",
      kind: "payment_pending",
      bookingId: "booking-100",
      amountCents: 1200000,
      createdAt: ISODate("2026-01-15T10:01:00Z"),
      phase: "before-snapshot"
    },
    {
      _id: "b343-e003",
      labTag: "snapshot343-v1",
      kind: "payment_confirmed",
      bookingId: "booking-100",
      amountCents: 1200000,
      createdAt: ISODate("2026-01-15T10:02:00Z"),
      phase: "before-snapshot"
    }
  ];

  for (const doc of base) {
    events.replaceOne(
      { _id: doc._id },
      doc,
      { upsert: true }
    );
  }

  events.createIndex(
    { labTag: 1, createdAt: 1 },
    { name: "ix_snapshot343_lab_time" }
  );

  printjson({
    baselineCount: events.countDocuments({
      labTag: "snapshot343-v1",
      phase: "before-snapshot"
    }),
    firstThree: events.find({
      _id: { $in: base.map(d => d._id) }
    }).sort({ createdAt: 1 }).toArray()
  });
})();
~~~

Kết quả baseline: **3 events** với thời gian 10:00, 10:01 và 10:02 UTC. Script có IDs cố định và replaceOne nên có thể chạy lại trên collection lab riêng. Việc tạo index cùng tên chỉ hợp lệ khi chưa tồn tại với key pattern khác.

### 18.3. Mốc snapshot giả định

Giả sử snapshot đã được tạo ở thời điểm logic:

~~~text
T_snapshot = 2026-01-15T10:02:30Z

Trong snapshot:
  b343-e001
  b343-e002
  b343-e003
~~~

Đây chỉ là **bài tập giả lập**; câu query dưới đây không chứng minh filesystem snapshot tồn tại.

~~~javascript
const lab = db.getSiblingDB("mongo_backup_lab_343");
const events = lab.getCollection("events");
const snapshotBoundary = ISODate("2026-01-15T10:02:30Z");

printjson(
  events.find({
    labTag: "snapshot343-v1",
    createdAt: { $lt: snapshotBoundary }
  })
  .sort({ createdAt: 1 })
  .toArray()
);
~~~

Kết quả mong đợi có ba events baseline (khi dataset chưa bị người học thay đổi).

### 18.4. Ghi dữ liệu sau mốc

~~~javascript
const lab = db.getSiblingDB("mongo_backup_lab_343");
const events = lab.getCollection("events");

events.replaceOne(
  { _id: "b343-e004" },
  {
    _id: "b343-e004",
    labTag: "snapshot343-v1",
    kind: "booking_cancelled",
    bookingId: "booking-100",
    createdAt: ISODate("2026-01-15T10:04:00Z"),
    phase: "after-snapshot"
  },
  { upsert: true }
);

events.replaceOne(
  { _id: "b343-e005" },
  {
    _id: "b343-e005",
    labTag: "snapshot343-v1",
    kind: "refund_requested",
    bookingId: "booking-100",
    createdAt: ISODate("2026-01-15T10:05:00Z"),
    phase: "after-snapshot"
  },
  { upsert: true }
);

printjson({
  allLabEvents: events.countDocuments({
    labTag: "snapshot343-v1"
  }),
  beforeBoundary: events.countDocuments({
    labTag: "snapshot343-v1",
    createdAt: {
      $lt: ISODate("2026-01-15T10:02:30Z")
    }
  }),
  afterBoundary: events.countDocuments({
    labTag: "snapshot343-v1",
    createdAt: {
      $gte: ISODate("2026-01-15T10:02:30Z")
    }
  })
});
~~~

Kết quả mong đợi: **allLabEvents = 5**, **beforeBoundary = 3**, **afterBoundary = 2**.

### 18.5. Ý nghĩa restore

Nếu một physical snapshot thật đã được chụp **trước khi ghi e004/e005**, restore điểm đó sẽ **không tự chứa e004/e005**. Muốn có các sự kiện sau snapshot cần một cơ chế **PITR** hoặc tái tạo từ nguồn ngoài theo nghiệp vụ.

**Cảnh báo quan trọng:** Query lọc createdAt từ collection đang chạy **không phải phép restore snapshot**. Nó chỉ mô phỏng tập sự kiện trước/sau một mốc dựa vào field nghiệp vụ. Khi có late-arriving writes, sự kiện có createdAt cũ có thể được ghi sau snapshot; khi đó filter theo createdAt **không phản ánh chính xác** byte-level snapshot membership.

### 18.6. Mô phỏng event đến muộn

~~~javascript
const lab = db.getSiblingDB("mongo_backup_lab_343");
const events = lab.getCollection("events");

events.replaceOne(
  { _id: "b343-late" },
  {
    _id: "b343-late",
    labTag: "snapshot343-v1",
    kind: "late_external_notification",
    bookingId: "booking-100",
    createdAt: ISODate("2026-01-15T10:01:30Z"),
    ingestedAt: ISODate("2026-01-15T10:06:00Z"),
    phase: "after-snapshot"
  },
  { upsert: true }
);
~~~

Event được **ghi sau mốc snapshot** nhưng có **createdAt trước boundary**. Vì thế:

~~~javascript
events.find({
  createdAt: {
    $lt: ISODate("2026-01-15T10:02:30Z")
  }
});
~~~

có thể trả event b343-late trên **database hiện tại**, dù event ấy **không nằm trong physical snapshot cũ**. Bài học: muốn xác định **restore point thật**, không được chỉ nhìn timestamp ứng dụng.

## 19. Runbook chuẩn bị trước snapshot

### 19.1. Xác nhận backup target

1. Xác định deployment: standalone, replica set hay sharded cluster.
2. Xác định backup member và lý do chọn.
3. Xác nhận RPO/RTO/SLA của đợt backup.
4. Xác nhận tool/provider snapshot đã được hỗ trợ và kiểm chứng.
5. Có người chịu trách nhiệm và quyền truy cập KMS/storage.

### 19.2. Xác nhận health

1. Kiểm tra mongod khỏe mạnh.
2. Kiểm tra disk/free space, snapshot COW capacity nếu liên quan.
3. Kiểm tra replication lag, oplog window, member state.
4. Kiểm tra không đang initial sync/rollback/maintenance bất thường.
5. Kiểm tra snapshot/copy target đủ dung lượng và quota.

### 19.3. Xác nhận consistency

1. Kiểm kê dbPath, journal, data/index/metadata dependencies.
2. Map sang **volumes và mount points**.
3. Kiểm tra snapshot atomic hoặc consistency group.
4. Quyết định cần clean shutdown hay fsyncLock.
5. Xác định khi nào snapshot point được xem là cố định.
6. Thiết kế unlock/unfreeze trong mọi nhánh lỗi.

### 19.4. Xác nhận security

1. Backup identity không dùng chung với app root.
2. Snapshot được mã hóa.
3. Có key/KMS permissions khi restore.
4. Có retention và offsite policy.
5. Manifest không chứa secret plaintext.

### 19.5. Xác nhận restore

1. Biết target cô lập để restore.
2. Có version MongoDB tương thích.
3. Có runbook phục hồi topology.
4. Có smoke queries và expected outcomes.
5. Có lịch restore drill gần nhất/tiếp theo.

## 20. Runbook snapshot có phối hợp với WiredTiger

### 20.1. Giai đoạn A — Prepare

~~~text
Collect:
  deployment + member identity
  MongoDB version + FCV
  storageEngine
  dbPath + journal volumes
  rs/shard status
  source applied optime
  backup credentials + permissions
  encryption key references
~~~

Nếu thiếu thông tin volume mapping, **dừng** thay vì chụp đại một volume có tên gần giống dbPath.

### 20.2. Giai đoạn B — Quiesce theo runbook

Với cold backup: dừng mongod sạch sẽ trên node được phép.

Với hot snapshot: chạy fsyncLock theo điều kiện được hỗ trợ, giám sát thời gian khóa, và chuẩn bị đường unlock độc lập.

Với backup platform tích hợp: thực hiện bước coordination mà sản phẩm yêu cầu, **không tự chèn fsyncLock** nếu tool đã có cơ chế khác mà thêm lock sẽ gây hại.

### 20.3. Giai đoạn C — Create consistent snapshot point

Yêu cầu provider tạo một điểm chụp cho toàn bộ volumes cần thiết. Trạng thái thành công phải được hiểu theo hợp đồng provider:

~~~text
SUCCESS FOR COORDINATION
  = snapshot point đã cố định

SUCCESS FOR RETENTION/RESTORE
  = dữ liệu đã được lưu, verified và
    có thể dùng khi phục hồi
~~~

Hai trạng thái này có thể xuất hiện tại các thời điểm khác nhau. Sau khi fixed snapshot point, có thể giải phóng lock theo runbook, nhưng job vẫn phải theo dõi quá trình export/replication snapshot đến hoàn tất.

### 20.4. Giai đoạn D — Unlock và verify source

Sau storage snapshot point:

- fsyncUnlock/thaw hoặc restart member theo quy trình.
- Kiểm tra writes trở lại bình thường.
- Kiểm tra replication lag có giảm không.
- Kiểm tra member health.
- Kiểm tra metrics/alerts sau backup.

**Nếu unlock lỗi, đó là operational incident cần xử lý ngay**, kể cả khi snapshot upload vẫn tiếp diễn.

### 20.5. Giai đoạn E — Commit backup manifest

Chỉ coi backup **usable** khi:

- Snapshot state hợp lệ.
- Consistency group/volume IDs đầy đủ.
- No errors from provider.
- Key references/permissions đã xác minh.
- Manifest có restore point và topology.
- Backup catalog/retention policy được cập nhật.

Sau đó lên lịch restore drill hoặc kiểm tra integrity phù hợp.

### 20.6. Giai đoạn F — Monitor

Theo dõi:

~~~text
backup start -> coordination -> snapshot point
             -> transfer complete -> catalog ready
             -> restore validation
~~~

Không chỉ tạo alert nếu job không chạy; cần alert nếu **không có usable successful backup** trong khoảng RPO/retention đã đặt.

## 21. Failure scenarios và hành động

| Tình huống | Hậu quả | Hành động phù hợp |
| --- | --- | --- |
| Snapshot chỉ volume data, thiếu journal | Recovery có thể không hợp lệ | Inventory đầy đủ, snapshot group |
| Data/journal chụp lệch thời điểm | Không crash-consistent | Atomic group hoặc đúng coordination |
| Dùng cp/rsync trên live dbPath | Trộn phiên bản file | Không coi là physical backup hợp lệ |
| fsyncLock chạy nhưng quên unlock | Writes/replication đình trệ | Emergency unlock runbook, monitor |
| Giữ lock trong suốt giờ upload | Latency/lag lớn | Unlock khi snapshot point fixed |
| Snapshot secondary lag 15 phút | RPO sai so với primary | Ghi source optime, chọn member khỏe |
| Backup member đang initial sync | Dữ liệu có thể chưa hợp lệ/đầy đủ | Chờ healthy SECONDARY |
| Oplog archive bị hở | PITR không liên tục | Alert và tạo base backup/repair chain |
| Chụp shards tuần tự không phối hợp | Cross-shard state inconsistency | Coordinated sharded backup |
| Chỉ backup mongos | Không có database data | Backup shards + config servers |
| Volume snapshot đã tạo nhưng export lỗi | Backup chưa sẵn sàng restore | Theo dõi completion, không mark usable |
| Snapshot không có manifest | Không biết source/version/keys | Sinh manifest và catalog |
| Mất KMS key | Không giải mã restore được | DR plan cho key access |
| Backup cùng account với production | Có thể bị xóa cùng sự cố | Offsite/immutable/access separation |
| Restore vào mongod đang chạy | Có thể corruption | Stop target, restore cô lập |
| Trộn snapshot generations | Metadata/journal mismatch | Same consistency point |
| Restore vào MongoDB version bất tương thích | Engine không mở data files | Ghi version/FCV, theo supported path |
| Restore replica snapshot trực tiếp vào active RS | Oplog/member state có thể xung đột | Theo RS recovery procedure |
| Restore có dữ liệu nhưng API lỗi | Thiếu config/secrets/network/index | Restore drill end-to-end |
| RPO dựa vào snapshot timestamp tường | Sai khi secondary lag | Dùng optime/restore watermark |
| PITR chỉ là file local.oplog.rs cũ | Thiếu log sau snapshot | Continuous archive và backup tool |
| Test bằng timestamp createdAt | Không phản ánh late-arriving writes | Dùng restore point metadata |
| Chỉ kiểm tra checksum | Không chứng minh database-consistent | Khởi động và validate restore |

## 22. Tình huống thiết kế: ba hệ thống có nhu cầu khác nhau

### 22.1. Hệ A — Standalone cho dữ liệu không quan trọng

~~~text
Data: 15 GiB
RPO: 24 giờ
RTO: 4 giờ
Downtime: chấp nhận 10 phút ban đêm
~~~

Giải pháp có thể dùng **clean shutdown + full volume snapshot** vào khung bảo trì, sau đó restart và restore drill. Đơn giản nhưng có downtime; backup vẫn cần được mã hóa và lưu ngoài máy nguồn.

### 22.2. Hệ B — Replica set đặt lịch liên tục

~~~text
Data: 600 GiB
RPO: 30 phút
RTO: 90 phút
Primary: tải ghi cao
Dedicated secondary: có sẵn
~~~

Cân nhắc **snapshot secondary** với storage consistency group và fsync coordination nếu cần. Nhưng phải theo dõi lag/oplog, hoàn tất backup trong đủ thời gian và đo restore throughput. Nếu snapshot mỗi 30 phút nhưng secondary lag 20 phút, effective RPO đã xấu hơn dự tính.

### 22.3. Hệ C — Sharded transactional platform

~~~text
Data: 10 TiB
RPO: 1 phút
RTO: 60 phút
Multiple shards + config server RS
Distributed transactions
~~~

Đây không phải bài toán có thể giải bằng **một cron job snapshot trên mỗi host** mà không có coordination. Cần giải pháp hỗ trợ consistent cluster backup và continuous log/PITR, restore testing nghiêm ngặt, hạ tầng dự phòng và chiến lược traffic cutover.

### 22.4. Cùng một storage engine nhưng yêu cầu backup khác

WiredTiger vẫn là storage engine ở cả ba hệ. Điểm khác là:

- Tính sẵn sàng được phép ảnh hưởng.
- Độ lớn dữ liệu và topology.
- RPO/RTO.
- Mức coordination cần thiết.
- Phụ thuộc hệ thống bên ngoài.

Không có một lệnh snapshot dùng được không cần điều chỉnh cho mọi hệ.

## 23. Câu hỏi thường gặp

### 23.1. Tôi có thể copy /var/lib/mongodb trong lúc mongod chạy không?

**Không coi một phép copy file thông thường khi server đang hoạt động là physical backup nhất quán.** Các file có thể được copy ở thời điểm khác nhau trong khi WiredTiger đang thay đổi. Dùng phương thức backup được hỗ trợ, clean shutdown, hoặc snapshot storage atomic có phối hợp phù hợp.

### 23.2. Có journal thì snapshot bất kỳ có được không?

**Không.** Journal giúp crash recovery khi các files thuộc một trạng thái storage phù hợp. Nó không bảo đảm phục hồi một tập dữ liệu được ghép từ nhiều thời điểm không nhất quán.

### 23.3. Chỉ cần fsyncLock rồi dùng rsync lâu bao nhiêu cũng được?

Giữ lock trong suốt rsync dài có thể gây write outage/replication lag. Khi dùng snapshot storage, mục tiêu là tạo **mốc ảnh chụp atomic nhanh** rồi unlock khi provider bảo đảm điểm đó cố định. Nếu dùng cách copy dưới lock hoặc cold copy, phải tính kỹ downtime và semantics, thường không thích hợp cho hệ ghi lớn.

### 23.4. Chụp một secondary có ảnh hưởng primary không?

Không khóa trực tiếp writes trên primary, nhưng vẫn có tác động gián tiếp tới HA/quorum, replication lag, oplog window và tài nguyên. Một backup member có health kém hoặc bị khóa quá lâu vẫn là rủi ro vận hành.

### 23.5. Có snapshot là đã có PITR chưa?

**Chưa.** Snapshot cung cấp một điểm dữ liệu. Muốn phục hồi giữa hai snapshots cần cơ chế log/continuous backup và quy trình replay chính thức, không có khoảng hở.

### 23.6. Có thể restore WiredTiger data files từ phiên bản cũ sang mọi phiên bản mới không?

Không được giả định. Physical storage format, FCV và quy trình upgrade/downgrade có ràng buộc. Cần kiểm tra supported restore path và thử trong môi trường cô lập.

### 23.7. Có thể dùng backup của một shard để restore cả cluster không?

Không. Sharded cluster còn chứa nhiều shards và config server metadata; backup toàn hệ thống phải phối hợp các thành phần và restore generation.

### 23.8. Backup trên cloud có cần tự lưu key không?

Cần có **quy trình bảo đảm KMS/key access khi restore**, nhưng không nên copy plaintext keys vào cùng backup. Sử dụng secret/key management phù hợp và kiểm thử cross-region/account permissions.

### 23.9. Checksum đúng nhưng mongod không start?

Checksum chỉ cho thấy bytes không bị thay đổi so với một nguồn tham chiếu. Nếu nguồn là một live-file-copy không nhất quán, hash vẫn có thể đúng. Cần xem restore logs, storage consistency, version, FCV, journal và encryption.

### 23.10. Đã có replication thì tại sao còn cần backup?

Replication giúp availability nhưng **xóa nhầm, cập nhật sai, dữ liệu lỗi và một số kiểu compromise có thể được nhân bản sang các thành viên**. Backup tạo một mốc độc lập theo thời gian, nên cần retention và khả năng restore ngoài replica set hiện tại.

## 24. Bài tập thực hành

### Bài 1 — Khái niệm

Giải thích sự khác nhau giữa volume snapshot, crash-consistent backup, application-consistent backup và MongoDB readConcern snapshot. Cái nào có thể dùng làm vật liệu phục hồi database?

### Bài 2 — WiredTiger

Mô tả vai trò của checkpoint và journal trong crash recovery. Tại sao không nên lấy một file checkpoint làm backup độc lập?

### Bài 3 — Copy live files

Một script copy file A lúc 10:00, file B lúc 10:15 và journal lúc 10:20 trong khi mongod vẫn ghi. Phân tích tại sao tất cả lệnh copy thành công vẫn không chứng minh bản backup hợp lệ.

### Bài 4 — Một volume

Một MongoDB dbPath và journal đều nằm trên cùng volume. Storage provider cung cấp atomic crash-consistent volume snapshots. Những điều kiện nào cần kiểm tra trước khi dùng chúng làm backup?

### Bài 5 — Nhiều volumes

dbPath trải trên volume A và journal ở volume B. A được chụp lúc 12:00:00, B lúc 12:00:10. Vì sao không thể gọi hai snapshots đó là một consistency point? Đề xuất phương án khắc phục.

### Bài 6 — fsyncLock

Mục đích của fsyncLock trong runbook snapshot là gì? Vì sao không nên giữ lock cho tới khi toàn bộ backup upload lên object storage?

### Bài 7 — Unlock failure

Snapshot API timeout sau fsyncLock. Thiết kế đường cleanup/alert/manual unlock. Những metrics/health checks nào cần xem sau đó?

### Bài 8 — Cold backup

Lập quy trình cold backup một mongod trong lab: chuẩn bị, shutdown, snapshot, restart, validate. Những nhược điểm nào làm cách này khó áp dụng trên primary production?

### Bài 9 — Secondary lag

Primary optime 10:30, backup secondary optime 10:25, snapshot wall-clock 10:31. RPO thực tế có thể khác thời gian tạo snapshot thế nào?

### Bài 10 — Majority write

Một write được majority-acknowledged trên replica set ba members, nhưng secondary B chưa apply write. Snapshot B có chắc chứa write đó không? Giải thích.

### Bài 11 — Oplog window

Backup secondary bị khóa writes 30 phút, sau đó phải catch up. Oplog window của primary chỉ còn 20 phút. Những rủi ro nào xuất hiện?

### Bài 12 — Chọn member

Trong replica set 3 members, hãy chọn một member làm backup source và nêu các điều kiện health, replication và quorum cần kiểm tra.

### Bài 13 — Snapshot point vs completion

Provider trả job accepted ở 10:00, snapshot point được xác lập ở 10:00:05 và upload hoàn tất 10:18. Khi nào có thể unlock? Khi nào mới đánh dấu backup usable?

### Bài 14 — RPO

Backup mỗi giờ, sự cố lúc 10:59 và snapshot cuối lúc 10:00. Không có PITR. Tính mức mất dữ liệu tiềm năng và đề xuất thay đổi policy để đạt RPO 10 phút.

### Bài 15 — RTO

Restore volume mất 35 phút, mongod recovery 8 phút, kiểm tra dữ liệu 12 phút, cutover 10 phút. RTO thực tế tối thiểu là bao nhiêu nếu các bước tuần tự?

### Bài 16 — PITR

Một hệ thống có base snapshot lúc 08:00, liên tục lưu oplog tới 12:00 và sự cố lúc 11:59. Muốn restore tới 11:55 cần những điều kiện về log continuity, restore engine và timestamp?

### Bài 17 — PITR gap

Oplog archive bị gián đoạn 45 phút nhưng snapshot lịch vẫn chạy. Vì sao không thể tuyên bố PITR tới mọi thời điểm trong khoảng đó?

### Bài 18 — Sharded cluster

Một chunk migrate từ A sang B giữa hai lần snapshot. Giải thích rủi ro metadata và dữ liệu nếu không có cluster-wide coordination.

### Bài 19 — Config server

Vì sao snapshot các shards mà không có config server metadata không đủ để khôi phục một sharded cluster?

### Bài 20 — Balancer

Dừng balancer có tự bảo đảm snapshot toàn sharded cluster nhất quán không? Còn vấn đề gì với application writes, transactions và oplog?

### Bài 21 — Atlas

Lập danh sách câu hỏi cần hỏi trước khi tin vào Atlas backup: tier, snapshot schedule, retention, PITR, restore target, key policy và latest successful backup.

### Bài 22 — Encryption

Snapshot mã hóa còn nguyên nhưng tổ chức đã mất KMS key. Điều gì xảy ra khi restore? Thiết kế kiểm thử cross-account/region key access.

### Bài 23 — Immutable backup

Vì sao replication cùng cluster không thay immutable/offsite backup? Phân tích tình huống ransomware hoặc admin xóa nhầm toàn bộ collection.

### Bài 24 — Manifest

Đề xuất backup manifest có version, FCV, storage engine, dbPath, volumes, snapshot IDs, applied optime, consistency point, encryption key reference và restore drill result.

### Bài 25 — Version compatibility

Một snapshot WiredTiger được tạo trên MongoDB version X nhưng target chỉ có binary version Y. Nêu những kiểm tra cần làm trước khi khởi động mongod với data files đó.

### Bài 26 — Restore drill

Thiết kế restore drill cô lập: mount volumes, khởi động mongod, kiểm tra logs, collections, indexes, business samples và tính actual RPO/RTO.

### Bài 27 — Lab seed

Chạy seed ở mục 18. Đối chiếu ba events trước mốc snapshot. Sau khi thêm e004/e005, giải thích vì sao một physical snapshot ở 10:02:30 không tự chứa hai events sau.

### Bài 28 — Late-arriving event

Event b343-late được ghi lúc 10:06 nhưng createdAt=10:01:30. Vì sao filter createdAt < 10:02:30 trên database hiện tại không chứng minh event đã có trong snapshot cũ?

### Bài 29 — Business reconciliation

MongoDB restore về 10:00 nhưng payment provider đã charge ở 10:15. Hệ thống cần quy trình nào để tránh charge lần hai hoặc mất thông tin thanh toán?

### Bài 30 — Runbook review

Nhóm A đề xuất chạy fsyncLock, rsync live dbPath trong 3 giờ rồi unlock. Nhóm B đề xuất dùng một secondary khỏe mạnh, tạo atomic volume snapshot trong vài giây rồi unlock và copy từ snapshot. So sánh rủi ro, điều kiện và các kiểm tra cần có.

### Bài 31 — Backup monitoring

Thiết kế dashboard theo dõi backup age, latest usable backup, snapshot completion, oplog archival gap, replication lag, fsyncLock duration, storage capacity, KMS access và restore drill age.

### Bài 32 — Role separation

Ai nên có quyền tạo/xóa snapshots, restore MongoDB, đọc backup manifest, quản lý KMS và đọc dữ liệu sau restore? Vì sao không để một credential API production làm tất cả?

### Bài 33 — Storage provider contract

Một cloud API hỗ trợ chụp ba volumes trong một request nhưng không nói rõ consistency group. Bạn cần xác nhận điều gì trước khi tuyên bố snapshot MongoDB hợp lệ?

### Bài 34 — Thiết kế RPO/RTO

Một hệ thống 3 TiB, replica set ba members, RPO 15 phút, RTO 90 phút. Hãy đề xuất snapshot schedule, PITR policy, backup member, offsite, encryption, restore infrastructure và cách chứng minh mục tiêu bằng drill.

## 25. Tài liệu tham khảo

- MongoDB Manual — [Backup Methods](https://www.mongodb.com/docs/manual/core/backups/).
- MongoDB Manual — [Back Up and Restore with Filesystem Snapshots](https://www.mongodb.com/docs/manual/tutorial/backup-with-filesystem-snapshots/).
- MongoDB Manual — [Back Up and Restore a Sharded Cluster](https://www.mongodb.com/docs/manual/tutorial/backup-sharded-cluster-with-filesystem-snapshots/).
- MongoDB Manual — [db.fsyncLock()](https://www.mongodb.com/docs/manual/reference/method/db.fsyncLock/).
- MongoDB Manual — [db.fsyncUnlock()](https://www.mongodb.com/docs/manual/reference/method/db.fsyncUnlock/).
- MongoDB Manual — [WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/).
- MongoDB Manual — [Journaling](https://www.mongodb.com/docs/manual/core/journaling/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).
- MongoDB Manual — [Replication Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/).
- MongoDB Manual — [Feature Compatibility Version](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/).
- MongoDB Atlas — [Backup Overview](https://www.mongodb.com/docs/atlas/backup-restore-cluster/).
- MongoDB Atlas — [Point-in-Time Restore](https://www.mongodb.com/docs/atlas/backup-restore-cluster/#point-in-time-restore).
- MongoDB Ops Manager — [Backup and Restore](https://www.mongodb.com/docs/ops-manager/current/backup/).
- MongoDB Database Tools — [mongodump](https://www.mongodb.com/docs/database-tools/mongodump/).
- MongoDB Database Tools — [mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/).

**Kết luận:** **Snapshot** là một bản chụp storage tại một mốc, không phải phép màu làm mọi tập file MongoDB trở nên nhất quán. Với **WiredTiger**, cần hiểu **checkpoint, journal, dbPath và crash recovery**; chỉ coi backup vật lý đáng tin khi các thành phần cần thiết được chụp thành **một trạng thái atomic/consistent**, đặc biệt khi có nhiều volumes. Có thể phối hợp bằng **clean shutdown**, **fsyncLock/fsyncUnlock** hoặc một **backup platform hỗ trợ**, ưu tiên backup từ secondary phù hợp để giảm tác động primary nhưng vẫn phải kiểm tra **replication lag, oplog window, RPO/RTO**. Với **sharded cluster**, snapshots phải được phối hợp trên shards và config servers; snapshot từng host độc lập chưa đủ. Cuối cùng, backup phải được **mã hóa, lưu độc lập, có manifest, có đường khôi phục được hỗ trợ và được diễn tập restore định kỳ**. Một bản snapshot chỉ thật sự có giá trị khi bạn **có thể khởi động MongoDB từ nó, xác minh dữ liệu và khôi phục dịch vụ đúng mục tiêu**.
