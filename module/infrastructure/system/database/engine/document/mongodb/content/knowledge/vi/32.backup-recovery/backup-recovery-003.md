# Tính nhất quán của bản sao lưu khi hệ thống vẫn đang ghi

Một hệ thống MongoDB phục vụ đơn hàng, ví điện tử, telemetry hoặc dữ liệu giao dịch thường **không thể dừng toàn bộ request** chỉ để sao lưu. Trong lúc công cụ backup đọc collection đầu tiên, ứng dụng vẫn có thể insert, update, delete, commit transaction, đổi index hoặc chạy migration. Khi restore, điều quan trọng không chỉ là **có file backup**, mà là file đó có mô tả một **trạng thái dữ liệu hợp lệ tại một thời điểm xác định** hay không.

Ví dụ ứng dụng chuyển 200.000 đồng từ ví A sang ví B. Nếu bản sao lưu ghi nhận **số dư A sau khi trừ tiền** nhưng **số dư B trước khi cộng tiền**, tổng số dư hệ thống có thể sai sau restore — dù từng file BSON đọc được và cả hai collections đều có đủ dữ liệu. Đây là một ví dụ của **bản sao lưu không nhất quán theo thời điểm**.

Mục tiêu của bài **“Tính nhất quán của bản sao lưu khi hệ thống vẫn đang ghi”** thuộc chương **Sao lưu và phục hồi**, module *Database Engine Document MongoDB*, là hiểu:

1. **Nhất quán** trong backup nghĩa là gì, khác với “đã copy xong” và khác **RPO/RTO** như thế nào.
2. Vì sao quét nhiều documents/collections trong lúc writes tiếp diễn dễ tạo bản dump **không tương ứng một thời điểm duy nhất**.
3. Khi nào có thể dùng **`mongodump --oplog`**, **filesystem snapshots**, hoặc **Atlas/Cloud Manager/Ops Manager managed backups**.
4. Vai trò **oplog, journal, WiredTiger checkpoint, write concern, read concern, snapshot read, replication lag** và giới hạn của mỗi cơ chế.
5. Vì sao **sharded cluster** phức tạp hơn replica set và không thể ghép tùy ý các bản dump từng shard.
6. Cách thiết kế **backup/restore runbook, PITR, giám sát oplog window, kiểm tra invariant sau restore**, cùng các bài tập tình huống.

> **Phạm vi:** Các ví dụ shell chạy trên **môi trường lab/DR đã chuẩn bị và được phép**. Không chạy lệnh khôi phục, dừng balancer, khóa ghi, drop dữ liệu hoặc reset replica set trên production chỉ để thử bài. Cú pháp/giới hạn thay đổi theo MongoDB Server, Database Tools và Atlas version; tài liệu chính thức được dẫn ở phần cuối.

## 1. “Nhất quán” có nhiều tầng, không phải chỉ một cờ backup

### 1.1. Ba khái niệm phải tách biệt

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **File/format integrity** | Backup có thể đọc, không bị thiếu/truncated/checksum lỗi. | File `backup.archive` khôi phục được BSON. |
| **Database point-in-time consistency** | Tập dữ liệu phản ánh một trạng thái MongoDB hợp lệ tại **cùng một mốc logic**; không nhìn thấy nửa một transaction. | Ví A và ví B cùng ở trước hoặc sau transaction chuyển tiền. |
| **Application/business consistency** | Các quy tắc nghiệp vụ vẫn đúng, kể cả dữ liệu ngoài MongoDB nếu được bao gồm. | Thanh toán, booking và sự kiện gửi Kafka thống nhất cùng một cutover. |

**File hợp lệ không có nghĩa dữ liệu nhất quán.** Một file dump hoàn chỉnh về mặt bytes vẫn có thể ghép collection A ở 10:00:03 với collection B ở 10:00:40. Ngược lại, bản sao lưu nhất quán ở 10:00 vẫn có thể **cũ** so với sự kiện lúc 10:05; đó là vấn đề **RPO**, không phải lỗi nhất quán.

### 1.2. Nhất quán theo một thời điểm

Giả sử MongoDB nhận:

~~~text
10:00:00  Orders count = 100; Payments count = 100
10:00:02  Transaction T creates order + payment atomically
10:00:03  Orders count = 101; Payments count = 101
~~~

Một bản sao lưu **point-in-time consistent** hợp lệ có thể đại diện:

- **Trước transaction T:** Orders=100 và Payments=100.
- **Sau transaction T:** Orders=101 và Payments=101.

Nhưng không nên trở thành **Orders=101, Payments=100** do lấy từ hai thời điểm khác nhau. Đây là vấn đề nghiêm trọng ngay cả khi từng collection riêng lẻ trông không có lỗi.

### 1.3. Atomicity tại write time không tự bảo đảm backup

MongoDB hỗ trợ **atomicity ở từng document** và multi-document transactions khi được triển khai đúng. Điều đó bảo vệ operations trực tiếp trên live database. Tuy nhiên, một **công cụ đọc tuần tự** không có snapshot boundary nhất quán có thể thấy collection thứ nhất ở thời điểm sau T và thứ hai ở thời điểm trước T.

**Transaction của ứng dụng và snapshot consistency của bản sao lưu là hai cơ chế khác nhau.** Không thể kết luận rằng “ứng dụng dùng MongoDB transaction nên `mongodump` thường chắc chắn consistent”.

### 1.4. Phân biệt crash-consistent và application-consistent

| Thuật ngữ | Mô tả | Điều chưa chắc đạt |
|---|---|---|
| **Crash-consistent snapshot** | Ảnh dữ liệu như sau một lần máy chủ dừng đột ngột, có thể recovery bằng journal/WiredTiger nếu copy đủ thành phần. | Không nhất thiết đồng bộ nhiều node/shards hoặc external queues. |
| **Database-consistent point-in-time backup** | Dữ liệu sau recovery ở một mốc logic chung với write ordering/transaction semantics. | Không tự bảo đảm dữ liệu ở Kafka, object storage, payment gateway. |
| **Application-consistent backup** | Được phối hợp theo business invariant, có thể gồm quiesce/markers/outbox và external systems. | Phụ thuộc phạm vi ứng dụng, không chỉ lệnh MongoDB. |

Từ “snapshot” có thể nói đến **OS filesystem snapshot**, **MongoDB readConcern snapshot**, **Atlas managed snapshot** hoặc **VM/cloud disk snapshot**. Các thứ này không mặc nhiên có cùng guarantee.

## 2. Lược đồ thời gian: lỗi đọc trong khi hệ thống đang ghi

### 2.1. Dump hai collections nối tiếp

~~~text
Timeline:

             10:00        10:02          10:04       10:06
              |             |              |           |
mongodump:    [read accounts]              [read ledger]
                            |
app write:                  [commit transaction T]

Backup accounts:
  số dư trước T

Backup ledger:
  bút toán sau T

Restore:
  accounts cũ + ledger mới -> lệch invariant.
~~~

Trên một replica set, khi không dùng cơ chế bảo đảm snapshot đồng nhất, một bản dump nhiều collections được đọc **trong các cửa sổ khác nhau**. MongoDB Database Tools ghi rõ: **không dùng `--oplog` thì khi có ghi trong lúc dump, kết quả không phản ánh một thời điểm duy nhất**.

### 2.2. Một collection cũng có thể thay đổi trong lúc quét

Ví dụ job đang xuất 10 triệu documents:

~~~text
Dump cursor:
  đọc _id 1..1000000

Writer:
  update một document đã đọc
  delete một document chưa đọc
  insert document mới

Dump cursor:
  tiếp tục đọc phần còn lại
~~~

Tùy thứ tự quét/query/index/engine, backup có thể không tương ứng với một snapshot nhất quán. Không nên suy từ ví dụ rằng tất cả các biến đổi cụ thể nhất định xuất hiện/biến mất theo một thứ tự cố định; lỗi căn bản là **không có thời điểm chốt chung**.

### 2.3. “Đã đọc majority” không tự giải quyết

Một reader dùng `readConcern:"majority"` nhận các dữ liệu đã được majority-acknowledged theo semantics server. Nhưng nếu reader quét collections ở **nhiều thời điểm**, dữ liệu vẫn có thể khác nhau do writes mới đã được majority commit giữa các lần đọc.

**Majority durability không đồng nghĩa mọi read có cùng snapshot timestamp.** Cần phân biệt với `readConcern:"snapshot"` trong các API/transactions hỗ trợ, và với backup agent có cơ chế pin/chọn một mốc recovery riêng.

## 3. RPO, RTO và mục tiêu consistency

Sự thành công của backup/restore nên được định nghĩa bằng ba tiêu chí:

- **Consistency:** Restore ra trạng thái hợp lệ tại một mốc logic xác định.
- **Recovery Point Objective (RPO):** Mức dữ liệu tối đa có thể mất so với thời điểm xảy ra sự cố.
- **Recovery Time Objective (RTO):** Thời gian tối đa để dịch vụ phục hồi hoạt động theo SLA.

Ví dụ:

~~~text
Backup snapshot:        09:00
Sự cố:                   09:47
Restore tới snapshot:   09:00

Data sau 09:00 bị mất nếu không có log/PITR.
Khoảng mất dữ liệu có thể lên tới 47 phút.
~~~

Bản backup ở 09:00 có thể hoàn toàn **consistent** nhưng không đáp ứng **RPO 5 phút**. Muốn giảm RPO, cần capture changes sau snapshot (ví dụ managed continuous cloud backup/PITR) và đảm bảo restore tới timestamp được hỗ trợ.

### 3.1. Các loại đòi hỏi thực tế

| Loại ứng dụng | Vấn đề lớn | Hướng đánh giá |
|---|---|---|
| Demo/dev, dữ liệu tái tạo được | RPO có thể dài. | `mongodump` theo lịch, test restore. |
| Knowledge base/API nhỏ | Dữ liệu liên tục cập nhật nhưng ít transaction. | Replica set `mongodump --oplog` hoặc managed snapshot. |
| Marketplace có orders/payments | Cần consistency và RPO thấp. | Coordinated backup/PITR, test business invariants. |
| Sharded SaaS 20 shards | Cross-shard transaction và chunk migration. | Managed cluster-wide backups/PITR. |
| IoT throughput cao | Oplog churn, storage/IOPS lớn. | Online snapshot solution, monitor oplog window. |
| Hệ thống chịu compliance | WORM/retention/encryption/audit. | Managed policy + immutable offsite copies + restore drills. |

**RPO là yêu cầu kinh doanh**, không phải giá trị bạn đo được bằng dung lượng file. RTO phải được **diễn tập restore**; tốc độ `mongodump` không nói được thời gian rebuild index, replay oplog, kiểm thử dữ liệu hay chuyển DNS/connection strings.

## 4. MongoDB replication, oplog, journal và checkpoint

### 4.1. Replica set và oplog

Replica set có **primary** tiếp nhận writes và **secondaries** đồng bộ các thao tác thông qua **oplog** — bộ nhật ký thao tác có thứ tự, giữ trong `local.oplog.rs` theo điều kiện và topology.

~~~text
Client writes
     |
     v
  Primary
     |
     +-- data files / WiredTiger
     |
     +-- oplog entries ------> Secondary A applies
                        \----> Secondary B applies
~~~

Oplog phục vụ replication và một số backup/recovery workflows. Nó **không phải nhật ký bất biến giữ mãi mãi**. Khi ghi quá nhiều so với kích thước/thời gian retention, các entries cũ có thể bị ghi đè; backup dựa vào oplog có thể gặp **history gap**.

### 4.2. Tại sao cần oplog trong online dump?

Trong lúc `mongodump` quét data, tool có thể ghi nhận **những operations diễn ra trong cửa sổ dump**. Khi restore, replay các operations theo thứ tự phù hợp giúp tạo một trạng thái tại một thời điểm logic, thay vì chỉ ghép các collections đã được đọc nối tiếp.

Đây là vai trò của `mongodump --oplog` và `mongorestore --oplogReplay` trên **replica set**. Nhưng các flags đó **không làm tự động hỗ trợ global snapshot của sharded cluster**, vì mỗi shard replica set có lịch sử riêng và còn có metadata config server.

### 4.3. Oplog window

**Oplog window** là khoảng thời gian giữa entry mới nhất và cũ nhất còn giữ trong oplog:

~~~text
Oplog oldest:  08:00
Oplog newest:  12:00
Window:         4 giờ
~~~

Nếu một backup workflow cần replay events từ 07:30 nhưng oldest entry chỉ từ 08:00, không thể tái tạo đầy đủ từ những events đã bị ghi đè. Tùy implementation, dump/agent có thể fail hoặc yêu cầu resync. Giám sát **oplog history trong giờ peak writes**, không chỉ trung bình ngày.

### 4.4. WiredTiger journal

**Journal** ghi các thay đổi cần thiết để phục hồi dữ liệu sau một crash theo cơ chế durability của WiredTiger. Một filesystem copy đúng cách cần tính đến **cả data files và journal**, hoặc phải dùng quy trình flush/lock khi chúng nằm trên nhiều volumes.

Không thể chỉ copy vài file `.wt` trong lúc mongod đang ghi rồi tuyên bố có thể restore. Một bản copy từng file thực hiện nối tiếp có thể lấy những phần không cùng checkpoint/journal state.

### 4.5. WiredTiger checkpoints

WiredTiger định kỳ tạo **checkpoints** biểu diễn trạng thái dữ liệu ổn định. MongoDB Manual mô tả checkpoints xảy ra khi có đủ dữ liệu hoặc khoảng thời gian (thường khoảng một phút), nhưng backup được restore ở mốc cụ thể nào còn phụ thuộc journal, snapshot method và node state.

**Checkpoint không thay thế oplog/PITR**: nó giúp crash recovery, không phải dịch vụ tự thu thập mọi change events và khôi phục đến thời gian bất kỳ.

### 4.6. Majority commit và rollback

Với `writeConcern:{w:"majority"}`, một write được xác nhận sau khi đáp ứng ngưỡng majority theo semantics deployment, giúp tránh trường hợp write chỉ tồn tại trên primary cũ rồi bị rollback sau election.

Nhưng:

- Majority ack **không** có nghĩa backup đã chứa write; backup có recovery point riêng.
- `w:1` có thể được ứng dụng thấy “success” nhưng vẫn có khả năng rollback nếu chưa replicate đủ.
- Secondary có thể **lag**; backup đọc secondary phản ánh trạng thái của node đó chứ không mặc định bằng primary “ngay bây giờ”.
- Consistent point-in-time backup có thể hoàn toàn đúng **nhưng trước** những writes gần nhất.

## 5. Các phương pháp sao lưu và guarantee khi writes tiếp diễn

| Phương pháp | Có thể sao lưu khi writes đang chạy? | Consistency cần hiểu | Khuyến nghị |
|---|---|---|---|
| `mongodump` thông thường | Về kỹ thuật có thể chạy. | **Không** bảo đảm một điểm thời gian khi có writes đồng thời. | Dữ liệu lab/dev, migration có quiesce, không dùng làm bảo đảm giao dịch online. |
| `mongodump --oplog` trên **một replica set** | Có, nếu đáp ứng điều kiện và không có DDL bị cấm. | Tool dùng oplog để đưa dump tới trạng thái tại một thời điểm logic khi restore với `--oplogReplay`. | Online logical backup toàn replica set, quy mô vừa, test restore. |
| Snapshot block-level **một node** có đầy đủ dữ liệu/journal trên một atomic volume | Có thể tạo snapshot trong lúc node chạy theo quy trình platform/Manual. | **Crash-consistent** cho node đó; phục hồi journal/checkpoint. | Self-managed replica set, cần cấu hình storage an toàn. |
| Copy dữ liệu từng file bằng `cp`/`rsync` khi mongod đang ghi | Có thể copy bytes, nhưng không đảm bảo hữu dụng. | **Không** phải snapshot atomic; file được đọc ở nhiều thời điểm. | Tránh. |
| Filesystem snapshot với journal/data **khác volumes** | Cần khóa/đình chỉ writes theo thủ tục Manual nếu không có atomic multi-volume snapshot được chứng minh. | Không bảo đảm nếu các volumes được chụp lệch thời điểm. | Dùng `fsyncLock`/quiesce hoặc phối hợp storage-level consistency. |
| Manual backup toàn **sharded cluster** bằng dump/snapshots | Yêu cầu quiesce writes và dừng balancer/schema transformations theo Manual. | Không tự bảo đảm cluster-wide atomicity nếu lấy từng shard khi đang ghi. | Chỉ dùng runbook chuyên biệt, kiểm tra version. |
| Atlas Cloud Backup coordinated snapshots | Có, với cluster/tier có tính năng. | Managed **cluster-wide consistent snapshots**, kể cả sharded cluster theo điều kiện. | Ưu tiên nếu muốn online backup có quản lý. |
| Atlas Continuous Cloud Backup / PITR | Có, với tính năng và retention window được bật. | Snapshot + captured oplog cho phép chọn recovery point trong cửa sổ phù hợp. | RPO ngắn, cần phục hồi tới trước thao tác sai. |
| Ops Manager / Cloud Manager managed backup | Có, theo support/topology. | Backup agents phối hợp snapshot/PIT và metadata, gồm sharded clusters theo sản phẩm. | Self-managed enterprise/large topology. |

**Lưu ý:** “Online backup” có hai nghĩa: (1) không tắt daemon, và (2) **người dùng vẫn có thể ghi bình thường**. Một snapshot thủ công có thể tạo khi `mongod` còn chạy nhưng vẫn phải **tạm dừng writes** — nghĩa (1) đúng, (2) sai. Hãy nêu rõ yêu cầu khi chọn giải pháp.

### 5.1. Tốc độ backup không quyết định consistency

Filesystem snapshot thường nhanh vì tạo bản ảnh copy-on-write thay vì đọc toàn bộ files ngay tại thời điểm tạo. Nhưng:

- Snapshot chỉ nhanh ở pha **create snapshot**, còn copy/transfer/archive/restore vẫn cần I/O.
- Snapshot cùng storage array không thay thế **offsite copy** khi cả site mất điện/cháy.
- Snapshot nhanh trên từng shard nhưng chụp không đồng bộ vẫn có thể tạo cluster snapshot không nhất quán.
- Khả năng undo/rollback/apply journal tùy phiên bản engine và trạng thái files.

### 5.2. Tính nhất quán và khả năng khôi phục là hai câu hỏi

Một backup có thể consistent nhưng thất bại khi restore vì:

- Bị thiếu file journal/index/metadata hoặc file archive bị truncate.
- Version/FCV target không tương thích.
- Snapshot thiếu encryption keys/remote KMS permissions.
- Restore process thiếu dung lượng, bị kill giữa chừng.
- Index build/validation không hoàn tất.
- Sharded topology/config server không tương thích.

Do đó **readback archive/checksum** là bước kỹ thuật, còn **restore drill + kiểm tra dữ liệu** mới chứng minh khả năng phục hồi thực tế.

## 6. `mongodump` thông thường khi writes vẫn tiếp tục

MongoDB Database Tools `mongodump` tạo **logical backup**: BSON documents và metadata định nghĩa index/options. Đây **không** phải một ảnh WiredTiger checkpoint vật lý; index data thường được **build lại** khi `mongorestore`.

Ví dụ trên command line của môi trường lab:

~~~bash
# Chỉ là ví dụ cho replica set lab:
mongodump \
  --uri="mongodb://backupuser@rs-lab:27017/?replicaSet=rsLab" \
  --archive="./dump-without-oplog.archive"
~~~

Nếu ứng dụng đang insert/update khi tool quét dữ liệu, file archive có thể chứa các collections/documents ở **những thời điểm khác nhau**.

### 6.1. Tại sao từng collection nhìn hợp lý vẫn nguy hiểm?

Giả sử:

~~~javascript
// Normal collections trên một replica set lab.
db.accounts.insertMany([
  { _id: "A", balanceMinor: 100000 },
  { _id: "B", balanceMinor: 100000 }
])

db.ledger.insertOne({
  _id: "TX-1",
  from: "A",
  to: "B",
  amountMinor: 20000,
  state: "COMMITTED"
})
~~~

Nếu `accounts` được đọc trước khi thực hiện transaction cập nhật số dư, còn `ledger` được đọc sau transaction, backup có thể chứa **số dư cũ + ledger mới**. Không có cách khôi phục invariant chỉ bằng việc file BSON được parse thành công.

### 6.2. Thêm `--readPreference=secondary` có đủ không?

Không. Chuyển nguồn đọc sang secondary giúp giảm tải primary nhưng:

- Secondary thường **nhận và apply oplog liên tục** trong lúc dump.
- Nó có thể lag so với primary.
- Các collections vẫn có thể được đọc tại **các thời điểm khác nhau**.
- Backup vẫn có thể chứa những writes đã được apply trong khi tool đang quét.

**Read preference là lựa chọn nguồn đọc**, không phải “đóng băng trạng thái DB ở một mốc”. Để bảo đảm point-in-time trên replica set bằng Database Tools, cần `--oplog` (với điều kiện).

### 6.3. `--readConcern majority` có đủ không?

Không. `readConcern:"majority"` bảo vệ tính chất visibility/durability của các dữ liệu đọc được theo semantics operation, nhưng **không** làm toàn bộ các cursors và collections của một dump thường trở thành cùng một snapshot timestamp.

Đừng biến hai khái niệm:

~~~text
Read only majority-committed data

                ≠

Read all collections at one identical timestamp
~~~

thành một yêu cầu duy nhất. Khi cần snapshot consistent, hãy dùng backup method hỗ trợ chính xác.

## 7. `mongodump --oplog`: online logical backup **một replica set**

Đối với **replica set**, MongoDB Database Tools cho phép `mongodump --oplog` ghi lại những oplog entries xảy ra **trong quá trình dump**. Khi restore bằng `mongorestore --oplogReplay`, tập dữ liệu có thể được tái tạo ở **một thời điểm logic duy nhất** dù application vẫn tiếp tục ghi trong lúc backup.

### 7.1. Quy trình khái niệm

~~~text
Replica set writes continue:

       t0           t1       t2       t3
       |            |        |        |
       +-----------------------------> time

mongodump:
       [----- read BSON collections -----]
       [----- capture oplog entries -----]

Archive:
       BSON collection dumps
       metadata/options/index definitions
       oplog.bson (hoặc embedded oplog trong archive)

mongorestore:
       Restore BSON collections
       Replay oplog entries in valid order
                   |
                   v
       Consistent recovery state
~~~

Không nên đọc sơ đồ rồi kết luận backup đủ để khôi phục **tới bất kỳ thời điểm nào sau dump**. `mongodump --oplog` bắt sự thay đổi **trong cửa sổ dump**, khác **continuous oplog archival** của PITR managed solutions.

### 7.2. Tạo full backup bằng `--oplog`

Trong **terminal** (không phải `mongosh`), chỉ trên replica set lab:

~~~bash
mongodump \
  --uri="mongodb://backupuser@rs-lab:27017/?replicaSet=rsLab" \
  --archive="./rsLab-2026-11-14.archive" \
  --oplog
~~~

Có thể dùng dạng thư mục:

~~~bash
mongodump \
  --uri="mongodb://backupuser@rs-lab:27017/?replicaSet=rsLab" \
  --out="./rsLab-2026-11-14" \
  --oplog
~~~

Ở dạng thư mục, oplog được ghi thành `oplog.bson` tại **đỉnh thư mục dump**; ở dạng archive, các entries được đóng trong archive. `--archive` và `--out` **không dùng cùng lúc**.

### 7.3. Phải là **full dump**

Theo MongoDB Database Tools docs, `mongodump --oplog` yêu cầu **full dump của một replica set member**. Không kết hợp các lựa chọn thu hẹp dữ liệu sau:

~~~bash
# Các tổ hợp sau KHÔNG hợp lệ với --oplog:
mongodump --oplog --db app
mongodump --oplog --collection accounts
mongodump --oplog --query='{"status":"ACTIVE"}'
mongodump --oplog --dumpDbUsersAndRoles
~~~

Đây là **ví dụ không hợp lệ, không phải thao tác nên chạy**. Tại sao? Vì oplog ghi operations của nhiều namespaces, còn dump chỉ một phần sẽ không cung cấp tập gốc đầy đủ để replay nhất quán theo cách tool thiết kế.

### 7.4. DDL và thay đổi metadata có thể làm dump thất bại

MongoDB Database Tools ghi rõ một số operations trong lúc `--oplog` chạy sẽ làm dump **thất bại**, ví dụ:

- `renameCollection` hoặc `db.collection.renameCollection()`.
- Pipeline `$out` làm thay collection.
- Các schema transformation/rename tương tự.
- Thay đổi users, roles, privileges.
- Thay đổi cluster-wide settings như `setDefaultRWConcern`.

Vì vậy “online backup cho phép writes tiếp diễn” **không có nghĩa mọi loại DDL/quản trị đều được thực hiện đồng thời**. Một kế hoạch backup production vẫn nên có **backup window hạn chế DDL**, cảnh báo migrations và giám sát exit code/backup artifact.

### 7.5. Backup từ secondary

Trong replica set có backup-dedicated secondary:

~~~text
Primary (serves writes)
   |
   +----> Secondary A (serves reads)
   |
   +----> Secondary B (backup dedicated)
                    |
                    +-- mongodump --oplog
~~~

Ưu điểm là giảm áp lực quét BSON trên primary. Nhưng:

- Secondary có thể **lag**; recovery timestamp tương ứng với data/oplog state của nguồn, không mặc định tới giờ primary mới nhất.
- Phải monitor replication delay, disk I/O, available oplog window và node health.
- Chọn node backup theo `readPreference`/topology để không vô tình đánh tải trên primary.
- Không giả định secondary backup “rảnh” nếu nó đang giữ shard replication/change streams/reads quan trọng.
- Nếu có election/rollback/source disconnect, backup có thể fail và cần làm lại thay vì coi archive đã hoàn chỉnh.

### 7.6. Dùng oplog không có nghĩa là zero-RPO

Backup hoàn tất lúc 10:10 và khôi phục với `--oplogReplay` sẽ không tự chứa write 10:11, 10:12, ... nếu không có các oplog segments được lưu liên tục sau đó. Với **RPO vài phút hoặc dưới phút**, phải đánh giá managed continuous backup/PITR hoặc quy trình archival/redo logs được thiết kế đầy đủ.

### 7.7. Cửa sổ oplog phải đủ

Ví dụ dump mất 3 giờ, oplog window trong giờ peak chỉ còn 45 phút. Có nguy cơ các entries cần thiết đã bị rotate/truncate trước khi tool/backup agent theo kịp. Kế hoạch:

1. Đo backup duration p95/p99 và throughput đỉnh.
2. Đo oplog window nhỏ nhất tại giờ peak.
3. Đặt margin cho spikes, network downtime và retry.
4. Theo dõi alerts khi oplog window tiến gần backup duration/lag.
5. Nếu history gap hoặc backup tool báo fail, **không đánh dấu bản dump là healthy**.

MongoDB Manual mô tả `oplogMinRetentionHours` và `replSetResizeOplog`, nhưng **tăng retention/size có tác động storage/replication**; cần capacity planning, không tự đổi ngay trên production.

### 7.8. Dấu mốc FCV/time-series theo Tools version

Với MongoDB mới hơn, có ngoại lệ quan trọng: Database Tools cảnh báo **không thay FCV giữa MongoDB 8.x và 9.0 trong lúc `mongodump --oplog` chạy trên deployment có time-series collections**, vì oplog có thể bắc qua **time-series format conversion** mà `mongorestore --oplogReplay` không thể replay trực tiếp qua một FCV state.

Từ **Database Tools 100.18.0**, `mongodump` có thể chủ động fail thay vì tạo dump không phục hồi được trong trường hợp này. Vì vậy, backup window nên **tránh FCV/major-version format transitions** và cần test restore tương thích. Xem phần version notes ở cuối.

## 8. `mongorestore --oplogReplay`: khôi phục đủ cả data lẫn writes trong cửa sổ dump

Một backup `mongodump --oplog` **chỉ phát huy guarantee khi restore đúng quy trình**. Nếu restore các BSON files mà bỏ qua oplog, bạn có thể trở lại trạng thái không nhất quán do các collections được quét vào những thời điểm khác nhau.

### 8.1. Restore vào môi trường **tách biệt và trống**

Trong terminal của một môi trường DR/test có phiên bản tương thích:

~~~bash
# Phục hồi bản archive của replica set lab vào target tách biệt.
# Không trỏ RESTORE_URI về cụm production đang phục vụ người dùng.
mongorestore \
  --uri="mongodb://restoreuser@restore-lab:27017/" \
  --archive="./rsLab-2026-11-14.archive" \
  --oplogReplay
~~~

Hoặc với directory dump:

~~~bash
mongorestore \
  --uri="mongodb://restoreuser@restore-lab:27017/" \
  --dir="./rsLab-2026-11-14" \
  --oplogReplay
~~~

`--oplogReplay` replay các oplog entries từ `oplog.bson` (trong directory) hoặc phần oplog của archive sau khi restore BSON data. Đích nên **rỗng hoặc được thiết kế riêng cho replay**; restore chồng lên DB đang ghi có thể xung đột dữ liệu và tạo trạng thái không dự đoán được.

### 8.2. Không chỉ chọn một namespace khi replay full oplog

Với một full replica-set dump và `--oplogReplay`, MongoDB Database Tools **không cho phép** thu hẹp restore bằng:

~~~bash
# KHÔNG hợp lệ trong ngữ cảnh full oplog replay:
mongorestore --oplogReplay --db app
mongorestore --oplogReplay --collection orders
mongorestore --oplogReplay --nsInclude "app.orders"
mongorestore --oplogReplay --nsExclude "app.logs"
mongorestore --oplogReplay --nsFrom "app.*" --nsTo "demo.*"
~~~

Những flags này gây lỗi/không tương thích vì replay logic kỳ vọng tập dữ liệu đầy đủ. Nếu mục tiêu là **restore một collection** từ backup lớn, phải dùng một quy trình **selective restore khác**, chấp nhận và thiết kế riêng các ràng buộc consistency, dependencies, indexes và cross-collection relationships.

### 8.3. `--oplogLimit` không phải “chọn giờ bằng mắt”

Database Tools có tùy chọn `--oplogLimit=<seconds>:<ordinal>` để giới hạn những entries được replay khi sử dụng `--oplogReplay`. Dùng sai timestamp có thể dẫn tới **inconsistency**; tài liệu chính thức có cảnh báo rõ khi tự chọn oplog ranges.

**Không** suy rằng chỉ cần trích một timestamp trong log rồi gắn `--oplogLimit` là sẽ tạo một arbitrary point-in-time restore hoàn toàn nhất quán; các transactions, metadata changes và phạm vi capture phải được xét. Đối với recovery theo phút/giây, ưu tiên **managed PITR** có cơ chế kiểm soát restore point.

### 8.4. Vấn đề write mới trên restore target

Nếu application đã kết nối target và đang insert trong lúc `mongorestore` chạy:

- Có thể tạo documents trùng, lỗi unique index hoặc partial restore.
- Oplog replay có thể không tương ứng với dataset target hiện tại.
- Một số index/migration có thể cản trở restore.
- Dữ liệu đích có thể còn từ restore thất bại trước đó.

Vì vậy, **cách ly restore target**, dừng writes/application traffic tới target, restore xong mới validate, rồi thực hiện cutover có điều phối.

### 8.5. Nếu restore thất bại giữa chừng

Đừng chạy lại cùng lệnh vô điều kiện trên target đã **partially restored**. MongoDB Database Tools cảnh báo khi `mongorestore` crash có thể để dữ liệu dở dang, không nhất quán. Runbook an toàn:

1. Xác nhận tool exit code, logs và giai đoạn thất bại.
2. **Giữ backup gốc bất biến** để bảo toàn chứng cứ.
3. Xóa/recreate **target DR đã được phê duyệt** hoặc reset môi trường theo phương án an toàn.
4. Restore lại từ đầu.
5. Test counts, indexes và business invariants trước khi công bố.

**Không** dùng `--drop` một cách tự động trên một cluster không được xác minh là môi trường DR; `mongorestore --drop` có thể xóa collections đang tồn tại.

### 8.6. Phục hồi có thể mất nhiều thời gian hơn tạo backup

Logical dump chứa documents và **index definitions**, nhưng không nhất thiết có sẵn index data structures giống physical snapshot. Khi restore, indexes có thể phải được **rebuild**, ảnh hưởng RTO. Tổng:

~~~text
RTO thực tế =
  chuẩn bị target
  + lấy/copy backup qua mạng
  + load BSON data
  + replay oplog
  + build indexes
  + validation/business checks
  + app cutover / cache warming
~~~

Backup job hoàn thành trong 20 phút không bảo đảm dịch vụ có thể phục hồi trong 20 phút.

## 9. Filesystem snapshot: nhất quán ở mức node và storage

**Filesystem snapshot** lưu trạng thái **toàn volume** ở một thời điểm gần như tức thì theo semantics của hệ thống lưu trữ. Với MongoDB/WiredTiger, điều kiện mấu chốt là snapshot phải bao gồm **đúng tập data files và journal files** và có tính atomic phù hợp.

### 9.1. Một volume có thể chụp đồng bộ

~~~text
Linux block device / logical volume V:

  /var/lib/mongodb/
    WiredTiger
    WiredTiger.wt
    collection-*.wt
    index-*.wt
    journal/
    ...

            |
   Atomic volume snapshot
            |
            v
      Snapshot image
            |
      Copy to offsite store
~~~

Nếu tất cả thành phần cần thiết nằm trên một volume và snapshot có atomicity đúng, backup có thể phản ánh một trạng thái **crash-consistent của node**. Khi khởi động target, MongoDB recovery dựa vào checkpoint/journal để đưa dữ liệu về trạng thái hợp lệ.

Tuy nhiên, **không** suy rằng mọi cloud disk snapshot, mọi RAID array, mọi container volume driver đều có atomic snapshot trên toàn tập dữ liệu. Phải xác minh cụ thể storage platform và tuân thủ MongoDB backup tutorial.

### 9.2. Data/journal nằm ở các volumes khác nhau

Trường hợp:

~~~text
Volume A:
  collection/index WiredTiger files

Volume B:
  journal files

Snapshot A at 10:00:00
Snapshot B at 10:00:20
~~~

Nếu writes tiếp diễn trong 20 giây giữa hai snapshots, bạn có thể ghép data files và journal từ **hai trạng thái không khớp**. MongoDB Manual yêu cầu **khóa và tạm dừng writes** đối với thủ tục filesystem backup khi WiredTiger data/journal trên những volumes tách biệt.

Không chỉ là “tất cả volumes được chụp trong cùng một phút” — cần cơ chế **atomic multi-volume group snapshot** được xác minh, hoặc khóa ghi/flush theo tài liệu.

### 9.3. Quy trình `db.fsyncLock()` khi được chỉ định

Trên một node lab hoặc backup-dedicated secondary theo hướng dẫn:

~~~javascript
// MẪU QUẢN TRỊ - KHÔNG CHẠY TRÊN PRIMARY PRODUCTION TÙY TIỆN.
db.fsyncLock()
~~~

Sau đó operator tạo snapshot/copy theo runbook, và **bắt buộc unlock**:

~~~javascript
db.fsyncUnlock()
~~~

**Ảnh hưởng:** `fsyncLock` có thể chặn writes và ảnh hưởng replication/app availability tùy node; nếu dùng primary sẽ tác động trực tiếp production. Không coi nó là cách đạt online backup với **writes vẫn chạy bình thường**.

### 9.4. Luôn có bước unlock/recovery khi lỗi

Runbook phải xử lý:

- Process tạo snapshot timeout.
- Operator session bị ngắt giữa `fsyncLock` và `fsyncUnlock`.
- Snapshot service trả lỗi nhưng node còn bị khóa.
- Secondary không theo kịp oplog khi bị chặn apply quá lâu.

**Giữ checklist và alarm** về thời gian locked; không tự để node bị khóa hàng giờ. Nếu dùng automation, phải có `finally`/failure handling và kiểm tra tình trạng khóa bằng command/version phù hợp.

### 9.5. Vì sao `rsync` sống không tương đương snapshot?

~~~bash
# KHÔNG dùng như bảo đảm consistent backup khi MongoDB vẫn ghi:
rsync -a /var/lib/mongodb/ backup-host:/backup/mongo/
~~~

Copy file `collection-1.wt` lúc 10:00:01, `index-1.wt` lúc 10:00:30 và journal lúc 10:01:00 có thể tạo bộ files không cùng thời điểm. Một lượt rsync thành công ở mức file/SSH **không** chứng minh crash-consistent database.

### 9.6. Storage snapshot không phải offsite backup

Một snapshot copy-on-write trên **cùng storage pool** có thể mất cùng với disk array/site. Sau khi tạo ảnh, cần chuyển sang **offsite/immutable storage**, kiểm tra checksum, encryption và retention. Snapshot nhanh hỗ trợ RTO, nhưng không thay chính sách bảo vệ khỏi ransomware, thao tác xóa nhầm snapshot, site failure và quyền admin bị chiếm.

### 9.7. Nên snapshot primary hay secondary?

Thông thường nên cân nhắc **secondary riêng cho backup** để giảm tải primary. Nhưng:

- Backup secondary phải healthy, không bị quá lag.
- Oplog window đủ để node quay lại replication sau snapshot/lock.
- Read traffic/hidden member topology phải theo thiết kế.
- Khi restore từ snapshot secondary, recovery point có thể **stale** so với primary.
- Nếu node được snapshot đang trải qua election/rollback, cần xem runbook về tính ổn định trước khi công bố backup.

Không chụp primary chỉ vì nó “mới nhất”, nếu cost/pause writes vi phạm SLA. Nhưng cũng không coi mọi secondary là consistent global point của cả cluster.

## 10. Sharded cluster: vì sao mỗi shard consistent vẫn chưa đủ?

Một sharded MongoDB cluster gồm nhiều **shard replica sets**, `mongos` routers và **config server replica set** chứa metadata về shards, collections và ranges/chunks. Transaction có thể ghi vào nhiều shards. Khi backup, phải bảo vệ tính nhất quán **toàn cluster**, chứ không chỉ từng shard riêng.

### 10.1. Ví dụ transaction xuyên shard

~~~text
                mongos
                  |
      +-----------+-----------+
      |                       |
      v                       v
   Shard A                  Shard B
 account A                account B

Transaction T:
  A.balance -= 200
  B.balance += 200

Backup Shard A at 10:00:10
Backup Shard B at 10:00:30
~~~

Nếu T commit lúc 10:00:20, backup A có thể phản ánh dữ liệu **trước T**, còn backup B phản ánh dữ liệu **sau T**. Mỗi shard snapshot riêng có thể hợp lệ, nhưng **khi khôi phục ghép lại, transaction T bị chia đôi**.

Đây là ví dụ của **cross-shard consistency problem**. Không sửa bằng việc “đồng bộ đồng hồ NTP” đơn giản: cần **phương pháp backup có phối hợp timestamp/recovery point và transaction boundaries**, hoặc tạm dừng writes theo runbook.

### 10.2. Metadata config server có thể lệch dữ liệu shards

Config server chứa thông tin **chunk/range ownership**. Nếu trong lúc backup balancer di chuyển range R:

~~~text
10:00  Config: range R thuộc Shard A
10:01  Balancer migrate R từ A -> B
10:02  Backup Shard A
10:03  Backup config metadata
10:04  Backup Shard B
~~~

Khi ghép dữ liệu/metadata ở nhiều thời điểm, restore có thể bị **missing data, duplicates hoặc metadata ownership mismatch**. Vì thế tài liệu MongoDB yêu cầu **dừng balancer** trong thủ tục backup sharded cluster thủ công và xác nhận migrations đã ngừng.

### 10.3. Vì sao `mongodump --oplog` trên `mongos` không giải quyết?

MongoDB Database Tools nêu rõ:

- `--oplog` làm việc trên các nodes có **oplog** như replica set members.
- Chạy `mongodump --oplog` qua `mongos` để dump toàn sharded cluster **không có tác dụng bảo đảm global snapshot**.
- Không thể sử dụng `mongodump --oplog` như một phương pháp online backup toàn sharded cluster theo đúng những semantics của replica set.
- `mongorestore --oplogReplay` **không được hỗ trợ đối với sharded clusters** trong mô hình đó.

**Do not:** dump từng shard với `--oplog`, chọn “oplog mới nhất” của mỗi shard rồi ghép tùy tiện và tuyên bố recover được cross-shard transactions. Oplogs riêng không tự tạo ra một global cut.

### 10.4. Manual sharded cluster backup phải dừng điều gì?

Theo các tutorials chính thức của MongoDB về self-managed sharded cluster:

1. **Dừng balancer**, chờ migrations đang chạy hoàn tất.
2. **Dừng writes** vào cluster và các hoạt động schema transformation/resharding liên quan.
3. Thực hiện **`fsync`/`db.fsyncLock()`** và snapshot/dump từng thành phần theo runbook/phiên bản được hỗ trợ.
4. Sao lưu **config server metadata** và mỗi shard theo đúng thứ tự/quy trình.
5. Xác minh các artifacts và metadata, rồi **unlock/restart balancer/writers** có kiểm soát.

Với cách làm thủ công, tài liệu cảnh báo độ nhất quán vẫn phụ thuộc điều kiện cluster không có operations đang dở dang và việc tuân thủ chính xác quy trình. **Đừng diễn giải “dừng balancer” là đủ**: nếu writes vẫn tiếp diễn, cross-shard inconsistency vẫn có thể xảy ra.

### 10.5. Ví dụ các lệnh **quản trị nhạy cảm**, không phải script copy-paste production

Trên `mongos` của một **sharded lab** được phép:

~~~javascript
// DỪNG BALANCER: làm thay đổi hoạt động cluster.
sh.stopBalancer()

// Kiểm tra trạng thái, và cần xác nhận migrations đã thực sự dừng.
sh.getBalancerState()
~~~

Trên môi trường/trình tự hỗ trợ, tài liệu backup bằng database dump còn mô tả khóa cluster từ `mongos`:

~~~javascript
// CHỈ MINH HỌA: cần tuân thủ đầy đủ procedure/permissions.
db.getSiblingDB("admin").fsyncLock()

// Tạo backup ở bước tiếp theo theo tutorial chính thức.

// Cuối cùng phải unlock theo đúng procedure:
db.getSiblingDB("admin").fsyncUnlock()
~~~

**Không chạy các câu lệnh này** trên production chỉ vì đang đọc bài; chúng có thể tác động trực tiếp write availability và cluster balancing. Với MongoDB versions khác nhau, cách lock/state verification/commands có thể khác; phải theo **tutorial đúng bản server**, không tự bỏ những bước chuẩn bị.

### 10.6. Tại sao backup config server quan trọng?

Không chỉ cần business collections:

~~~text
Sharded-cluster backup set:

  config server replica set
    - collection/shard metadata
    - chunk/range ownership
    - configuration state

  shard A replica set
    - data/index definitions

  shard B replica set
    - data/index definitions

  shard C replica set
    - data/index definitions
~~~

Khôi phục dữ liệu shards mà thiếu/không khớp config metadata có thể khiến `mongos` không biết đúng location của ranges. Một **cluster restore** khác với import documents vào một collection mới; đừng cố phục hồi topology bằng cách chèn thủ công documents vào `config.*`.

### 10.7. Tương thích topology khi restore

Các managed systems và restore tools có điều kiện về:

- Số shards, kiểu config servers (dedicated/config-shard).
- Server version và FCV.
- Auth/users/roles/encryption/key management.
- Logical/physical backup format.
- Snapshot age và tương thích khi đã add/remove shards.

Ví dụ **Atlas Cloud Backup** có quy định **source/target sharded clusters phải có số shards tương thích** và kiểu config server tương ứng; có trường hợp không thể restore snapshot cũ vào topology đã thay đổi. Phải kiểm tra chính xác tutorial và lên kế hoạch **restore vào cluster mới với topology phù hợp**.

### 10.8. Cách được khuyến nghị khi cần online backup thật sự

Nếu business không cho dừng writes trên sharded cluster, cách đơn giản hơn về trách nhiệm vận hành là dùng:

- **Atlas managed cluster-wide backups**.
- **Atlas Continuous Cloud Backup (PITR)** khi cần recovery timestamp gần sự cố.
- **MongoDB Ops Manager / Cloud Manager** với coordinated backup/restore theo điều kiện sản phẩm.

Các dịch vụ này được thiết kế để **phối hợp shards, transactions và metadata**; không nên thay thế chúng bằng một cron job chạy nhiều `mongodump --oplog` song song mà không có thuật toán global cut được xác nhận.

## 11. Atlas Cloud Backup: backup quản lý cho cluster đang hoạt động

**MongoDB Atlas Cloud Backup** cung cấp snapshots theo chính sách và, khi tính năng **Continuous Cloud Backup** được bật trên deployment hỗ trợ, khả năng **point-in-time restore** trong một cửa sổ được cấu hình.

### 11.1. Consistent snapshot của managed service

Tài liệu MongoDB Atlas Architecture Center mô tả **cluster-wide consistent snapshots cho cả sharded clusters**. Atlas điều phối thời gian giữa shards để bảo đảm snapshot tương ứng với mốc cluster được chọn.

Điều này khắc phục hạn chế của việc operator tự chụp từng shard tại những thời điểm khác nhau. Nhưng không suy rằng mọi thao tác DDL, tất cả backup tiers hoặc mỗi tính năng PITR đều được hỗ trợ như nhau — cần kiểm tra **cluster tier, cloud provider, region, version, backup policy và restore target**.

### 11.2. Snapshot có thể được tạo khi ứng dụng vẫn ghi

~~~text
Applications continuously write
          |
          v
      Atlas cluster
     /     |      \
  Shard A Shard B Shard C
     \     |      /
      coordinated snapshot
              |
              v
     Backup storage + retention policy
~~~

**Managed backup** giúp tránh tự xây lock/stop balancer workflow trong nhiều trường hợp. Tuy nhiên, backup job vẫn tiêu thụ storage/compute/network và có thể có constraints riêng với phiên bản/tính năng.

### 11.3. PITR: snapshot cộng captured changes

~~~text
09:00     Snapshot S0
  |
  +-- 09:05 changes captured
  +-- 09:10 changes captured
  +-- 09:15 changes captured
  +-- 09:17 accidental deletion
  |
  v
09:18     Incident detected

Recovery objective:
  Restore to 09:16:59 (just before deletion),
  if that point is inside permitted PITR window.
~~~

**Đúng thời điểm** phải xác định theo hỗ trợ của sản phẩm và thời gian thực tế của operation/commit. Có thể muốn restore **ngay trước** một lệnh xóa sai, nhưng chỉ chọn thời gian trên đồng hồ không đảm bảo lệnh đó hoàn toàn chưa áp dụng nếu clock và cluster timestamp không khớp như bạn nghĩ; cần tham khảo oplog timestamps/audit logs khi khả dụng.

### 11.4. Snapshot schedule không phải continuous backup

Nếu policy chỉ giữ snapshots hàng giờ:

~~~text
09:00 snapshot
10:00 snapshot
10:49 fail
~~~

Chỉ có snapshots (không PITR) thì recovery có thể phải trở lại 10:00, mất gần 49 phút writes. Continuous backup lưu thêm changes để hỗ trợ chọn restore point trong window. Đừng đánh đồng “có backup hằng giờ” với RPO một phút.

### 11.5. Backup retention và restore window

Các thông số khác nhau:

| Tham số | Ý nghĩa |
|---|---|
| Snapshot frequency | Bao lâu tạo bản snapshot mới. |
| Snapshot retention | Giữ snapshot trong bao lâu. |
| Continuous/PITR window | Khoảng lịch sử có đủ log để restore theo thời gian. |
| Backup compliance policy | Bản nào bắt buộc giữ, có immutability/quy định pháp lý. |
| Restore target constraints | Số shards/region/tier/version/phân vùng dữ liệu tương thích. |
| RPO | Mức mất dữ liệu chấp nhận theo business. |
| RTO | Tổng thời gian khôi phục khả dụng sau sự cố. |

Nếu PITR window chỉ 24 giờ mà phát hiện dữ liệu sai sau 3 ngày, **không thể** tự động restore tới điểm ngay trước lỗi bằng PITR window đó, dù một snapshot cũ có thể còn theo retention policy.

### 11.6. Cảnh báo fallback snapshots

Tài liệu Atlas có đề cập **fallback snapshots** trong một số tình huống restore, kèm cảnh báo chúng **có thể chứa dữ liệu không nhất quán** và chỉ nên xem là lựa chọn cuối cùng. Không vì thấy snapshot có trong UI mà bỏ qua warning về consistency. Khi đánh giá DR, hãy ưu tiên snapshot được hệ thống xác nhận có guarantee mong muốn và test application invariants.

### 11.7. Restore vào cluster mới là cách giảm rủi ro

Trong nhiều tình huống, restore sang **cluster mới/tách biệt**, kiểm tra dữ liệu, rồi chuyển traffic là lựa chọn an toàn hơn restore đè cụm đang phục vụ. Atlas docs lưu ý cluster-level restore có thể **xóa dữ liệu hiện có trên target** và khiến target unavailable trong quá trình restore. Runbook cần phân biệt:

- **In-place cluster restore**: downtime/có thể mất dữ liệu target đã có.
- **Restore to new cluster**: cần chuẩn bị topology/cost/connection strings/migration, nhưng cho phép validate trước cutover.

### 11.8. Search indexes, secrets và external services

Atlas restore có thể khôi phục **search index definitions** nhưng không có sẵn tất cả index data; Search/mongot có thể phải **build lại**, làm kéo dài thời gian sẵn sàng của tính năng search dù collections đã restore xong. Ngoài ra:

- Secrets/KMS keys và access policies có thể nằm ngoài backup data.
- Các integration như Kafka, S3, payment systems, Redis caches không nhất thiết cùng restore point.
- Replication/backup management logs phải được lưu phục vụ audit và recovery decision.

**Cluster consistent snapshot chỉ là một phần của DR plan toàn hệ thống.**

## 12. Transaction và backup consistency: ví dụ nghiệp vụ đầy đủ

Giả sử hệ thống ví điện tử có `wallets` và `transfers` trong **cùng replica set**. Chuyển tiền cần:

1. Kiểm tra ví A đủ tiền.
2. Giảm A và tăng B.
3. Tạo record `transfers` có trạng thái COMMITTED.
4. Tất cả thay đổi commit hoặc rollback cùng nhau.

### 12.1. Transaction chuẩn ở tầng ứng dụng

Ví dụ `mongosh` trên replica set lab:

~~~javascript
const session = db.getMongo().startSession()
const sdb = session.getDatabase("backup342_lab")

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  const debit = sdb.wallets.updateOne(
    { _id: "A", balanceMinor: { $gte: 20000 } },
    { $inc: { balanceMinor: -20000 } }
  )
  if (debit.matchedCount !== 1) {
    throw new Error("insufficient funds or missing source wallet")
  }

  const credit = sdb.wallets.updateOne(
    { _id: "B" },
    { $inc: { balanceMinor: 20000 } }
  )
  if (credit.matchedCount !== 1) {
    throw new Error("missing destination wallet")
  }

  sdb.transfers.insertOne({
    _id: "TX-20261114-001",
    from: "A",
    to: "B",
    amountMinor: 20000,
    state: "COMMITTED",
    createdAt: new Date()
  })
  session.commitTransaction()
} catch (err) {
  try { session.abortTransaction() } catch (_) {}
  throw err
} finally {
  session.endSession()
}
~~~

**Lưu ý:** Code minh họa tính atomic; production cần transaction retry policy, commit ambiguity handling, stable idempotency key và tránh duplicate transfer. Việc cùng transaction giúp tránh ghi nửa nghiệp vụ trong **live database**, nhưng backup vẫn phải có recovery point đúng.

### 12.2. Nếu backup cắt ngang commit?

~~~text
Timeline transaction T:

  t0: T bắt đầu, cập nhật A/B và tạo TX
  t1: T commit thành công

Backup recovery point P:

  P < t1:
     A/B và transfer record ở trạng thái trước T

  P >= t1:
     A/B và transfer record ở trạng thái sau T
~~~

Một backup consistent phải tôn trọng **transaction atomicity tại recovery point**. Các câu đọc tự do của `mongodump` thường không tự bảo đảm quy tắc đó; `--oplog` trên replica set hoặc managed backup/PITR được thiết kế để bảo vệ nó theo điều kiện.

### 12.3. Ví dụ invariant sau restore

~~~javascript
// Chạy trên database DR đã restore, không trỏ vào production.
const rdb = db.getSiblingDB("backup342_lab")
const walletA = rdb.wallets.findOne({ _id: "A" })
const walletB = rdb.wallets.findOne({ _id: "B" })

if (walletA == null || walletB == null) {
  throw new Error("wallet missing after restore")
}

const total = walletA.balanceMinor + walletB.balanceMinor
printjson({
  totalMinor: total,
  transfers: rdb.transfers.countDocuments({ state: "COMMITTED" })
})
~~~

Nếu ban đầu tổng số dư hai ví 200.000 đồng và không có nạp/rút, tổng vẫn phải 200.000 sau mọi chuyển khoản nội bộ. Nhưng **tổng đúng chưa đủ**: vẫn cần kiểm tra từng ledger entry/transfer ID, thời gian và đối chiếu hệ thống thanh toán.

### 12.4. Snapshot vẫn có thể chụp một trạng thái business trung gian

Nếu ứng dụng thực hiện **hai writes không cùng transaction**:

~~~text
update A.balance
      |
      +---- backup point P
      |
update B.balance
~~~

thì ngay cả một **database snapshot đúng tại P** vẫn có thể chứa trạng thái A đã trừ, B chưa cộng. Backup không thay thế transaction/outbox/business atomicity của ứng dụng.

**Database-consistent** nghĩa là phản ánh đúng trạng thái MongoDB lúc P; **business-consistent** còn đòi hỏi ứng dụng không tạo các trạng thái vi phạm invariant (hoặc có recovery workflow được định nghĩa).

## 13. Read concern và write concern: ảnh hưởng thật đến backup

### 13.1. `w:1` so với `w:"majority"`

~~~javascript
// Có thể được ack bởi primary trước khi đủ majority:
db.events.insertOne(
  { eventId: "E-1001", value: 42 },
  { writeConcern: { w: 1 } }
)

// Yêu cầu majority acknowledgement:
db.events.insertOne(
  { eventId: "E-1002", value: 43 },
  { writeConcern: { w: "majority" } }
)
~~~

`w:"majority"` giảm nguy cơ acknowledged write bị rollback sau election. Nhưng backup ở recovery point trước E-1002 vẫn không chứa E-1002 dù nó đã majority-acknowledged ngay sau đó. Đây là **RPO/recovery point**, không phải lỗi của majority.

### 13.2. `readConcern:"local"`

Reader có thể thấy dữ liệu mới nhất cục bộ trên node, gồm một số writes chưa majority-committed và còn có khả năng rollback. Không coi `local` là bảo đảm “mới nhất và an toàn nhất”; cần xét source node, stable timestamps và backup methodology.

### 13.3. `readConcern:"majority"`

`majority` bảo đảm điều kiện visibility của từng operation theo semantics server, **không đóng băng** toàn bộ database qua hàng nghìn cursor batches:

~~~text
10:00:00  Read accounts with majority
10:00:05  Commit transaction T with majority
10:00:10  Read transfers with majority
~~~

Hai reads đều majority nhưng thấy **hai thời điểm khác nhau**. “Dump đọc majority” không thể thay `--oplog` hoặc managed snapshot guarantee.

### 13.4. `readConcern:"snapshot"`

Trong operations/transactions hỗ trợ, `snapshot` cho phép đọc dữ liệu ở **một snapshot timestamp**. Nhưng:

- Read-only transaction rất dài để quét toàn database có thể tăng áp lực snapshot history/cache và chạm transaction lifetime limits.
- Sharded cluster cần phối hợp timestamp across shards.
- Snapshot read không tự lưu data/journal hay capture oplog liên tục.
- `mongodump` không biến thành cluster-wide consistent backup chỉ vì một application dùng read concern snapshot ở chỗ khác.

**Dùng công cụ backup được hỗ trợ và xác nhận rõ guarantee**, không tự thay bằng read transaction quét khổng lồ.

### 13.5. Causal consistency có giúp không?

Causally consistent session bảo vệ thứ tự quan hệ nhân quả cho reads/writes theo điều kiện, **không** tự tạo global point-in-time cut cho tất cả collections và shards khi backup tool chạy độc lập.

Không đồng nhất causal consistency với snapshot consistency, và không nghĩ session của API người dùng điều phối được process `mongodump` ở máy khác.

## 14. Các loại thay đổi khác trong cửa sổ backup

Không chỉ `insertOne()` và `updateMany()` mới ảnh hưởng tính nhất quán. DDL, background jobs, TTL và cluster management có thể làm backup không đại diện một trạng thái hợp lệ.

### 14.1. Rename/DDL

~~~javascript
// MINH HỌA DDL, không chạy trong backup window.
db.orders.renameCollection("orders_v2")
~~~

Nếu `mongodump` đã quét một phần `orders` khi rename xảy ra và tiếp tục sang `orders_v2` sau đó, output có thể lỗi namespace hoặc không trọn vẹn. `mongodump --oplog` có danh sách operations làm fail, như `renameCollection`, aggregation `$out` và những thay đổi users/roles/cluster-wide settings.

**Lập backup window tránh deploy migrations/schema transformations**, không chỉ tránh traffic web.

### 14.2. TTL deletes

TTL monitor có thể xóa documents cũ trong lúc backup. Với dump thường, hai lần đọc có thể nhìn thấy trạng thái trước và sau delete; với replica-set `--oplog` hoặc managed recovery point, tool phải tái tạo đúng những deletes tại mốc logic.

Sau restore, TTL có thể **tiếp tục xóa** documents ngay vì chúng đã quá hạn, làm test counts thay đổi. Khi kiểm tra restore, cần biết TTL policy và thời gian thực tế, không mặc định dữ liệu phải đứng yên mãi sau khi mongod khởi động.

### 14.3. Index builds

Index build có thể tăng IOPS và kéo dài backup duration. `mongodump` xuất BSON documents cùng index definitions, còn khi `mongorestore`, indexes có thể phải **rebuild**. Vì vậy:

- Backup nhanh không có nghĩa restore nhanh.
- Cần dung lượng trống cho rebuild.
- Sau restore phải kiểm tra index ready/queries, không chỉ collection counts.
- Không chạy index migration lớn cùng backup nếu chưa đánh giá ảnh hưởng.

### 14.4. Compaction và storage transformations

Compaction hoặc thay đổi file layout có thể tác động physical snapshots/file-copy. Dùng backup/storage API được hỗ trợ, không quét `.wt` bằng script tự chế khi engine vẫn thay đổi cấu trúc.

### 14.5. Chunk migration/resharding

Trên sharded cluster:

- Balancer di chuyển chunks/ranges.
- Resharding clone dữ liệu và đổi metadata ownership.
- Schema/FCV transformations có thể thay layout.
- Cross-shard transactions có commit protocol riêng.

Manual backup không phối hợp có thể **bỏ sót/đúp ranges** hoặc làm metadata không khớp dữ liệu. Dừng **balancer, writes và schema transformations** theo tutorial, hoặc dùng managed coordinated backup.

### 14.6. Atlas Search/Vector indexes

Phục hồi BSON documents không đảm bảo Search/Vector index segments sẵn sàng ngay tại cùng thời điểm. Index definitions có thể được restore, còn search index data cần **initial sync/rebuild**. DR readiness phải bao gồm search endpoints, không chỉ `findOne()` trên collection.

### 14.7. Major version, FCV và định dạng lưu trữ

Không chạy backup spanning FCV/major-version layout changes khi công cụ docs cảnh báo không hỗ trợ. Ví dụ MongoDB 8.x ↔ 9.0 có **time-series format conversion** có thể làm `mongorestore --oplogReplay` không replay một oplog range bắc qua conversion. Database Tools 100.18.0+ có hành vi fail sớm trong trường hợp tương ứng.

Nếu DR runbook cần recovery qua upgrade window, phải lưu **backup được chứng minh restore được ở từng giai đoạn**, không giả định tương thích backward/forward tuyệt đối.

## 15. Dữ liệu ngoài MongoDB: consistent DB chưa chắc consistent system

Một ứng dụng thương mại điện tử thường dùng MongoDB cùng:

- Kafka/RabbitMQ/SQS cho events.
- Object storage cho ảnh, hóa đơn, bản export.
- Redis cho cache/queues.
- Payment provider và ledger ở service khác.
- Search index, warehouse hoặc analytics projections.

Một bản backup MongoDB có thể hoàn toàn hợp lệ ở 10:00, trong khi Kafka offsets và object storage ở 10:03. Khôi phục MongoDB nhưng không lập kế hoạch cho các hệ thống liên quan có thể gây duplicate events, mất tham chiếu hoặc double processing.

### 15.1. Ví dụ outbox và event đã publish

~~~text
09:59  MongoDB transaction:
         Create order O-10
         Insert outbox event E-10
       Commit.

10:00  MongoDB backup point P.

10:01  Worker sends E-10 to Kafka, marks outbox SENT.

10:05  Incident; restore MongoDB to P.
~~~

Sau restore:

- MongoDB có order O-10 và outbox E-10 **chưa SENT** (trạng thái lúc 10:00).
- Kafka vẫn có event E-10 đã gửi lúc 10:01.
- Worker có thể publish lại E-10.

Đây không nhất thiết là **lỗi bản backup**. Cần idempotent consumers và stable event IDs để xử lý replay. Với quy trình khôi phục toàn hệ thống, phải định nghĩa cutover/queue offsets/deduplication.

### 15.2. Đừng xóa external objects sớm

Nếu MongoDB giữ:

~~~javascript
{
  _id: "INVOICE-100",
  pdfUrl: "s3://billing/invoices/INVOICE-100.pdf"
}
~~~

nhưng object storage đã xóa file tại 10:03, còn DB restore về 10:00, record được hồi phục có thể trỏ tới file không tồn tại. Cần **retention phối hợp** cho object storage (versioning/soft delete/WORM theo policy), không chỉ backup MongoDB documents.

### 15.3. Cache không phải nguồn sự thật

Redis cache có thể chứa giá trị mới hơn restore point. Sau MongoDB restore, nên invalidate/warm cache theo runbook để tránh phục vụ dữ liệu từ “tương lai” so với DB vừa phục hồi.

### 15.4. Multi-region và external consistency

Nếu MongoDB cluster phân vùng theo region, dịch vụ bên ngoài có event logs ở UTC khác local time, hãy dùng **event IDs, logical offsets, cluster timestamps và commit markers** đáng tin, không chỉ so chuỗi ngày giờ trong logs. NTP giúp giảm clock skew nhưng **không thay thế distributed transaction/coordination** giữa các hệ thống.

### 15.5. Thiết kế application recovery protocol

Một quy trình tốt:

1. Chọn **MongoDB recovery point P** được chứng minh consistent.
2. Ghi lại **external offsets/checkpoints** tương ứng hoặc xác định cách replay idempotent.
3. Tạm dừng ingress/consumer writes trong lúc restore/cutover.
4. Restore MongoDB, kiểm tra business invariants.
5. Điều chỉnh queue consumer offsets hoặc dùng replay/deduplication policy.
6. Rebuild caches/search/read models phụ thuộc MongoDB.
7. Cho traffic vào lại theo canary, monitor duplicate/missing events.

**Không quảng cáo “toàn bộ hệ thống được khôi phục atomically”** trừ khi thật sự có cơ chế phối hợp và kiểm chứng cho từng thành phần.

## 16. Bảo mật backup khi hệ thống vẫn ghi

Consistency là trọng tâm, nhưng một bản sao lưu vẫn cần bảo vệ **tính bí mật, toàn vẹn và quyền sử dụng**.

### 16.1. Tài khoản backup chỉ có quyền cần thiết

Không dùng tài khoản application với quyền quản trị toàn cluster chỉ để chạy backup. Với `mongodump`, dùng built-in roles/quyền phù hợp với các collections/metadata; với managed backup, cấp project roles theo nhiệm vụ. Restore account cũng nên tách biệt, chỉ dùng trong môi trường DR được phép.

### 16.2. Mã hóa ở đường truyền và nơi lưu

Trong production:

- Dùng TLS tới MongoDB.
- Mã hóa backup khi lưu và khi truyền tới offsite storage.
- Bảo vệ key bằng KMS/secret manager và kiểm tra khôi phục được key.
- Không để mật khẩu URI trong shell history, log CI, README hoặc repo.
- Đặt retention/immutable storage theo quy định để chống xóa/sửa trái phép.

Ví dụ lệnh bài học dùng hostname/username giả định; **không** đưa secret thật vào ví dụ hoặc log.

### 16.3. Checksum và tính toàn vẹn file

Sau khi copy archive tới storage khác, tạo checksum:

~~~bash
# Ví dụ trên Linux/Unix ở môi trường DR.
sha256sum rsLab-2026-11-14.archive
~~~

So sánh checksum tại nguồn và đích giúp phát hiện **file bị hỏng trên đường copy**. Nhưng checksum pass chỉ xác nhận bytes trùng, **không chứng minh nội dung DB consistent**. Để chứng minh tính nhất quán, phải restore và kiểm tra business invariants.

### 16.4. Restore drill không nên dùng dữ liệu nhạy cảm bừa bãi

Một backup production có thể chứa PII/secrets. DR test phải sử dụng môi trường có security controls tương đương, giới hạn người được truy cập, cân nhắc anonymization khi cần và bảo vệ log artifacts. Không tải backup khách hàng xuống laptop cá nhân chỉ để thử.

### 16.5. Malware/ransomware và backup independence

Nếu backup nằm trên cùng account/storage với production và có thể bị xóa bởi cùng credentials, mất quyền production có thể kéo theo mất backup. Cần **tách quyền, immutable/offsite copies, audit trails và quy trình restore khi hệ thống quản trị chính bị xâm phạm**.

## 17. Giám sát backup khi write throughput thay đổi

Một backup job thành công tuần trước có thể thất bại trong đợt flash sale vì **oplog churn, latency, index build, IO pressure hoặc thiếu disk headroom**. Giám sát liên tục tốt hơn một cron job im lặng trả exit code 0.

### 17.1. Những số liệu tối thiểu

| Metric | Nên đo | Cảnh báo khi |
|---|---|---|
| **Last verified recovery point** | Timestamp backup/PITR mới nhất đã được xác nhận. | Lâu hơn RPO/SLO cho phép. |
| **Backup job success/failure** | Exit codes/managed job states, errors. | Job fail hoặc skipped nhưng scheduler vẫn báo success. |
| **Backup duration** | Thời gian tạo snapshot/dump, copy offsite. | Vượt backup window, tăng đột ngột. |
| **Oplog window** | Khoảng thời gian còn history. | Quá sát backup duration + retry margin. |
| **Replication lag** | Lag backup secondary và các secondaries. | Recovery point stale hoặc node không bắt kịp. |
| **Write QPS/oplog bytes/sec** | Đỉnh/biến động theo thời gian. | Oplog window thu hẹp nhanh lúc peak. |
| **CPU/IOPS/cache pressure** | Primary, backup secondary, storage. | Backup làm tăng p95/p99 latency của app. |
| **Backup artifact size** | Full/incremental sizes và tăng trưởng. | Nhỏ bất thường hoặc lớn bất thường. |
| **Checksum/transfer result** | Hash nguồn/đích, upload integrity. | Mismatch hoặc copy thiếu/truncated. |
| **Restore-drill outcome** | Pass/fail, thời gian, invariants. | Chưa drill theo lịch hoặc fail. |
| **PITR window coverage** | Earliest/latest restore timestamp. | Cửa sổ ngắn hơn retention/RPO policy. |
| **Key/KMS availability** | KMS grants, backup encryption keys. | Key revoked/không còn truy cập lúc restore. |
| **Sharded cluster state** | Balancer/migrations, pending DDL/reshard. | Manual backup diễn ra khi cluster đang thay topology. |

### 17.2. Xem oplog window trên replica set

Trên `mongosh` kết nối trực tiếp một replica-set member (theo quyền hỗ trợ):

~~~javascript
// Helper truyền thống hiển thị oplog size/time range.
rs.printReplicationInfo()

// Xem trạng thái replication, member health/optimes.
rs.status()
~~~

Trong deployment mới, một số helpers có thể thay đổi hoặc được thay bằng monitoring/API; lấy metrics từ Atlas/Ops Manager nếu phù hợp. **Không** gọi helper replica-set trực tiếp qua `mongos` rồi suy ra đây là một oplog toàn cluster.

### 17.3. Oplog window phụ thuộc tốc độ ghi

Một ước lượng sơ bộ:

\[
\text{Oplog history duration}
\approx
\frac{\text{effective oplog capacity}}
{\text{average oplog write bytes/second}}
\]

Nếu phát sinh nhiều writes lớn, **window sẽ giảm** dù dung lượng oplog được giữ cố định, trừ khi có minimum retention hoặc cấu hình khác. Đây chỉ là mô hình sơ bộ; thực tế có phân phối entry sizes, truncation policies, transaction operations và retention settings.

### 17.4. Minh họa capacity planning

~~~text
Off-peak:
  backup duration: 45 phút
  oplog window:    5 giờ

Flash sale:
  backup duration: 90 phút
  oplog window:    55 phút
~~~

Ở flash sale, backup duration đã vượt window quan sát, dễ có rủi ro backup agent cần history không còn. Không dùng chính xác 90/55 như một ngưỡng bất biến: thu logs của tool và workload, tăng headroom/throttle hoặc dùng backup method phù hợp.

### 17.5. Đừng chỉ giám sát disk free

Một node có 2 TB disk trống nhưng mỗi lần backup làm p99 latency tăng 5 lần vẫn có thể không đáp ứng SLO. Backup workload cần được coi là **một khách hàng của CPU, network, I/O, cache**; nếu backup dedicated secondary, cần bảo đảm secondary đó đủ capacity và không làm oplog/replication tụt quá xa.

### 17.6. Alert khi backup “success nhưng sai phạm vi”

Ví dụ job định backup toàn replica set nhưng người vận hành thêm `--db=app` vào `mongodump`, trong khi lại bỏ `--oplog` để command chạy được. Job có thể thành công về mặt exit code nhưng **đã đánh mất mục tiêu consistency**. Vì vậy manifest/automation phải ghi rõ:

- Backup **full replica set** hay partial DB/collection?
- Có `--oplog` không, tool version nào?
- Có recovery timestamp/point ở đâu?
- Target cluster và roles?
- Có kết quả **restore drill** và business checks?

Không báo “healthy” chỉ dựa vào việc file tồn tại.

## 18. Runbook tổng thể: từ backup đến restore/cutover

Một runbook phải đủ cụ thể để operator thực hiện **trong sự cố**, không yêu cầu tự suy kiến trúc lúc production đang xuống.

### Giai đoạn A — Định nghĩa mục tiêu

1. Chỉ rõ topology: standalone, replica set, sharded cluster, Atlas/managed.
2. Định nghĩa RPO, RTO, recovery granularity (full cluster, DB, collection).
3. Liệt kê business invariants và external dependencies.
4. Chọn phương pháp backup phù hợp **khả năng writes tiếp diễn**.
5. Xác định retention, offsite/immutable storage và compliance.
6. Ghi version/FCV và các backup/restore tool versions được hỗ trợ.

### Giai đoạn B — Chuẩn bị trước backup

1. Kiểm tra replica set healthy, oplog window/replication lag/capacity.
2. Xác minh user credentials/roles/KMS permissions.
3. Với manual sharded backup: lịch phối hợp dừng writes/balancer/DDL.
4. Với replica-set `--oplog`: chuẩn bị full dump, tránh DDL bị cấm.
5. Chọn storage destination đủ dung lượng và được mã hóa.
6. Gắn backup ID, start time, source topology, tool version vào manifest.

### Giai đoạn C — Thu thập backup

~~~text
Backup job starts
   |
   +-- Check source topology/version/health
   |
   +-- Capture data with appropriate consistency method
   |
   +-- Capture oplog or coordinated snapshot metadata
   |
   +-- Copy artifact to protected storage
   |
   +-- Verify complete artifact / checksum
   |
   +-- Record recovery point and retention
   |
   v
Mark artifact "CANDIDATE FOR RESTORE"
~~~

Lúc này mới có **backup artifact candidate**. Không cần mọi backup đều phải restore kiểm tra ngay lập tức, nhưng cần lịch **restore validation** và không coi trạng thái file-only là đã được chứng minh khôi phục được.

### Giai đoạn D — Restore test vào môi trường tách biệt

1. Chọn artifact có recovery point/retention phù hợp.
2. Tạo **target DR mới/trống** với topology/version tương thích.
3. Ngắt inbound application writes tới DR.
4. Restore data và oplog/PITR theo đúng phương pháp.
5. Xem logs/exit codes và giai đoạn index builds.
6. Xác minh database names, document counts, schema/index definitions.
7. Chạy business invariants (ví dụ wallet totals, orphan references).
8. Kiểm tra queries trọng yếu/end-to-end APIs.
9. Ghi kết quả và thời gian restore **thực tế**.

### Giai đoạn E — Khi phải cutover production

1. Tuyên bố sự cố, chọn recovery point P được phê duyệt.
2. Tạm dừng/điều phối writes và message consumers trước cutover.
3. Restore vào target độc lập hoặc theo in-place runbook được chấp thuận.
4. Chạy integrity/business checks và xác nhận quyền/KMS.
5. Chuyển connection strings/DNS/router đến target.
6. Vô hiệu/hướng dẫn lại producers ghi vào cluster cũ để tránh split brain.
7. Warm caches/rebuild search indexes/reconcile external events.
8. Theo dõi errors, duplicates, lag và p95/p99.
9. Ghi lại dữ liệu đã mất theo RPO thực tế, thông báo stakeholders.

### Giai đoạn F — Sau sự cố

- Lưu artifact hashes, manifest, logs, chosen recovery point, người phê duyệt.
- Kiểm tra nguyên nhân: backup method sai, oplog gap, storage lỗi, thao tác DDL, quyền/KMS.
- Điều chỉnh retention/monitoring/capacity và diễn tập lại.
- Không xóa old cluster/artifacts sớm nếu chưa xác minh đầy đủ và chưa hết retention/forensics policy.

### 18.1. Ví dụ backup manifest

~~~json
{
  "backupId": "RS-LAB-20261114-0100",
  "sourceType": "replicaSet",
  "sourceName": "rsLab",
  "method": "mongodump --oplog",
  "databaseToolsVersion": "100.x.y",
  "serverVersion": "8.x.y",
  "fcv": "8.0",
  "startedAtUtc": "2026-11-14T01:00:00Z",
  "finishedAtUtc": "2026-11-14T01:18:00Z",
  "archive": "rsLab-2026-11-14.archive",
  "checksumSha256": "<computed-by-backup-job>",
  "restorePoint": "<recorded-from-backup-metadata>",
  "store": "encrypted-offsite",
  "restoreDrill": {
    "status": "NOT_YET_RUN",
    "lastVerifiedAtUtc": null
  }
}
~~~

**Đây là JSON minh họa về metadata**, không phải một chuẩn bắt buộc của MongoDB. `checksumSha256` phải do chương trình tính trên file thực; `restorePoint` không được tự suy từ giờ chạy scheduler.

### 18.2. Một bài học quan trọng về restore target

Mục tiêu DR không được nhận writes từ production trước khi restore hoàn tất. Ngoài ra, phải tránh hai cluster cùng nhận writes sau cutover. Nếu cluster cũ quay trở lại trong khi ứng dụng đã chuyển sang cluster mới, cần định nghĩa **fencing/switchover policy**; nếu không có, bạn có thể có hai “nguồn sự thật” phân kỳ dù backup ban đầu consistent.

## 19. Lab minh họa: writes chạy song song với backup

Mục tiêu lab không phải gây lỗi production, mà là quan sát sự khác nhau giữa **file dump bình thường** và **full dump có oplog** trên một **replica set test**. Kết quả thời gian có thể thay đổi theo máy/phiên bản; không giả định luôn tạo ra một trường hợp inconsistency cụ thể chỉ bằng 30 writes.

### 19.1. Chuẩn bị replica set test

Yêu cầu:

- Có replica set `rsLab` được khởi tạo và healthy.
- Có quyền backup/restore phù hợp.
- Dùng database `backup342_lab` **riêng biệt**.
- Hai terminal: một chạy writer, một chạy `mongodump`.
- Restore target **khác nguồn**, rỗng, không chứa dữ liệu có giá trị.

**Không** dùng một cluster production hoặc Atlas đang phục vụ khách hàng để chạy các ví dụ xóa/restore ở bài này.

### 19.2. Tạo fixture

Trong `mongosh` của replica set lab:

~~~javascript
const lab = db.getSiblingDB("backup342_lab")

lab.wallets.insertMany([
  { _id: "A", balanceMinor: 100000 },
  { _id: "B", balanceMinor: 100000 }
])

lab.transfers.insertOne({
  _id: "SEED",
  from: "system",
  to: "system",
  amountMinor: 0,
  state: "SEED"
})

lab.events.insertMany([
  { _id: 1, label: "seed", createdAt: new Date() },
  { _id: 2, label: "seed", createdAt: new Date() }
])
~~~

**Chạy một lần.** Nếu chạy lại, có thể trùng `_id`. Khi muốn reset, chỉ làm trên database lab đã được xác minh, không copy lệnh drop vào môi trường khác.

### 19.3. Terminal A — Tạo một số writes đồng thời

Trong `mongosh`:

~~~javascript
const lab = db.getSiblingDB("backup342_lab")

for (let i = 3; i <= 50; i++) {
  lab.events.insertOne({
    _id: i,
    label: "concurrent-write",
    createdAt: new Date()
  })
  sleep(100)
}
~~~

Đây là **50 hoặc ít hơn** operations có giới hạn rõ ràng, không phải vòng vô hạn; không phải test chịu tải. Nếu chạy lại sau khi đã insert, có thể trùng `_id`. Dùng một database lab khác hoặc thay ranges khi muốn lặp.

### 19.4. Terminal B — Dump thường

~~~bash
mongodump \
  --uri="mongodb://backupuser@rs-lab:27017/?replicaSet=rsLab" \
  --archive="./plain.archive"
~~~

Để quan sát khác biệt thật, corpus phải đủ lớn để dump kéo dài và writers phải trùng thời gian. Với fixture nhỏ, tool có thể hoàn tất trước khi writers chạy; **không thấy lỗi không chứng minh dump thường consistent khi có concurrent writes**.

### 19.5. Terminal B — Full dump với oplog

~~~bash
mongodump \
  --uri="mongodb://backupuser@rs-lab:27017/?replicaSet=rsLab" \
  --archive="./with-oplog.archive" \
  --oplog
~~~

Đây là cách đúng để thử **online consistent logical dump một replica set** theo MongoDB Database Tools, miễn không có DDL bị cấm và tool hoàn tất thành công. `--oplog` không được kết hợp `--db=backup342_lab`; backup phải là full replica-set dump.

### 19.6. Restore và so sánh

Restore từng archive vào **hai targets DR trống, tách biệt**:

~~~bash
# Target DR 1: plain dump, không dùng oplogReplay.
mongorestore \
  --uri="mongodb://restoreuser@restore-plain:27017/" \
  --archive="./plain.archive"

# Target DR 2: full dump với oplog.
mongorestore \
  --uri="mongodb://restoreuser@restore-oplog:27017/" \
  --archive="./with-oplog.archive" \
  --oplogReplay
~~~

Không restore cả hai vào cùng một target; không chạy trên live source. Kiểm tra:

~~~javascript
const lab = db.getSiblingDB("backup342_lab")

printjson({
  events: lab.events.countDocuments({}),
  wallets: lab.wallets.countDocuments({}),
  transfers: lab.transfers.countDocuments({})
})

printjson(lab.wallets.find().sort({ _id: 1 }).toArray())
~~~

Vì writers có thể kết thúc trước/giữa/sau backup, **số events khác nhau giữa snapshots không tự chứng minh lỗi consistency**. Một backup ở thời điểm sớm có thể đúng dù thiếu writes mới. Mục tiêu là hiểu **recovery point** và kiểm tra có thể restore một trạng thái logic hợp lệ.

### 19.7. Muốn chứng minh invariant tốt hơn, dùng transaction

Có thể viết một writer phát sinh các transfers atomically thay vì chỉ insert events. Sau restore, kiểm:

1. Tổng ví A+B không đổi khi chỉ chuyển nội bộ.
2. Mỗi committed transfer ID có số dư tương ứng.
3. Không có transfer ở trạng thái một nửa; kiểm xem dữ liệu trước/sau recovery point có hợp lý.
4. Khi so hai backups, không dùng count thô để khẳng định một backup hỏng chỉ vì nó cũ hơn.

Với một fixture bé, thao tác trùng thời gian không chắc chắn; để đánh giá nghiêm túc cần test harness có concurrency/timestamps được kiểm soát, không phải dựa vào một lần chạy may rủi.

### 19.8. Sau lab phải dọn môi trường an toàn

Chỉ xóa các targets test có nhãn riêng sau khi xác minh **đúng môi trường DR**. Giữ logs và archive mẫu nếu dùng cho tài liệu đào tạo, với chính sách bảo mật tương ứng. Không xóa backup production vì thấy test restore thành công một lần.

## 20. Các nhầm lẫn thường gặp

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| “File BSON restore được là backup consistent.” | Từng collection có thể lấy từ những thời điểm khác nhau. | Cần point-in-time guarantee và kiểm business invariant. |
| “Dump thường là snapshot tại lúc bắt đầu.” | `mongodump` không khóa toàn DB; writes xảy ra trong lúc quét. | Dùng `--oplog` trên replica set hoặc managed backup. |
| “`--oplog` chạy được với `--db`.” | Tool yêu cầu full dump replica set. | Không giới hạn namespace khi dùng `--oplog`. |
| “Dump qua `mongos --oplog` cho snapshot toàn cluster.” | `mongos` không là một oplog toàn cluster. | Dùng managed coordinated backup hoặc manual sharded runbook. |
| “Có thể dùng `--oplogReplay` cho sharded restore.” | Database Tools không hỗ trợ theo mô hình này. | Dùng cluster restore mechanism được hỗ trợ. |
| “Dump mỗi shard cùng phút là đủ.” | Vẫn lệch transaction commit/metadata ranges. | Cần global consistent cut/stop writes. |
| “Dừng balancer là đủ để backup sharded cluster.” | Cross-shard writes vẫn tiếp diễn. | Manual procedure yêu cầu dừng writes/schema operations. |
| “Có `readConcern:majority` là full snapshot.” | Majority reads vẫn có thể ở các timestamps khác nhau. | Snapshot timestamp và backup method là vấn đề khác. |
| “Write majority đảm bảo backup mới nhất.” | Backup có recovery point riêng và có thể cũ. | Majority durability khác RPO. |
| “Secondary luôn đồng bộ primary.” | Replication asynchronous, có lag. | Xem optime/lag và backup recovery point. |
| “Filesystem `cp` sống đủ để restore.” | Các files copy vào các thời điểm khác. | Atomic volume snapshot hoặc khóa writes theo docs. |
| “Data/journal khác volumes snapshot tuần tự vẫn an toàn.” | Hai snapshots có thể không đồng bộ. | Atomic group snapshot được chứng minh hoặc fsyncLock/quiesce. |
| “`fsyncLock` không ảnh hưởng người dùng.” | Có thể block writes/replication. | Dùng backup node/maintenance window, luôn unlock. |
| “Journal giống oplog.” | Journal phục vụ crash recovery; oplog phục vụ replication/redo workflows. | Chọn đúng công cụ theo mục tiêu. |
| “Snapshot nhanh nghĩa là restore cũng nhanh.” | Copy, replay, index build, validation, cutover tốn thời gian. | Đo RTO bằng restore drill. |
| “Snapshot consistent nghĩa là zero data loss.” | Writes sau point P không có trong backup. | RPO là tiêu chí riêng. |
| “PITR window vô hạn.” | Chỉ restore trong retention window được cấu hình. | Theo dõi earliest/latest restorable point. |
| “Backup thành công thì không cần thử restore.” | Artifact có thể không compatible hoặc thiếu keys. | Restore drills thường kỳ. |
| “Một checksum tốt chứng minh database đúng.” | Chỉ chứng minh file bytes nguyên vẹn. | Cần restore + kiểm invariants. |
| “Có transaction thì dump thường luôn consistent.” | Backup đọc dữ liệu ở các thời điểm khác nhau. | Transaction và backup snapshot boundary độc lập. |
| “Nếu ứng dụng ghi không atomic, backup sẽ sửa hộ.” | Snapshot có thể chụp trạng thái trung gian thật. | Sửa application transaction/outbox logic. |
| “Backup MongoDB bao gồm Kafka offsets và S3 objects.” | Ngoài phạm vi DB backup. | Thiết kế multi-system recovery và replay. |
| “Outbox có nghĩa sau restore không thể duplicate event.” | Restore có thể quay lại trạng thái unsent. | Idempotent consumers/stable event IDs. |
| “Backup physical snapshot cùng site là đủ DR.” | Site/storage/credentials có thể mất cùng lúc. | Offsite/immutable copies và restore drills. |
| “Có file archive thì chỉ cần chmod là restore.” | Thiếu role/KMS/FCV/version/topology có thể fail. | Xác minh prerequisites trước sự cố. |
| “Index/data luôn đầy đủ ngay sau restore.” | Logical restore rebuild indexes, Search index sync lại. | Tính RTO tới lúc chức năng sẵn sàng. |
| “Backup một collection đủ cho transaction nhiều collections.” | Relationships có thể lệch trạng thái. | Cần logical scope/consistency strategy phù hợp. |
| “Có thể chọn `--oplogLimit` bất kỳ để PITR.” | Replay partial ranges sai dễ làm inconsistency. | Dùng managed PITR hoặc quy trình oplog chuyên biệt đã chứng minh. |
| “FCV upgrade không ảnh hưởng backup.” | Có format conversion không replay được giữa 8.x và 9.0 cho time-series. | Tránh backup spanning format transition; test restore. |
| “Nếu restore failed thì chạy lại chồng lên dữ liệu dở dang.” | Target có thể partial/inconsistent. | Reset target DR được phép rồi restore từ đầu. |
| “Restore vào production đang nhận writes cho nhanh.” | Dễ xung đột và mất dữ liệu. | Restore vào target cách ly, validate rồi cutover. |
| “Sau cutover có thể để cluster cũ nhận writes song song.” | Tạo split brain/nguồn dữ liệu phân kỳ. | Fencing old primary/writers và kiểm soát switchover. |

### 20.1. Tách ba câu hỏi chẩn đoán

~~~text
Backup file có hoàn chỉnh không?
  -> checksum, file size, tool exit code, transfer logs

Backup có nhất quán tại một mốc không?
  -> method, oplog/snapshot metadata, tool docs, restore invariants

Backup có đáp ứng RPO/RTO không?
  -> actual recovery point, restore duration, app readiness
~~~

Không dùng một từ “backup success” để thay cả ba phép đánh giá.

## 21. Bài tập tình huống và đáp án

Những bài tập dưới đây dùng số liệu và hệ thống **giả định**; chúng không phải kết quả của một lần chạy backup thật. Khi bài yêu cầu chọn command, áp dụng trên **replica set/sharded lab hoặc DR target** với quyền thích hợp, không chạy thao tác phục hồi/khóa writes trên production.

### Bài 1 — Hai collections được dump ở hai thời điểm

**Đề:** `mongodump` đọc `wallets` lúc 09:00, đọc `transfers` lúc 09:05, một transaction commit lúc 09:03. Bản dump có chắc phản ánh một thời điểm không?

**Đáp án:** Không, nếu dùng dump thường không có cơ chế snapshot/oplog. `wallets` có thể ở trước T và `transfers` ở sau T. Dùng online full replica-set dump có `--oplog` hoặc managed point-in-time backup được hỗ trợ.

### Bài 2 — BSON hợp lệ nhưng tiền không cân

**Đề:** Sau restore, mọi collections đều parse được nhưng tổng `wallet.balanceMinor` giảm 20.000 so với ledger. Tình huống nào đáng điều tra trước?

**Đáp án:** Kiểm tra **backup consistency method**, recovery timestamp, transaction boundaries và restore oplog có được replay không. Đồng thời kiểm logic application có atomic transaction khi ghi không. File BSON hợp lệ không loại trừ lỗi thời điểm hoặc lỗi business trước khi backup.

### Bài 3 — Khi nào dùng `--oplog`?

**Đề:** Một replica set 3 nodes đang phục vụ writes; cần full logical backup mà không dừng writes. Chọn tool/flags?

**Đáp án:** `mongodump --oplog` cho **full dump của một replica set member** trên Database Tools/version hỗ trợ; khi restore dùng `mongorestore --oplogReplay` và verify. Tránh DDL operations làm dump fail, monitor oplog window.

### Bài 4 — `--oplog` kết hợp `--db`

**Đề:** Developer chạy `mongodump --db app --oplog` và nhận lỗi. Tại sao?

**Đáp án:** `--oplog` yêu cầu **full replica set dump**, không kết hợp `--db`, `--collection`, `--query` và một số flags thu hẹp. Muốn backup riêng DB, cần phương án khác và không tự tuyên bố có full point-in-time guarantee.

### Bài 5 — Restore bỏ `--oplogReplay`

**Đề:** Team có full dump `--oplog` nhưng khôi phục chỉ bằng `mongorestore --archive=file`. Có bảo đảm consistency như thiết kế không?

**Đáp án:** Không. Nếu không replay oplog, bản dump documents có thể phản ánh nhiều thời điểm. Phải dùng `--oplogReplay` theo đúng định dạng/conditions và kiểm logs.

### Bài 6 — Chọn một collection khi oplog replay

**Đề:** Có thể `mongorestore --oplogReplay --nsInclude="app.wallets"` trên full dump không?

**Đáp án:** Không theo limitations Database Tools. Oplog replay cho full replica-set dump không hỗ trợ tùy tiện `--db`, `--collection`, `--nsInclude`, `--nsExclude`, `--nsFrom` hay `--nsTo`. Thiết kế selective restore procedure riêng nếu cần.

### Bài 7 — Dump secondary có automatically consistent không?

**Đề:** Vì backup chạy trên secondary, một người nói không cần `--oplog`. Đúng không?

**Đáp án:** Không. Secondary vẫn apply writes từ oplog trong khi dump quét; còn có lag. `readPreference:secondary` giảm tải primary, **không đóng băng snapshot**. Với consistent full replica-set logical backup, xem `--oplog` và recovery point.

### Bài 8 — Majority reads

**Đề:** Hai collections được đọc với `readConcern:"majority"` trước và sau một transaction majority commit. Đây có phải một snapshot duy nhất?

**Đáp án:** Không. Mỗi read có thể ở một thời điểm, dù dữ liệu trả về đã majority committed. **Majority visibility ≠ global snapshot timestamp**.

### Bài 9 — Majority writes và RPO

**Đề:** Write lúc 10:02 được `w:"majority"` ack. Backup recovery point là 10:00. Restore có chứa write 10:02 không?

**Đáp án:** Không. Backup chỉ phản ánh trạng thái đến recovery point phù hợp. Majority write không làm thay đổi thời điểm của bản backup đã tạo. Đây là vấn đề RPO.

### Bài 10 — `w:1` và election

**Đề:** Client nhận ACK `w:1` nhưng primary fail trước khi entry được majority replicated. Sau election, write có thể thế nào?

**Đáp án:** Có thể bị rollback. Nếu cần durability mạnh cho business transaction, xem `w:"majority"` cùng cấu hình write concern phù hợp. Không coi primary ACK là bảo đảm mọi backup/secondary đã có write.

### Bài 11 — Journal là oplog?

**Đề:** Operator sao chép journal files rồi nói có thể replay đến mọi timestamp trong tuần. Đúng không?

**Đáp án:** Không. WiredTiger journal phục vụ **crash recovery**, còn oplog phục vụ replication và một số log-based backup/PITR workflows. Journal không phải archive liên tục một tuần mặc định.

### Bài 12 — Filesystem snapshot một volume

**Đề:** Data và journal cùng một atomic snapshot volume của một replica set secondary. Writes vẫn chạy trên primary. Điều gì có thể được bảo đảm?

**Đáp án:** Với storage/tooling đáp ứng MongoDB procedure, snapshot có thể tạo **crash-consistent ảnh của node secondary**. Nhưng nó có thể **stale** vì replication lag và không tạo một global point cho sharded cluster. Phải test restore và business invariants.

### Bài 13 — Data và journal khác volumes

**Đề:** Volume data chụp lúc 10:00, journal volume chụp 10:01 khi writes đang chạy. Có an toàn không?

**Đáp án:** Không bảo đảm. Snapshot hai volumes có thể lệch trạng thái. Theo MongoDB filesystem snapshot tutorial, cần **khóa/đình chỉ writes** khi journals/data nằm trên volumes tách biệt theo quy trình, hoặc có cơ chế atomic group snapshot được chứng minh.

### Bài 14 — `rsync` live data directory

**Đề:** Cron job chạy `rsync -a /var/lib/mongodb /backup` mỗi giờ khi mongod vẫn ghi. Có được gọi là consistent hot backup không?

**Đáp án:** Không. `rsync` đọc từng file nối tiếp, không chốt toàn tập data/journal ở cùng thời điểm. Dùng atomic filesystem snapshot hoặc MongoDB backup methods được hỗ trợ.

### Bài 15 — `fsyncLock` trên primary

**Đề:** Team chạy `db.fsyncLock()` trên primary giữa giờ cao điểm để chụp snapshot. Hậu quả?

**Đáp án:** Có thể **chặn writes và ảnh hưởng availability/latency**, trái yêu cầu “writes vẫn chạy”. Chỉ dùng theo approved runbook, thường cân nhắc backup secondary hoặc managed backup; **phải unlock** an toàn.

### Bài 16 — Oplog window không đủ

**Đề:** Dump cần 2 giờ, oplog window giảm còn 40 phút khi flash sale. Cần làm gì?

**Đáp án:** Đây là rủi ro không giữ đủ history. Giám sát errors/lag, tăng capacity/oplog retention có tính toán hoặc giảm dump duration/throttle/chọn managed solution. Không coi backup thành công nếu tool báo oplog gap.

### Bài 17 — Backups trên mỗi shard vào thời điểm khác

**Đề:** Shard A được snapshot 12:00:00 và B 12:01:00; transaction ghi cả hai commit 12:00:30. Kết quả?

**Đáp án:** Có thể chỉ một shard chứa thay đổi của T; cluster restore không nhất quán. Dùng coordinated cluster-wide backup hoặc manual procedure có writes quiesced.

### Bài 18 — Backup trên `mongos --oplog`

**Đề:** Có thể chạy một `mongodump --oplog` qua `mongos` để sao lưu online tất cả shards không?

**Đáp án:** Không. `--oplog` trên mongos **không đảm bảo global point-in-time snapshot**, và Database Tools không hỗ trợ dùng nó như replica-set full backup cho sharded cluster.

### Bài 19 — Balancer đang di chuyển chunks

**Đề:** Trong lúc dump từng shard, balancer chuyển một range từ shard A sang B. Điều gì có thể sai?

**Đáp án:** Dữ liệu có thể **bị đúp hoặc bỏ sót** khi chụp các shards không cùng điểm/metadata. Manual backup yêu cầu dừng balancer, chờ migrations hoàn tất và dừng writes/schema transformations theo tutorial.

### Bài 20 — Config server metadata

**Đề:** Operator backup đủ data files từng shard nhưng bỏ qua config server state. Có đủ để restore đúng topology không?

**Đáp án:** Không. Config server giữ chunk/range ownership và sharding metadata. Restore toàn cluster cần metadata tương thích, không tự insert chỉnh `config.*` bằng tay để “sửa” đường dẫn ranges.

### Bài 21 — Atlas Cloud Backup có thể dùng khi cluster vẫn ghi?

**Đề:** Sharded cluster Atlas có backup management phù hợp; business không cho dừng writes. Có cần tự chạy `fsyncLock` trên tất cả shards?

**Đáp án:** Thông thường **không** với **Atlas managed coordinated backup** vì Atlas có cơ chế snapshot cluster-wide. Vẫn phải kiểm tra tier/version/policy, quyền backup và restore target. Không lấy quy trình thủ công của filesystem snapshot áp vào managed service như bước bắt buộc.

### Bài 22 — Snapshot khác Continuous Cloud Backup

**Đề:** Atlas chỉ có snapshots mỗi giờ, không bật Continuous Cloud Backup. Sự cố lúc 10:49, snapshot mới nhất 10:00. Mất tối đa bao lâu dữ liệu?

**Đáp án:** Có thể mất gần **49 phút writes** sau snapshot 10:00 (trong tình huống giả định). Snapshot có thể perfectly consistent nhưng **RPO không đáp ứng mục tiêu 5 phút**. Cần continuous/PITR phù hợp hoặc điều chỉnh policy.

### Bài 23 — PITR về trước lệnh delete nhầm

**Đề:** Lệnh xóa sai commit 09:17, phát hiện 09:18; PITR window bao 09:16:59. Nên làm gì?

**Đáp án:** Chọn **recovery point được xác minh trước delete**, phù hợp timestamps/semantics của Atlas, restore vào target DR thích hợp, kiểm tra dữ liệu rồi cutover/reconcile. Không chỉ nhập ngày giờ ước lượng rồi coi chắc chắn không chứa operation sai.

### Bài 24 — PITR window chỉ một ngày

**Đề:** Một lệnh delete sai xảy ra 3 ngày trước và PITR window chỉ 24 giờ. Có thể chọn PITR ngay trước lệnh đó không?

**Đáp án:** Không nếu restore point đã nằm ngoài history window. Có thể xem snapshots retention cũ hơn hoặc các external data copies, nhưng không tuyên bố có arbitrary-time PITR vô hạn.

### Bài 25 — RPO thấp nhưng RTO cao

**Đề:** PITR chỉ mất tối đa 1 phút data, nhưng khôi phục 10 TB và rebuild indexes mất 7 giờ. Hệ thống có đáp ứng SLA RTO 1 giờ không?

**Đáp án:** Không. RPO thấp không đảm bảo RTO thấp. Cần đo end-to-end restore/cutover, tối ưu topology/restore methods, hot standby nếu phù hợp và kế hoạch read model/index build.

### Bài 26 — Restore in-place vào target có dữ liệu

**Đề:** Operator chọn Restore cluster-level ngay trên target đang phục vụ người dùng. Rủi ro?

**Đáp án:** Cluster-level restore có thể **xóa dữ liệu target hiện có** và gây downtime; writes trong quá trình restore cũng nguy hiểm. Ưu tiên target DR mới/cách ly, xác minh rồi cutover nếu kiến trúc cho phép.

### Bài 27 — Restore giữa chừng thất bại

**Đề:** `mongorestore --oplogReplay` bị kill sau khi đã load một số collections. Có nên chạy lại cùng lệnh ngay trên target dở dang?

**Đáp án:** Không nên. Cần xem logs, giữ source backup bất biến, **reset/recreate target DR được phép** rồi restore lại từ đầu; kiểm tra full result. Đừng dùng `--drop` trên cluster chưa xác minh.

### Bài 28 — SHA256 match nhưng ledger lệch

**Đề:** Checksum nguồn và đích trùng, nhưng sau restore thiếu payment record tương ứng order. Checksum có loại trừ lỗi consistency không?

**Đáp án:** Không. Checksum chỉ bảo đảm bytes file không đổi khi truyền/lưu. Có thể backup được tạo với consistency method sai hoặc ứng dụng ghi không atomic. Cần điều tra recovery point/transactions và business checks.

### Bài 29 — Kafka event được gửi sau backup

**Đề:** Backup MongoDB lúc 10:00 có outbox E1=NEW, Kafka nhận E1 lúc 10:01, MongoDB restore về 10:00. Worker sẽ thấy gì?

**Đáp án:** Worker có thể thấy E1 chưa SENT và **gửi lại**; consumer phải có stable event IDs/idempotent processing để tránh double side effect. Đây không nhất thiết là lỗi backup.

### Bài 30 — Object storage và DB restore

**Đề:** MongoDB restore về thời điểm có record trỏ tới S3 file, nhưng file bị xóa sau đó khỏi S3 và không có versioned backup. Tài liệu có dùng được không?

**Đáp án:** Có thể không. MongoDB backup không tự chứa external object bytes. Cần phối hợp retention/backup của object storage và kiểm references sau restore.

### Bài 31 — TTL ngay sau restore

**Đề:** Restore collection có TTL 7 ngày từ snapshot 10 ngày trước. Một số documents biến mất sau khi service lên. Điều này chắc chắn là backup không nhất quán?

**Đáp án:** Không nhất thiết. TTL monitor có thể xóa documents đã quá hạn theo chính sách sau restore. Cần kiểm tra TTL indexes, logical clocks và trạng thái tại recovery point trước khi kết luận sai.

### Bài 32 — Search chưa READY

**Đề:** MongoDB collections đã restore, API tìm kiếm qua Atlas Search trả ít kết quả hoặc không sẵn sàng. Vì sao?

**Đáp án:** Search index data có thể cần **build/initial sync** sau khi khôi phục index definitions. RTO phải tính cả thời gian search readiness, không chỉ CRUD database.

### Bài 33 — MongoDB 8.x → 9.0 FCV conversion

**Đề:** `mongodump --oplog` chạy trên deployment có time-series khi FCV được đổi từ 8.x sang 9.0. Có được coi backup nhất quán không?

**Đáp án:** Không nên. Database Tools docs cảnh báo oplog có thể bắc qua **time-series format conversion** mà `mongorestore --oplogReplay` không replay trực tiếp; Tools 100.18.0+ có thể fail thay vì tạo backup không restore được. Tránh version/FCV transformation trong backup window; đối chiếu docs đúng branch.

### Bài 34 — Balancer disabled nhưng writes vẫn chạy

**Đề:** Team dừng balancer, backup config server và shards nối tiếp khi applications vẫn ghi. Có global consistent point không?

**Đáp án:** Chưa bảo đảm. Dừng balancer chỉ tránh range migrations; **cross-shard writes/transactions** vẫn có thể xảy ra giữa snapshots. Manual procedures yêu cầu dừng writes/schema transformations, hoặc dùng managed coordinated backup.

### Bài 35 — “Chụp snapshot giống nhau theo đồng hồ”

**Đề:** Hai nodes có NTP đồng bộ và mỗi node được chụp đúng lúc 10:00:00 ±20 ms. Có thể khẳng định cross-shard transaction atomicity không?

**Đáp án:** Không. Đồng hồ wall-clock chính xác không tự tạo distributed consistent cut của committed writes/metadata, đặc biệt khi transactions và replication có delay. Cần coordination/recovery protocol được hỗ trợ.

### Bài 36 — Backup artifact giữ cùng account production

**Đề:** Cloud admin bị chiếm quyền và có thể xóa cả production lẫn backups ở cùng account. Phương án nên thêm?

**Đáp án:** Tách quyền/backup account, immutable/offsite copies, encryption/KMS independence theo khả năng, audit và restore drills. Backup phải tồn tại được qua failure mode của production.

### Bài 37 — Restore drill có đủ một count?

**Đề:** Sau restore, `db.orders.countDocuments({})` bằng nguồn tại một thời điểm ước lượng. Có cần kiểm gì thêm?

**Đáp án:** Có: payment/order relationships, transfer ledger totals, unique IDs, indexes, permissions, query availability, restore tool logs, recovery timestamp, external events và thời gian RTO. Cùng count không chứng minh cùng dữ liệu.

### Bài 38 — Chọn phương pháp cho sharded SaaS online

**Đề:** 12 shards, traffic 24/7, cross-shard transactions, RPO vài phút; team đề xuất 12 cron jobs `mongodump --oplog` song song. Có hợp lý không?

**Đáp án:** Không. Các oplogs riêng không tự cho một global consistency point, config metadata và chunk placement cũng phải khớp. Ưu tiên managed coordinated backup/PITR có hỗ trợ topology, hoặc giải pháp đã được chứng minh. Không tự ghép 12 outputs thành backup nhất quán.

### Bài 39 — Chọn phương pháp cho replica set nhỏ

**Đề:** Một replica set 3 nodes, 120 GB, có backup secondary, writes liên tục, cần bản logical backup hằng đêm; có thể chịu RPO 24h. Gợi ý giải pháp?

**Đáp án gợi ý:** Full `mongodump --oplog` từ secondary healthy, đủ oplog window và tránh DDL, offsite archive/checksum, restore bằng `--oplogReplay` vào DR, monitor job/replication, drill định kỳ. Nếu cần RPO thấp hơn thì xem managed PITR hoặc tăng backup frequency/method phù hợp.

### Bài 40 — Lập DR plan cho marketplace có Kafka và S3

**Đề:** Hệ thống gồm sharded MongoDB, Kafka payment events, S3 invoice PDFs, Redis cache. RPO 5 phút và RTO 1 giờ, writes không thể dừng để backup. Hãy nêu thiết kế có thể kiểm chứng.

**Đáp án gợi ý:**

1. Dùng **managed cluster-wide consistent backup/PITR** cho sharded MongoDB theo tier/region/version hỗ trợ.
2. Chọn recovery point P trong PITR window, có audit/timestamp đã xác minh.
3. Định nghĩa Kafka offset/eventId replay và consumer idempotency; không coi MongoDB restore làm Kafka tự quay lại P.
4. Lưu S3 objects/versioning/retention phù hợp để documents đã restore không trỏ file mất.
5. Invalidate/warm Redis sau cutover; Redis không là source of truth.
6. Restore vào cluster DR tương thích, test cross-shard transaction invariants và payment/order counts.
7. Dự trù time cho Search indexes, cache, connection cutover, role/KMS validation.
8. Giám sát RPO actual, RTO measured và error/duplicate rate sau chuyển đổi.
9. Có fencing để cluster cũ không cùng nhận writes; rehearsal định kỳ chứng minh RTO 1 giờ là khả thi.
10. Đặt alert nếu backup/PITR window/KMS/DR drills không đáp ứng policy.

Không có một lệnh MongoDB duy nhất khiến **mọi** hệ thống ngoài MongoDB nhất quán. Phương án đúng cần xác định ranh giới dữ liệu và cơ chế replay/repair của toàn ứng dụng.

## 22. Bảng quyết định nhanh theo topology và mục tiêu

| Bối cảnh | Có thể để writes tiếp diễn? | Phương án cân nhắc trước | Lỗi phải tránh |
|---|---|---|---|
| Standalone lab, dữ liệu không quan trọng | Có thể chấp nhận quiesce hoặc inconsistent dump khi phù hợp. | Dump/restore thử, kiểm tra rõ mức bảo đảm. | Gọi dump thường là snapshot consistent. |
| Replica set, full logical backup, writes 24/7 | **Có** khi thỏa điều kiện. | `mongodump --oplog` + `mongorestore --oplogReplay`. | Thêm `--db`/`--collection` hoặc bỏ replay. |
| Replica set, yêu cầu backup vật lý nhanh, một atomic volume | Có thể theo quy trình storage được hỗ trợ. | Filesystem snapshot data+journal của một member. | Live `rsync`/`cp` hoặc quên journal. |
| Replica set, journal/data ở volumes khác nhau | Phải có quiesce/atomic group strategy. | `fsyncLock` và snapshot theo Manual; cân nhắc secondary. | Chụp hai volumes ở hai thời điểm khi vẫn ghi. |
| Self-managed sharded cluster, dừng writes tạm được | **Không** trong thời gian manual backup được yêu cầu. | Sharded-cluster manual backup tutorial và coordinated maintenance. | Chỉ dừng balancer mà không dừng writes. |
| Sharded cluster, không thể dừng writes | Có, bằng dịch vụ phối hợp. | Atlas/Ops Manager/Cloud Manager coordinated backups. | Ghép các replica-set backups riêng không có global cut. |
| RPO tính bằng phút và phải chọn timestamp | Có, với PITR được bật và đủ window. | Continuous backup + point-in-time restore. | Chỉ có snapshot hourly mà hứa RPO 1 phút. |
| Yêu cầu restore riêng một collection | Phụ thuộc method/business invariant. | Selective restore/migration plan chuyên biệt. | Dùng `--oplogReplay --nsInclude` trái limitations. |
| Hệ thống có Kafka/S3/payment service | Backup MongoDB chưa đủ. | DB PITR + external replay/versioning/idempotency. | Coi backup MongoDB là whole-system transaction. |
| Production có search indexes lớn | Backup data chưa đủ làm RTO. | Tính index rebuild/warmup và query readiness. | Đo RTO đến lúc restore BSON xong rồi dừng đồng hồ. |

### 22.1. Luồng chọn phương pháp

~~~text
Toplogy là một replica set?
  |
  +-- Có:
  |     Cần full logical backup, giữ writes tiếp diễn?
  |       -> mongodump --oplog (đúng version/constraints)
  |       -> mongorestore --oplogReplay khi restore
  |
  |     Cần physical snapshot?
  |       -> atomic storage group + data/journal đầy đủ
  |       -> nếu volumes tách: fsyncLock/quiesce theo Manual
  |
  +-- Không: sharded cluster?
        |
        +-- Phải giữ writes?
        |     -> coordinated managed backup/PITR
        |
        +-- Có maintenance window dừng writes?
              -> manual sharded backup procedure
              -> stop balancer + writes + schema transformations

Cần RPO thấp hơn snapshot interval?
  -> PITR/continuous captured changes.

Cần khôi phục full application?
  -> MongoDB + Kafka/S3/Redis/payment + invariants.
~~~

### 22.2. Ba “bằng chứng” phải giữ sau mỗi lần backup

1. **Backup completion evidence:** Job ID, exit status, artifact paths, checksum, tool/server version, backup recovery point.
2. **Consistency evidence:** Method guarantee theo docs, trạng thái oplog/snapshot/cluster coordination, không có DDL conflicts, restore test business invariants.
3. **Recoverability evidence:** DR drill thành công, thời gian phục hồi thật, indexes/permissions/keys sẵn sàng, RPO/RTO được ghi lại.

Không cần mọi bản backup đều được restore thử ngay khi tạo, nhưng phải có **chiến lược kiểm tra định kỳ** và đủ lịch sử để phát hiện một phương pháp đã ngừng bảo đảm restore sau version/FCV change.

## 23. Tài liệu MongoDB chính thức

Các liên kết sau được dùng để đối chiếu cú pháp và giới hạn theo **MongoDB Server version, Database Tools version và managed cluster tier**. Trang `/manual/` thường là bản tài liệu hiện hành; nếu production chạy một dòng cũ, hãy chọn phiên bản tài liệu tương ứng trước khi áp dụng thao tác.

### 23.1. Logical dump và oplog replay

1. [`mongodump` — Database Tools](https://www.mongodb.com/docs/database-tools/mongodump/) — `--oplog`, full replica-set dump, các flags không kết hợp được, DDL làm dump fail, limitations của `mongos`.
2. [`mongodump` Behavior, Access and Usage](https://www.mongodb.com/docs/database-tools/mongodump/mongodump-behavior/) — output BSON/index definitions, read preference, scope/exclusions.
3. [`mongorestore` — Database Tools](https://www.mongodb.com/docs/database-tools/mongorestore/) — `--oplogReplay`, full restore constraints, `--oplogLimit` và định dạng archive/directory.
4. [`mongorestore` Behavior, Access and Usage](https://www.mongodb.com/docs/database-tools/mongorestore/mongorestore-behavior-access-usage/) — lỗi restore giữa chừng, transaction/oplog restrictions, time-series FCV format conversion.
5. [MongoDB Database Tools Documentation](https://www.mongodb.com/docs/database-tools/) — so sánh version Database Tools và server/FCV.

### 23.2. Filesystem snapshots và sharded cluster

6. [Back Up a Self-Managed Deployment with Filesystem Snapshots](https://www.mongodb.com/docs/manual/tutorial/backup-with-filesystem-snapshots/) — WiredTiger data/journal, atomic volume, `fsyncLock` khi volumes tách, restore.
7. [Back Up a Sharded Cluster with File System Snapshots](https://www.mongodb.com/docs/manual/tutorial/backup-sharded-cluster-with-filesystem-snapshots/) — dừng writes/balancer/DDL và sao lưu config servers + shards.
8. [Back Up a Self-Managed Sharded Cluster with a Database Dump](https://www.mongodb.com/docs/manual/tutorial/backup-sharded-cluster-with-database-dumps/) — manual sharded dump workflow và tính tương thích server patch levels.
9. [Backup and Restore a Self-Managed Sharded Cluster](https://www.mongodb.com/docs/manual/administration/backup-sharded-clusters/) — tập hợp procedures và cảnh báo cross-shard consistency.
10. [Backup Methods for Self-Managed Deployments](https://www.mongodb.com/docs/manual/core/backups/) — so sánh RPO/RTO, dump, physical snapshot và managed backups.
11. [Manage Sharded Cluster Balancer](https://www.mongodb.com/docs/manual/tutorial/manage-sharded-cluster-balancer/) — `sh.stopBalancer()` và kiểm tra migrations khi manual backup.
12. [`db.fsyncLock()`](https://www.mongodb.com/docs/manual/reference/method/db.fsyncLock/) — flush/lock để hỗ trợ backup với ảnh hưởng tới writes.
13. [`db.fsyncUnlock()`](https://www.mongodb.com/docs/manual/reference/method/db.fsyncUnlock/) — trả node khỏi trạng thái bị khóa.

### 23.3. Replica set, read/write concern và transaction

14. [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — oplog window, retention, resize và replication log semantics.
15. [Read Isolation, Consistency and Recency](https://www.mongodb.com/docs/manual/core/read-isolation-consistency-recency/) — local/majority/snapshot/causal consistency khác nhau.
16. [Read Concern `snapshot`](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/) — snapshot timestamp và điều kiện hỗ trợ.
17. [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — majority acknowledgement và durability.
18. [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — transaction atomicity và distributed transactions.
19. [Replica Set Rollbacks](https://www.mongodb.com/docs/manual/core/replica-set-rollbacks/) — writes có thể rollback khi chưa majority committed.

### 23.4. Atlas Cloud Backup, PITR và restore

20. [Atlas Cloud Backup Overview](https://www.mongodb.com/docs/atlas/backup/cloud-backup/overview/) — quản lý backup policies và điều kiện.
21. [Atlas Architecture — Guidance for Backups](https://www.mongodb.com/docs/atlas/architecture/current/backups/) — snapshots cluster-wide, continuous backups, RPO/RTO.
22. [Dedicated Cluster Backups](https://www.mongodb.com/docs/atlas/backup/cloud-backup/dedicated-cluster-backup/) — cách Atlas điều phối snapshot và captured changes.
23. [Recover a Point In Time with Continuous Cloud Backup](https://www.mongodb.com/docs/atlas/recover-pit-continuous-cloud-backup/) — lựa chọn timestamp và restore window.
24. [Restore from a Snapshot](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-from-snapshot/) — source/target topology, fallback snapshot consistency warning.
25. [Atlas Restore Overview](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-overview/) — prerequisites và tránh traffic trên target.
26. [Troubleshoot Backup and Restore Failures](https://www.mongodb.com/docs/manual/troubleshooting/backup-restore-failures/) — oplog gaps, backup agents, restore failures.

### 23.5. Cách dùng tài liệu an toàn

Trước khi chạy lệnh trong production, luôn trả lời:

1. Backup source là **replica set member** hay **mongos sharded cluster**?
2. Method có cho **writes tiếp tục** không, hay chỉ daemon vẫn chạy trong lúc writes bị khóa?
3. Recovery point được xác định thế nào và được ghi lại ở đâu?
4. Có DDL, chunk migration, FCV format conversion hay admin changes bị cấm không?
5. Oplog window đủ so với duration/lag không?
6. Restore target/version/FCV/topology có tương thích không?
7. Có encryption keys, credentials, index definitions và external dependencies không?
8. Có bài kiểm tra invariant, RPO/RTO và khả năng cutover an toàn không?

## 24. Kết luận

**Một bản sao lưu được tạo khi MongoDB vẫn đang nhận writes chỉ đáng tin nếu có thể khôi phục một trạng thái dữ liệu hợp lệ tại một thời điểm logic được xác định.** File BSON đầy đủ, checksum đúng hoặc screenshot “backup completed” **chưa đủ** để chứng minh tính nhất quán.

Trên **một replica set**, `mongodump --oplog` kết hợp `mongorestore --oplogReplay` là một phương pháp logical backup phù hợp khi vẫn nhận writes, với điều kiện **full dump, oplog window đủ, không có DDL bị cấm và kiểm tra restore**. Với **filesystem snapshot**, phải đảm bảo tính atomic của các volumes chứa data/journal, và dùng `fsyncLock`/quiesce theo hướng dẫn khi cần. Với **sharded cluster**, việc ghép backups từng shard không tạo global consistent point; backup thủ công cần phối hợp dừng writes/balancer/schema changes, còn hệ thống yêu cầu online cluster-wide snapshot thường phù hợp hơn với **Atlas/Ops Manager/Cloud Manager coordinated backups**.

Cuối cùng, consistency không đồng nghĩa **RPO bằng 0**, và backup DB không tự bao gồm Kafka/S3/Redis hoặc các services nghiệp vụ. Một chiến lược đáng tin phải có **recovery-point policy, oplog/PITR coverage, offsite immutable backups, restore drills, business invariants và cutover runbook**. Điều quan trọng nhất không phải “sao lưu được bao nhiêu GB”, mà là **có thể phục hồi đúng trạng thái cần thiết, trong thời gian cho phép, mà không phá vỡ các cam kết dữ liệu của ứng dụng**.
