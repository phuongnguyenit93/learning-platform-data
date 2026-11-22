# Đánh giá ổ đĩa, journal, checkpoint và cấu hình nén trong MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Tối ưu hiệu năng  
> **Bài học:** Đánh giá ổ đĩa, journal, checkpoint và cấu hình nén

## 1. Tình huống thực tế: MongoDB chậm dù CPU còn dư

Một dịch vụ đơn hàng có MongoDB replica set. Trong giờ cao điểm, đội vận hành ghi nhận:

- API ghi đơn hàng tăng từ p95 35 ms lên 350 ms.
- CPU primary khoảng 50–60%, không bão hòa.
- `iostat` báo `w_await` tăng mạnh, hàng đợi ghi kéo dài.
- WiredTiger có nhiều dirty pages và thời gian checkpoint tăng.
- Trên một volume cloud, write IOPS tiến sát giới hạn provisioned.
- Dung lượng disk thực tế tăng nhanh hơn dự kiến sau đợt nhập dữ liệu.

Có người đề xuất “tắt journal để ghi nhanh hơn”, người khác muốn “đổi tất cả collections sang zstd”, và một người cho rằng “thêm RAM là đủ”. Không có phương án nào chắc chắn đúng nếu chưa phân biệt các công đoạn:

```text
Application write
       |
       v
mongod: parse / validate / index updates
       |
       v
WiredTiger pages in cache
       |
       +---------------------+
       |                     |
       v                     v
Journal write-ahead log    Checkpoint / data files
       |                     |
       v                     v
Journal flush / fsync      Dirty page write / fsync
       |                     |
       +----------+----------+
                  |
                  v
             Filesystem / OS
                  |
                  v
            SSD / cloud disk
       (IOPS, throughput, latency,
         queue, capacity, burst)
```

**Journal** và **checkpoint** cùng tham gia bảo đảm độ bền dữ liệu, nhưng không phải hai bản sao có thể thay thế lẫn nhau. **Nén** giúp giảm số byte lưu/truyền tới storage, nhưng tiêu tốn CPU và có thể làm thay đổi hiệu năng theo workload. **Đánh giá ổ đĩa** phải xem cả latency, IOPS, throughput, dung lượng và giới hạn I/O thực.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định nút thắt của ổ đĩa bằng IOPS, MiB/s, latency, queue và giới hạn volume.
2. Phân biệt dữ liệu logic, bytes được cấp phát và dung lượng filesystem.
3. Giải thích WiredTiger journal, checkpoint, crash recovery và sự liên hệ với write concern.
4. Đọc các số liệu từ `serverStatus.wiredTiger.log`, `checkpoint`, `cache` và từ OS/cloud.
5. Hiểu ba nhóm nén: **collection block compression**, **journal compression**, **index prefix compression**.
6. So sánh `snappy`, `zlib`, `zstd` và `none` theo CPU, I/O, storage và latency.
7. Hiểu thay đổi cấu hình mặc định thường chỉ áp dụng cho **collection/index được tạo sau đó**.
8. Thiết kế benchmark công bằng, một thay đổi tại một thời điểm và có khả năng rollback.
9. Thực hành `mongosh`/công cụ hệ điều hành trên dữ liệu mô phỏng, không can thiệp cấu hình production.

## 2. Mô hình lưu trữ: từ document đến byte trên đĩa

MongoDB dùng WiredTiger làm storage engine mặc định trong các deployment phổ biến. Có nhiều lớp biến đổi giữa document BSON và byte thực trên ổ:

```text
BSON documents and indexes
          |
          v
WiredTiger B-tree pages
          |
       (compression)
          |
          v
Allocated WiredTiger data/index blocks
          |
          +---- Journal files
          +---- History store / oplog
          +---- Checkpoint and temporary I/O
          |
          v
Filesystem / OS page cache
          |
          v
Block device / cloud volume
          |
          v
Snapshots, backups, replicas elsewhere
```

Một document dài 2 KiB không đồng nghĩa MongoDB ghi đúng 2 KiB xuống đĩa trong mọi operation. Ghi có thể tạo thay đổi dữ liệu, thay đổi nhiều index, journal records, và sau đó checkpoint các pages. OS và storage có thể gom hoặc chia nhỏ I/O.

### 2.1. Các khái niệm dung lượng không giống nhau

| Khái niệm | Ví dụ cách đo | Ý nghĩa |
| --- | --- | --- |
| Document BSON logic | `dataSize` | Dữ liệu chưa nén theo thống kê MongoDB |
| Storage allocation | `storageSize` | Byte được cấp phát cho dữ liệu collection |
| Index allocation | `indexSize` | Byte được cấp phát cho indexes |
| Tổng DB data/index | `totalSize` | Thường = `storageSize + indexSize` |
| Journal files | Theo filesystem, `wiredTiger.log` | Write-ahead logging, biến động theo hoạt động |
| Oplog/history store | Theo namespace/filesystem | Cần cho replication, rollback/snapshots |
| Free space dùng lại | `freeStorageSize` khi hỗ trợ | Storage đã cấp phát nhưng có thể reuse |
| Filesystem used/free | `df -h` hoặc cloud metrics | Toàn bộ các file và metadata trên volume |
| Backups/snapshots | Công cụ backup/cloud | Có thể không nằm trên filesystem MongoDB |

Ví dụ:

```text
Logical BSON data       300 GiB
Collection allocation   180 GiB  (có compression)
Index allocation         45 GiB
Journal + oplog + khác   35 GiB
Filesystem overhead      10 GiB
---------------------------------
Disk used               ~270 GiB
```

Các số **minh họa**, không phải tỉ lệ mặc định. Cần lấy số từ cùng thời điểm, cùng node/volume, theo semantics từng metric.

### 2.2. Vì sao `dataSize` có thể lớn hơn `storageSize`?

Document BSON có những key name lặp đi lặp lại, nhiều chuỗi/JSON-like payload có tính lặp; block compressor tận dụng điều đó. Ví dụ 300 GiB BSON có thể nén thành ít hơn 200 GiB dữ liệu cấp phát.

Nhưng:

- Dữ liệu đã nén (JPEG, PDF, ZIP, ciphertext) có thể nén rất ít.
- Documents khác cấu trúc tạo tỉ lệ khác.
- Các indexes tiêu thụ thêm byte.
- Fragmentation và free space có thể khiến `storageSize` không giảm sau delete.
- Data size không bao gồm mọi chi phí journal, oplog và tệp ngoài DB.

Không dùng `dataSize / storageSize` như “compression ratio tuyệt đối” của toàn hệ thống.

## 3. Đánh giá phần cứng và cloud storage

### 3.1. Các tiêu chí trước khi chọn ổ

| Thuộc tính | Câu hỏi |
| --- | --- |
| Dung lượng có thể dùng | Còn bao nhiêu sau OS, journal, oplog và headroom? |
| Random read IOPS | Truy vấn index/page-ins có đủ khả năng phục vụ? |
| Random write IOPS | Updates, index modifications, journal/checkpoint có theo kịp? |
| Sequential throughput | Backup, restore, scan lớn, build index chạy ở tốc độ nào? |
| Read/write latency | I/O phải chờ bao lâu, đặc biệt p95/p99? |
| Queue depth | Request có xếp hàng kéo dài không? |
| Burst/credits | Cloud volume có chạy nhanh tạm thời rồi tụt sau khi hết credit? |
| Durability | Có chính sách replication/snapshot và lỗi disk phù hợp? |
| Filesystem/OS | Có cấu hình và khả năng fsync tương thích? |
| Tách workload | DB files, journal, backup/temp có tranh nhau một volume không? |

**NVMe SSD**, **network SSD** và **cloud block storage** có khả năng/giới hạn khác nhau. “1 TiB disk” là thông tin capacity, không đảm bảo số IOPS hoặc băng thông cụ thể.

### 3.2. IOPS và throughput khác nhau

Một workload đọc các khối 4 KiB:

\[
20\,000 \text{ IOPS} \times 4 \text{ KiB}
\approx 78.1 \text{ MiB/s}
\]

Một workload tuần tự đọc khối 1 MiB:

\[
200 \text{ IOPS} \times 1 \text{ MiB}
=200 \text{ MiB/s}
\]

Workload đầu **cần nhiều IOPS**; workload sau **cần nhiều throughput**. Cùng một volume có thể đạt giới hạn IOPS trước khi đạt giới hạn MiB/s hoặc ngược lại.

### 3.3. Latency và queue depth

Khi tốc độ yêu cầu I/O tới vượt tốc độ thiết bị xử lý, queue dài ra và latency có thể tăng nhanh.

```text
Arrival:    10,000 I/O requests/s
Capacity:    8,000 I/O requests/s
            ----------------------
Backlog:    +2,000 requests/s nếu kéo dài
```

Hàng đợi càng dài, các journal fsync và checkpoint writes càng có khả năng chờ. Tăng disk capacity không giải quyết bài toán này nếu IOPS quota không đổi.

Một quan hệ ước lượng theo Little's Law:

\[
L \approx \lambda W
\]

Trong đó `L` là số request trung bình trong hệ thống, `λ` throughput và `W` thời gian ở hệ thống. Đây là cách suy nghĩ về tương quan queue/latency, **không phải công thức tự suy ra latency MongoDB từ một chỉ số `iostat`**.

### 3.4. Đọc `iostat`

Trên Linux có `sysstat`:

```bash
iostat -xz 1 5
```

Cột thường gặp:

- `r/s`, `w/s`: read/write operations mỗi giây.
- `rkB/s`, `wkB/s`: throughput.
- `r_await`, `w_await`: thời gian trung bình của read/write I/O, gồm chờ queue theo semantics của công cụ.
- `aqu-sz`: độ sâu queue trung bình.
- `%util`: tỉ lệ thời gian thiết bị có I/O hoạt động theo cách kernel đo.

**Không đánh đồng `%util=100%` trên NVMe/cloud disk với “đã đạt toàn bộ IOPS tối đa”**. Storage song song có thể xử lý nhiều I/O một lúc; hãy đọc cùng latency, queue, throughput và giới hạn provisioned.

### 3.5. Dùng nhiều lớp telemetry

```text
API latency increased
           |
           v
MongoDB write latency increased?
           |
           +-- No  -> check app/network/pool/downstream
           |
           +-- Yes -> journal sync/checkpoint/eviction?
                         |
                         +-- OS disk await/queue up?
                         |         |
                         |         +-- Yes -> I/O pressure
                         |
                         +-- CPU/query/lock/replication?
```

Một snapshot CPU thấp không chứng minh thiết bị I/O khỏe. Ngược lại, disk latency thấp không loại trừ tắc vì CPU, lock, query plan hoặc flow control.

## 4. Journal là gì trong WiredTiger?

### 4.1. Write-ahead log để phục hồi sau crash

WiredTiger dùng **journal (write-ahead log)** kết hợp **checkpoint** để bảo vệ dữ liệu.

Khi một write thay đổi document và các indexes liên quan, storage engine tạo journal record mô tả thay đổi cần thiết. Các records được gom trong bộ đệm và ghi/sync xuống journal files theo các điều kiện cấu hình.

```text
Client update
      |
      v
Update page(s) / index(es) in cache
      |
      v
WiredTiger journal record(s)
      |
      +--> memory buffer
      |
      v
Journal write / sync
      |
      v
Durable journal on storage
      |
     ...
      |
      v
Later checkpoint persists data pages
```

Không diễn giải sơ đồ thành “mọi write được journal sync xong trước khi trả success”. **Thời điểm acknowledgement phụ thuộc write concern**, đặc biệt `j` và `w`.

### 4.2. Journal không phải diagnostic log

Tên dễ nhầm:

- `mongod.log`/container logs: **diagnostic log**, phục vụ quan sát vận hành.
- `WiredTigerLog.<sequence>` trong thư mục journal dưới `dbPath`: **write-ahead journal**, phục vụ durability/recovery.

Không tail/rotate/delete journal files bằng thao tác thủ công như log vận hành. Xóa/cắt journal có thể phá khả năng khôi phục sau crash.

### 4.3. Journaling luôn bật trên MongoDB hiện đại

Từ **MongoDB 6.1**, journaling luôn được bật theo tài liệu. Các tùy chọn cũ `storage.journal.enabled`, `--journal`, `--nojournal` đã bị loại bỏ.

Vì vậy, không đề xuất “tắt journal để tăng TPS” trên MongoDB 6.1+; vừa không được hỗ trợ, vừa đi ngược yêu cầu durability. Với hệ phiên bản cũ, vẫn không tùy tiện tắt journaling trên hệ có dữ liệu quan trọng.

### 4.4. Một journal record có thể bao gồm cả index updates

Ví dụ:

```javascript
db.orders.updateOne(
  { _id: orderId },
  { $set: { status: "PAID", updatedAt: new Date() } }
);
```

Nếu `status` và `updatedAt` có indexes, write có thể sửa cả document/index entries. Theo mô tả journaling của WiredTiger, journal record cho thao tác ghi do client khởi tạo có thể bao gồm các internal modifications liên quan.

Không dùng `modifiedCount=1` để suy ra đúng một disk write hoặc đúng một index entry được sửa.

## 5. Khi nào journal được sync?

### 5.1. Buffering và group commit

MongoDB cấu hình WiredTiger sử dụng bộ đệm journal. Thay vì mỗi thao tác ghi nhất thiết gây một physical fsync độc lập, engine có thể gom nhiều thay đổi để giảm chi phí.

Các điều kiện quan trọng theo tài liệu:

- Một write bao gồm hoặc hàm ý `j:true` sẽ yêu cầu journal sync tương ứng trên replica set member.
- Secondary có đồng bộ journal theo batch oplog application.
- Journal commit interval mặc định khoảng **100 ms**.
- Khi cần tạo journal file mới (giới hạn file khoảng **100 MB**).

Đây là **điều kiện kích hoạt theo thiết kế**, không phải bảo đảm “mọi write mất tối đa 100 ms” trên storage. Độ trễ thực còn phụ thuộc queue, fsync, workload và scheduler.

### 5.2. `storage.journal.commitIntervalMs`

Trên deployment self-managed/version có hỗ trợ:

```yaml
storage:
  journal:
    commitIntervalMs: 100
```

Theo tài liệu cấu hình hiện hành, đây là khoảng tối đa mặc định giữa các lần journal operation, có giới hạn theo phiên bản. Giảm khoảng này có thể tăng sync frequency và disk overhead; tăng khoảng này ảnh hưởng cửa sổ durability của writes không yêu cầu `j:true`.

**Không chỉnh `commitIntervalMs` theo phỏng đoán**, đặc biệt không đổi durability contract của ứng dụng chỉ vì có một spike latency.

### 5.3. `j:true` và `w:"majority"`

Ví dụ:

```javascript
db.orders.insertOne(
  {
    _id: new ObjectId(),
    status: "CREATED",
    createdAt: new Date()
  },
  {
    writeConcern: {
      w: "majority",
      j: true,
      wtimeout: 10000
    }
  }
);
```

Cần phân biệt:

- `w:1`: acknowledgment từ primary theo semantics của write concern.
- `w:"majority"`: acknowledgment khi đa số thành viên có điều kiện xác nhận cần thiết.
- `j:true`: yêu cầu journal durability theo semantics của deployment.
- `wtimeout`: giới hạn chờ write concern, không có nghĩa thao tác ghi chắc chắn được rollback nếu timeout.

Trong replica set, `w:"majority"` **hàm ý `j:true` nếu `writeConcernMajorityJournalDefault=true`** theo tài liệu. Không nói một cách tuyệt đối rằng majority luôn luôn đồng nghĩa journal durable bất kể cấu hình/phiên bản.

`j:true` **không thay thế `w:"majority"`** khi cần bảo vệ trước failover/replica acknowledgment. Ngược lại, write concern mạnh hơn có thể tăng độ trễ khi replica set hoặc disk bị quá tải.

### 5.4. Write concern timeout và unknown outcome

Nếu client nhận timeout:

```text
Client sends update
       |
MongoDB may have applied write
       |
Journal/replica acknowledgment delayed
       |
Client times out
```

Không tự coi “timeout” là “chưa có dữ liệu” rồi insert lặp bản ghi. Phải đối soát bằng khóa nghiệp vụ/idempotency key hoặc retryable writes khi đúng điều kiện. Đây vừa là vấn đề correctness vừa là điểm phát sinh duplicate workload khi storage chậm.

### 5.5. Bảo mật và an toàn journal

Journal có thể chứa dữ liệu nhạy cảm đã được lưu/ghi trong database. Cần áp dụng:

- Quyền OS đối với `dbPath`.
- Encryption at rest/volume encryption theo yêu cầu.
- Backup/snapshot policy và an toàn key.
- Không copy journal ra thư mục công khai để “debug”.
- Không xóa thủ công file `WiredTigerLog.*`.
- Bảo đảm đủ disk headroom: thiếu chỗ cho journal có thể làm MongoDB crash.

## 6. Checkpoint là gì?

### 6.1. Một điểm dữ liệu nhất quán trên disk

WiredTiger tạo **checkpoint** nhằm đưa một snapshot nhất quán của data files xuống lưu trữ, để có thể khôi phục từ trạng thái hợp lệ đó.

Sơ đồ:

```text
Memory / cache has latest changes
                |
                v
        WiredTiger checkpoint
                |
        write dirty data pages
                |
                v
     data files at consistent state
                |
                v
        checkpoint metadata
     references new valid checkpoint
```

WiredTiger có cơ chế để **checkpoint cũ vẫn hợp lệ trong khi checkpoint mới đang được ghi**. Khi metadata được cập nhật nguyên tử để trỏ đến checkpoint mới, checkpoint đó trở thành trạng thái có thể dùng cho recovery.

### 6.2. Chu kỳ checkpoint thông thường

Theo tài liệu WiredTiger, MongoDB cấu hình tạo checkpoint ở khoảng **60 giây**. Không hiểu con số này như lời hứa mỗi checkpoint hoàn tất đúng 60 giây; thời gian thực hiện phụ thuộc dirty pages, device và workload.

Khi tải lớn, checkpoint có thể gây burst I/O. Nhưng **thấy disk writes tăng quanh checkpoint chưa tự chứng minh lỗi** — cần đo latency, queue, thời gian checkpoint và ảnh hưởng ứng dụng.

### 6.3. Journal + checkpoint khi khởi động lại

Giả sử:

```text
T0: checkpoint A hoàn tất
T1: write X, journal đã durable
T2: write Y, journal đã durable
T3: process crash trước checkpoint B
T4: mongod khởi động lại
```

Quy trình khôi phục khái niệm:

1. Đọc thông tin checkpoint cuối cùng hợp lệ.
2. Xác định các journal records sau checkpoint đó.
3. Replay những thay đổi cần thiết.
4. Tái lập trạng thái dữ liệu bền vững theo contract.

Vì vậy **checkpoint không phải điều kiện bắt buộc để mỗi write `j:true` trở nên durable**; journal được dùng để bảo vệ khoảng giữa các checkpoints.

### 6.4. Checkpoint không phải snapshot backup độc lập

Một checkpoint là một cấu phần **nội bộ storage engine**. Không copy tùy tiện các file `.wt` đang mở tại một thời điểm rồi gọi đó là backup hợp lệ.

Backup cần:

- Quy trình MongoDB/Atlas/snapshot được hỗ trợ.
- Nhất quán data, indexes và metadata.
- Oplog/PITR khi cần.
- Đối chiếu replica state/FCV/topology.
- Kế hoạch khôi phục được thử nghiệm.

**Journal + checkpoint không thay thế backup** và không giúp bạn phục hồi khi người dùng xóa collection hợp lệ rồi dữ liệu xóa cũng được journal/checkpoint.

### 6.5. History store và transaction dài

WiredTiger sử dụng MVCC và snapshot history. Đọc/transaction dài có thể kéo dài thời gian giữ các phiên bản cũ, khiến history store, cache và I/O tăng.

Tài liệu mô tả `minSnapshotHistoryWindowInSeconds` ảnh hưởng mức độ giữ snapshot history và `WiredTigerHS.wt`. Không tự mở rộng history window để “sửa slow reads” nếu chưa hiểu storage impact.

## 7. Journal, checkpoint, eviction và cache liên hệ thế nào?

```text
             MongoDB writes
                   |
                   v
        WiredTiger dirty pages
                   |
         +---------+---------+
         |                   |
         v                   v
    Journal records     Checkpoint / eviction
         |                   |
  journal flush/fsync     data page writes
         |                   |
         +---------+---------+
                   |
                   v
          Same storage subsystem
                   |
                   v
         IOPS, latency, queue
```

### 7.1. Dirty cache pressure

Khi tốc độ updates lớn, dirty bytes tăng. Nếu storage write performance không theo kịp, checkpoint/eviction cần nhiều thời gian hơn, application threads có thể tham gia eviction hoặc phải chờ cache space.

Tuy nhiên, một tỉ lệ dirty cache cao **không tự đồng nghĩa journal chưa durable**; journal durability và dirty pages là hai cơ chế khác nhau.

### 7.2. Khi checkpoint trông giống nguyên nhân nhưng không phải root cause

Tình huống:

```text
13:00 bulk import starts
13:01 dirty bytes rise
13:02 checkpoint duration rises
13:02 disk write latency rises
13:02 API p95 increases
```

Có thể nguyên nhân thật là **bulk import đẩy writes vượt IOPS**, còn checkpoint duration là một hệ quả. Chỉ thay checkpoint interval chưa giải quyết giới hạn thiết bị.

### 7.3. Vì sao tăng cache chưa chắc có ích?

Tăng cache có thể giữ nhiều pages hơn, nhưng:

- Không tăng throughput/IOPS vật lý.
- Có thể lấy RAM từ OS filesystem cache.
- Có thể gây OOM trong container.
- Không xử lý long-running transactions pinning.
- Có thể trì hoãn thay vì loại bỏ burst I/O.

Cần chứng minh root cause trước khi điều chỉnh `storage.wiredTiger.engineConfig.cacheSizeGB` hoặc `cacheSizePct`.

## 8. Đọc journal metrics từ `serverStatus()`

Trên server dùng WiredTiger:

```javascript
const s = db.serverStatus();
const log = s.wiredTiger?.log || {};

printjson({
  uptime: s.uptime,
  logBytesWritten: log["log bytes written"],
  logPayloadBytes: log["log bytes of payload data"],
  logWriteOperations: log["log write operations"],
  logSyncOperations: log["log sync operations"],
  logSyncDurationUs: log["log sync time duration (usecs)"],
  recordsCompressed: log["log records compressed"],
  recordsNotCompressed: log["log records not compressed"],
  recordsTooSmall:
    log["log records too small to compress"]
});
```

Các keys trong `wiredTiger.log` là **statistics của storage engine**, có thể khác/thiếu theo release. Một số managed tiers hạn chế `serverStatus`.

### 8.1. Cách hiểu các chỉ số

| Metric | Cách đọc |
| --- | --- |
| `log bytes written` | Tổng bytes journal được ghi theo metric của engine |
| `log bytes of payload data` | Payload bytes được thống kê riêng |
| `log write operations` | Số operations ghi journal, thường là counter |
| `log sync operations` | Số lần đồng bộ journal được theo dõi |
| `log sync time duration (usecs)` | Tổng thời gian sync, microseconds |
| `log records compressed` | Số records được nén |
| `log records too small to compress` | Records quá nhỏ so với giới hạn compressor |

**Không** suy ra `logBytesWritten = kích thước hiện tại của thư mục journal`: đây là counter tích lũy, còn journal files được tạo/thu hồi theo quá trình recovery/checkpoint.

### 8.2. Đo tốc độ journal bằng delta

\[
\text{Journal bytes/s}
=
\frac{B_2-B_1}{t_2-t_1}
\]

\[
\text{Journal sync/s}
=
\frac{S_2-S_1}{t_2-t_1}
\]

Đối với tổng thời gian sync `T` và số sync `S`:

\[
\text{Mean sync time over interval}
\approx
\frac{T_2-T_1}{S_2-S_1}
\]

Công thức trên chỉ hợp lệ khi samples đến từ **cùng một process**, counters không reset và mẫu số >0. Đây là average của các syncs được metric đếm, **không phải p95 fsync latency**.

### 8.3. Ví dụ tính hai samples có kiểm tra reset

```javascript
function journalSample() {
  const s = db.serverStatus();
  const log = s.wiredTiger?.log || {};

  return {
    at: Date.now(),
    uptime: s.uptime,
    bytes: log["log bytes written"],
    syncs: log["log sync operations"],
    syncTimeUs: log["log sync time duration (usecs)"]
  };
}

function safeNumber(value) {
  if (value == null) return null;
  const n = Number(value);
  return Number.isFinite(n) &&
    Number.isSafeInteger(n) ? n : null;
}

function rate(v1, v2, elapsedSec) {
  const a = safeNumber(v1);
  const b = safeNumber(v2);
  if (a == null || b == null ||
      b < a || elapsedSec <= 0) return null;
  return (b - a) / elapsedSec;
}

const first = journalSample();
sleep(5000);
const second = journalSample();
const seconds = (second.at - first.at) / 1000;

if (second.uptime <= first.uptime) {
  print("Uptime không tăng: bỏ phép đo nếu có restart.");
} else {
  const bytesPerSec =
    rate(first.bytes, second.bytes, seconds);
  const syncsPerSec =
    rate(first.syncs, second.syncs, seconds);

  printjson({
    elapsedSec: seconds,
    journalBytesPerSec: bytesPerSec,
    journalSyncsPerSec: syncsPerSec,
    averageJournalSyncMs:
      syncsPerSec > 0
        ? (rate(first.syncTimeUs,
                second.syncTimeUs,
                seconds) / syncsPerSec) / 1000
        : null
  });
}
```

Đây là **ví dụ thu thập kỹ thuật**. Trong production nên dùng telemetry agent/time-series, xử lý reset/overflow với kiểu số thích hợp và xác nhận instance identity. Không coi `Number()` an toàn cho mọi counter 64-bit; helper trên trả null nếu vượt safe integer.

## 9. Đọc checkpoint metrics từ WiredTiger

Tài liệu `serverStatus` cung cấp nhiều metrics trong `wiredTiger.checkpoint` và `wiredTiger.transaction` theo phiên bản.

```javascript
const s = db.serverStatus();

printjson({
  checkpoint: s.wiredTiger?.checkpoint,
  selectedTransactionCheckpoint: {
    checkpoints:
      s.wiredTiger?.transaction?.[
        "transaction checkpoints"
      ],
    recentMs:
      s.wiredTiger?.transaction?.[
        "transaction checkpoint most recent time (msecs)"
      ],
    totalMs:
      s.wiredTiger?.transaction?.[
        "transaction checkpoint total time (msecs)"
      ]
  }
});
```

Không giả định toàn bộ các fields tồn tại ở mọi bản. Khi `checkpoint` có:

- `most recent time (msecs)`: thời gian checkpoint gần nhất theo thống kê.
- `max time (msecs)`: checkpoint dài nhất được ghi nhận.
- `total time (msecs)`: thời gian tích lũy.
- `total succeed number of checkpoints`: counter checkpoints thành công.
- `total failed number of checkpoints`: counter checkpoints thất bại.
- `bytes written for checkpoint` trong `block-manager`/`capacity`: dấu hiệu throughput liên quan, khi có.

### 9.1. Làm sao đánh giá checkpoint kéo dài?

Một lần checkpoint 3 giây chưa tự là lỗi. Nếu trong giờ bình thường recent time 0.8 giây, giờ cao điểm tăng lên 35 giây cùng lúc disk write latency/queue và API p99 tăng thì đây là tín hiệu cần điều tra.

Xem thêm:

- Dirty cache bytes.
- Disk write latency/IOPS/throughput.
- Journal sync duration.
- Index build/bulk import.
- Long-running transactions/snapshot history.
- Replication lag và write concern.
- Cloud volume burst quota.

### 9.2. Những điều không nên làm

- Không xóa checkpoint/WiredTiger metadata files.
- Không chỉnh sửa thủ công `WiredTiger.wt` hoặc `WiredTigerHS.wt`.
- Không restart primary lặp lại vì thấy checkpoint dài.
- Không thay checkpoint scheduling khi chưa có tài liệu và benchmark.
- Không cho rằng checkpoint nhanh nghĩa journal fsync cũng nhanh.

## 10. Cấu hình nén: ba lớp hoàn toàn khác nhau

WiredTiger có **ba nhóm nén**, và mỗi nhóm giải quyết loại dữ liệu khác nhau.

| Nhóm | Cấu hình | Đối tượng được nén | Mặc định thường gặp |
| --- | --- | --- | --- |
| Collection block | `storage.wiredTiger.collectionConfig.blockCompressor` | Các blocks dữ liệu của collections | `snappy` với đa số collections; **time-series mặc định zstd** |
| Journal | `storage.wiredTiger.engineConfig.journalCompressor` | Journal records | `snappy` |
| Index prefix | `storage.wiredTiger.indexConfig.prefixCompression` | Những prefix chung trong index keys | `true` |

**Không lẫn với network compression** của MongoDB wire protocol (`compressors` trong driver/server), là tính năng riêng cho dữ liệu **truyền qua mạng**.

### 10.1. Collection block compression

WiredTiger nén các blocks trên đĩa. Các giá trị cấu hình được tài liệu liệt kê:

- `none`: không nén blocks.
- `snappy`: ưu tiên tốc độ và CPU nhẹ tương đối.
- `zlib`: thường nén chặt hơn nhưng CPU cost cao hơn.
- `zstd`: thường cân bằng compression ratio và tốc độ tốt, tùy level và corpus.

**Không có compressor tốt nhất cho mọi workload**. Ví dụ một service CPU-bound có thể chịu thiệt nếu đổi sang thuật toán/level tốn CPU, dù disk bytes giảm.

### 10.2. Journal compression

Cấu hình journal độc lập với collection compression:

```yaml
storage:
  wiredTiger:
    engineConfig:
      journalCompressor: snappy
```

Các lựa chọn: `none`, `snappy`, `zlib`, `zstd`. Journal compressor ảnh hưởng records trong write-ahead log, **không đổi cách mã hóa các data blocks đã ghi trong collections**.

Theo tài liệu, WiredTiger không nén những journal record có kích thước **≤128 bytes**. Vì vậy tỉ lệ nén journal không chỉ phụ thuộc thuật toán, mà còn phụ thuộc kích thước record/workload.

### 10.3. Index prefix compression

Indexes dạng B-tree có thể chứa keys với prefix giống nhau:

```text
customer:0000001
customer:0000002
customer:0000003
customer:0000004
```

Thay vì lặp toàn bộ prefix trong các keys được lưu, prefix compression giúp giảm storage. Đây không phải thuật toán `snappy/zlib/zstd` cho index keys; nó là một kỹ thuật **nén tiền tố**.

MongoDB thường bật `prefixCompression:true` mặc định. Nếu index keys có prefix lặp, tiết kiệm có thể đáng kể. Nếu keys ngẫu nhiên/khác hoàn toàn, lợi ích ít hơn.

Không tắt prefix compression mặc định chỉ vì muốn “giảm CPU” mà chưa có benchmark; nhiều workload được lợi từ lượng disk/cache nhỏ hơn.

## 11. So sánh Snappy, zlib, zstd và none

| Thuật toán | Ưu điểm thường gặp | Đánh đổi | Khi đáng thử |
| --- | --- | --- | --- |
| `snappy` | Nén/giải nén nhanh, CPU tương đối nhẹ | Ratio có thể thấp hơn zlib/zstd | OLTP latency-sensitive; lựa chọn nền |
| `zstd` | Ratio tốt, hiệu năng thường cân bằng; có levels tùy phiên bản | Compression level cao có thể tiêu CPU | Dataset lớn, disk/storage quan trọng, CPU còn headroom |
| `zlib` | Có thể nén tốt với dữ liệu phù hợp | CPU/time nén thường cao hơn snappy | Archive-ish workload hoặc corpus rất nén được, phải đo |
| `none` | Loại bỏ chi phí CPU nén của lớp đó | Tốn disk/I/O, page cache kém hiệu quả hơn | Data đã nén hoặc CPU rất hạn chế, cần benchmark |

**Bảng này mô tả xu hướng, không phải cam kết thứ hạng tốc độ trong mọi environment.** Actual outcomes phụ thuộc dữ liệu, size, compression level, cache, read/write mix, CPU instruction set và disk IOPS.

### 11.1. Dữ liệu nào nén tốt?

Ví dụ nhiều document có keys và status lặp:

```javascript
{
  tenantId: "demo-tenant",
  category: "BOOK",
  status: "ACTIVE",
  description:
    "Tài liệu mô phỏng có nhiều cấu trúc lặp để đo nén"
}
```

Dữ liệu lặp/chuỗi dài thường nén tốt hơn bytes có entropy cao.

### 11.2. Dữ liệu nào nén kém?

- JPEG/PNG/video đã nén.
- ZIP/gzip.
- Ciphertext được mã hóa tốt.
- Dữ liệu ngẫu nhiên/entropy cao.
- Payload đã được ứng dụng nén.

Không bật zstd level cao trên dữ liệu đã nén rồi giả định sẽ tiết kiệm 50% nữa; có thể chỉ tăng CPU.

### 11.3. Nén ảnh hưởng RAM và I/O theo hai cách

```text
Compressed blocks on disk
              |
         OS page cache
       (compressed bytes)
              |
        WiredTiger reads
              |
           Decompress
              |
       WiredTiger cache
       (working pages)
```

Nén giảm lượng bytes trên disk và thường giúp filesystem cache chứa nhiều compressed blocks. Nhưng WiredTiger internal cache lưu các page representations dùng trong bộ nhớ, không nên giả định toàn bộ internal cache giảm đúng bằng compression ratio trên disk.

### 11.4. Khi nào nén mạnh hơn làm chậm query?

Nếu workload:

- đã nằm trong cache;
- CPU-bound vì query computation;
- thường xuyên ghi/cập nhật pages;
- cần p99 rất thấp;

thì việc giảm disk size có thể không bù được CPU compression/decompression cost.

Ngược lại, với workload I/O-bound, compressor mạnh hơn có thể **giảm số physical reads/writes**, giúp latency cải thiện dù CPU tăng. Kết luận phải dựa trên đo.

## 12. Cấu hình WiredTiger trên self-managed MongoDB

### 12.1. Mẫu YAML tham khảo

Ví dụ trên **môi trường lab self-managed**, không phải khuyến nghị thay đổi production ngay:

```yaml
storage:
  wiredTiger:
    engineConfig:
      journalCompressor: snappy
    collectionConfig:
      blockCompressor: snappy
    indexConfig:
      prefixCompression: true
```

Đây gần các lựa chọn mặc định được tài liệu mô tả cho collections thông thường, journal và indexes. Time-series có quy tắc default nén khác.

### 12.2. Một cấu hình thử nghiệm Zstd

```yaml
storage:
  wiredTiger:
    engineConfig:
      journalCompressor: zstd
      zstdCompressionLevel: 6
    collectionConfig:
      blockCompressor: zstd
    indexConfig:
      prefixCompression: true
```

Đây là cấu hình **thử nghiệm**, không phải “best practice” chung. Nếu đổi cả journal và collection compressor cùng lúc, sẽ **khó quy tác động** cho từng thay đổi; benchmark nên thay **một biến ở mỗi lần thử**.

MongoDB 8.2 thay đổi dải `zstdCompressionLevel`, cho phép giá trị từ -7 đến 22; MongoDB 8.0 có dải 1–22. Không copy giá trị âm sang phiên bản không hỗ trợ. Giá trị `0` có semantics đặc biệt trong tài liệu hiện hành (dùng default của zstd library, có thể khác MongoDB default).

### 12.3. Thay đổi default có tác dụng trên đối tượng mới

Tài liệu MongoDB nêu:

- Thay `storage.wiredTiger.collectionConfig.blockCompressor` trên deployment hiện hữu: **collections mới** sử dụng default mới; **collections cũ giữ compressor đã dùng khi tạo**.
- Thay `storage.wiredTiger.indexConfig.prefixCompression`: **indexes mới** dùng default mới; existing indexes không tự chuyển đổi.

Vì vậy không thể kết luận “đổi YAML từ snappy sang zstd nên toàn bộ 3 TiB dữ liệu cũ tự được nén lại thành zstd”.

Nếu muốn thay đổi nén của dữ liệu đã tồn tại, cần kế hoạch tạo collection/index mới hoặc workflow migrate/rebuild được MongoDB hỗ trợ, đo chi phí và đảm bảo nhất quán dữ liệu. Không chạy `collMod` hoặc `compact` tùy tiện rồi tin chắc toàn bộ data blocks đã đổi algorithm.

### 12.4. Cấu hình collection riêng khi tạo

Trên MongoDB self-managed và phiên bản hỗ trợ tùy chọn storage engine:

```javascript
const lab = db.getSiblingDB("mongo_perf_row370_lab");

lab.runCommand({
  create: "zstd_example",
  storageEngine: {
    wiredTiger: {
      configString: "block_compressor=zstd"
    }
  }
});
```

Tùy deployment managed hoặc permissions, command có thể bị từ chối; không dùng quyền production để vượt restrictions của dịch vụ. Collection-specific option được lưu ở metadata lúc tạo, không phải tự động áp cho collections hiện hữu.

**Chỉ tạo `zstd_example` khi chắc chắn namespace chưa tồn tại và được phép thử.** Trong lab đầy đủ ở phần sau sẽ dùng tên duy nhất để tránh trùng.

### 12.5. Per-index prefixCompression

WiredTiger có khả năng cấu hình index riêng trong một số lệnh/index options được server hỗ trợ. Nhưng thay đổi trên một index existing phải theo quy trình rebuild hợp lệ nếu cần; đừng edit index metadata hoặc system collections.

Với indexes quan trọng, benchmark việc tắt/bật prefix compression sau khi tách bạch thay đổi query plan/index key pattern. Chỉ bật/tắt theo giả thuyết có số liệu.

## 13. Đọc cấu hình thực tế, không suy ra từ file YAML cũ

### 13.1. `getCmdLineOpts`

Trên self-managed `mongod` có quyền phù hợp:

```javascript
const result = db.adminCommand({
  getCmdLineOpts: 1
});

printjson({
  parsed: result.parsed?.storage?.wiredTiger,
  journal: result.parsed?.storage?.journal
});
```

Command phản ánh các tùy chọn đã parse từ startup config; **không có field được liệt kê** không có nghĩa option không tồn tại — có thể server dùng default. Managed service có thể hạn chế command.

### 13.2. Xem metadata của collection

```javascript
const info = db.getCollectionInfos({
  name: "orders"
});

printjson(
  info.map((x) => ({
    name: x.name,
    options: x.options,
    type: x.type
  }))
);
```

Nếu collection được tạo với `storageEngine.wiredTiger.configString`, thông tin có thể xuất hiện ở options theo version. Tuy nhiên không phải mọi version/API trả compressor thực tế dưới dạng dễ đọc chỉ qua `getCollectionInfos`. Kết hợp `collStats`, collection metadata và thông tin quản trị theo tài liệu.

### 13.3. Không dùng raw file edits

Tuyệt đối không sửa thủ công:

```text
dbPath/WiredTiger.wt
dbPath/WiredTiger.turtle
dbPath/collection-*.wt
dbPath/index-*.wt
dbPath/journal/WiredTigerLog.*
```

Điều này có thể phá checkpoint recovery và làm dữ liệu không mở được. Cấu hình được áp dụng qua interface quản trị được hỗ trợ, có backup và maintenance plan.

## 14. Đo storage usage và tỉ lệ nén

### 14.1. `dbStats`

```javascript
const s = db.runCommand({
  dbStats: 1
});

printjson({
  db: s.db,
  objects: s.objects,
  dataSize: s.dataSize,
  storageSize: s.storageSize,
  indexSize: s.indexSize,
  totalSize: s.totalSize,
  fsUsedSize: s.fsUsedSize,
  fsTotalSize: s.fsTotalSize
});
```

Trên collection riêng:

```javascript
const s = db.runCommand({
  collStats: "orders"
});

printjson({
  count: s.count,
  size: s.size,
  storageSize: s.storageSize,
  totalIndexSize: s.totalIndexSize,
  wiredTiger: s.wiredTiger ? "[statistics available]" : null
});
```

Công cụ quản lý có thể dùng `$collStats` hoặc methods tương đương theo version. `collStats` có thể bị giới hạn trong một số môi trường managed; kiểm tra quyền và API compatibility.

### 14.2. Một tỷ lệ chỉ có ý nghĩa tương đối

Đối với cùng một collection/snapshot:

\[
\text{Approx. logical/storage ratio}
=
\frac{\text{size}}{\text{storageSize}}
\]

Ví dụ:

```text
Collection logical size: 100 MiB
Collection storageSize:   40 MiB
Ratio:                   2.5
```

Tuy nhiên đây **không phải benchmark compressor thuần** vì:

- Page fragmentation và allocated free space.
- Index bytes không nằm trong `storageSize`.
- Không cùng số documents/hình dạng field.
- Nén các block phụ thuộc thứ tự insert/update.
- Background checkpoint/write activity.
- Chưa loại trừ metadata và time-series semantics.

Vì vậy dùng “ratio” để **so xu hướng trên dataset chuẩn hóa**, không dùng nó làm số đo bất biến hoặc cam kết dự báo chi phí.

### 14.3. Đọc free storage với tần suất hợp lý

Một số phiên bản hỗ trợ:

```javascript
db.runCommand({
  dbStats: 1,
  freeStorage: 1
});
```

Thống kê freeStorage có thể tốn I/O/CPU; không gọi dày đặc trên database lớn chỉ để vẽ dashboard từng giây. Nếu monitoring service đã có metric thích hợp, ưu tiên metric đã được thu thập.

## 15. Benchmark nén công bằng: nguyên tắc thiết kế

### 15.1. Câu hỏi đúng trước khi thử

Không hỏi “Zstd có nhanh hơn Snappy không?” mà nên hỏi:

> “Với tập documents và query distribution của hệ thống, việc dùng zstd thay snappy có giảm chi phí disk và cải thiện p95 mà không vượt CPU SLO, write latency và storage budget hay không?”

Định nghĩa tiêu chí:

- Dataset: số lượng, cấu trúc, entropy, kích thước BSON.
- Read/write mix: 90/10 hay 10/90.
- Query patterns: point lookup, range scan, aggregation.
- Indexes giống nhau.
- Compression level, index prefix compression, journal settings.
- Hardware: CPU cores, RAM, storage type, IOPS, throughput.
- Concurrency: số clients/threads, connection pooling.
- Độ dài run, warm-up, cold/warm cache.
- Lỗi/throttle/replication/failover.
- Metrics: p50/p95/p99, throughput, CPU, disk, storageSize.

### 15.2. Đừng thay nhiều biến

Không so:

```text
A: snappy, 8 GiB RAM, HDD, không index
B: zstd, 32 GiB RAM, NVMe, có index
```

và kết luận “zstd nhanh gấp 10”. Cần kiểm soát biến và chạy nhiều lần để tránh nhiễu warm cache, compaction và noisy neighbors.

### 15.3. Tách hai bài đo

**Storage compression experiment:**

- Insert cùng tập document.
- Cùng index, cùng storage layout.
- Đợi trạng thái ổn định thích hợp.
- Đo storageSize, indexSize, raw dataset size.
- So CPU/bytes processed khi insert.

**Application performance experiment:**

- Run read/write queries đại diện.
- Cùng concurrency và dataset.
- So QPS, p95/p99, errors.
- So disk IOPS/await/queue.
- So journal/checkpoint metrics và replication lag.

Một compressor “nén tốt” có thể không giúp ứng dụng nhanh hơn nếu bottleneck ở CPU/query.

### 15.4. Đo tác động tới checkpoint/journal

Nếu thay block compressor, phải đo **checkpoint/data file writes** riêng tương đối với journal. Nếu thay journal compressor, phải đo **journal write/sync bytes/time** và durability latency.

Nén blocks mạnh hơn không nhất thiết giảm số journal sync calls. Journal compression khác collection block compression; giữ hai thử nghiệm riêng để có thể diễn giải.

## 16. Lab mongosh nhỏ: so cấu hình Snappy và Zstd

### 16.1. Điều kiện và phạm vi

Lab này chỉ chạy trên **MongoDB self-managed test deployment hỗ trợ `storageEngine.wiredTiger.configString`**, với quyền tạo collection. Nếu Atlas/managed không cho phép collection-specific storage options, **bỏ qua phần tạo collections nén riêng**, vẫn học cách đo `serverStatus` và `dbStats`.

Không:

- Đổi startup YAML của production.
- Restart `mongod`.
- Tắt journal hoặc xóa journal files.
- Tạo vài GB dữ liệu để cố gây I/O pressure.
- Đụng namespace ngoài lab.
- Chạy lệnh `dropDatabase()` trên database dùng chung.

### 16.2. Tạo tên collection riêng cho lượt thử

```javascript
const lab = db.getSiblingDB("mongo_perf_row370_lab");
const runId = "row370-" + new ObjectId().toHexString();

const collSnappyName =
  "sample_snappy_" + runId.replace(/-/g, "_");
const collZstdName =
  "sample_zstd_" + runId.replace(/-/g, "_");

if (lab.getCollectionNames().includes(collSnappyName) ||
    lab.getCollectionNames().includes(collZstdName)) {
  throw new Error("Namespace trùng; không ghi đè.");
}

printjson({
  database: lab.getName(),
  runId,
  collSnappyName,
  collZstdName
});
```

### 16.3. Tạo collections với compressor khác nhau

```javascript
const snappyResult = lab.runCommand({
  create: collSnappyName,
  storageEngine: {
    wiredTiger: {
      configString: "block_compressor=snappy"
    }
  }
});

const zstdResult = lab.runCommand({
  create: collZstdName,
  storageEngine: {
    wiredTiger: {
      configString: "block_compressor=zstd"
    }
  }
});

printjson({ snappyResult, zstdResult });

if (!snappyResult.ok || !zstdResult.ok) {
  throw new Error(
    "Thiếu hỗ trợ/permission: dừng lab, không thử trên prod."
  );
}

const snappy = lab.getCollection(collSnappyName);
const zstd = lab.getCollection(collZstdName);
```

Nếu lệnh `create` lỗi ở một môi trường, không tự chạy `drop()` để “làm lại sạch”. Trước hết xác nhận namespace nào đã được tạo và quyền sở hữu. Không tiến hành insert nếu không có đủ hai collections.

### 16.4. Dữ liệu có cấu trúc lặp nhưng vẫn khác nhau

```javascript
const template =
  "Tài liệu demo có nội dung lặp để so sánh block " +
  "compression trên tập dữ liệu MongoDB; không chứa PII. ";

const docs = Array.from({ length: 1500 }, (_, i) => ({
  _id: new ObjectId(),
  runId,
  code: "ROW370-" + String(i).padStart(5, "0"),
  category: "demo-" + (i % 7),
  status: i % 4 === 0 ? "INACTIVE" : "ACTIVE",
  value: i * 17,
  description: template.repeat(12),
  tags: ["mongodb", "wiredtiger", "compression"],
  createdAt: new Date("2026-11-14T00:00:00Z")
}));

const snappyWrite = snappy.insertMany(docs);
const zstdWrite = zstd.insertMany(docs);

printjson({
  runId,
  snappyInserted: Object.keys(snappyWrite.insertedIds).length,
  zstdInserted: Object.keys(zstdWrite.insertedIds).length
});
```

Hai collections dùng **cùng document IDs và nội dung**, nhưng đây không phải benchmark production. Corpus được thiết kế nén tốt; với JSON/BSON ít lặp, dữ liệu nén sẵn hoặc ciphertext, kết quả sẽ khác.

### 16.5. Tạo cùng index trên cả hai collections

```javascript
for (const coll of [snappy, zstd]) {
  coll.createIndex(
    { runId: 1, category: 1, value: -1 },
    { name: "run_category_value" }
  );
}
```

Bởi index giống nhau, so sánh data storage sẽ bớt sai lệch. Tuy vậy index bytes vẫn cần thống kê riêng, và vị trí trên disk/cache/fragmentation không hoàn toàn đồng nhất.

### 16.6. Đọc thống kê hai collections

```javascript
function storageSummary(name) {
  const stats = lab.runCommand({
    collStats: name
  });

  return {
    collection: name,
    count: stats.count,
    logicalBytes: stats.size,
    storageBytes: stats.storageSize,
    indexBytes: stats.totalIndexSize,
    approximateLogicalStorageRatio:
      Number(stats.storageSize) > 0
        ? Number(stats.size) / Number(stats.storageSize)
        : null
  };
}

printjson([
  storageSummary(collSnappyName),
  storageSummary(collZstdName)
]);
```

Lưu ý:

- Một sample 1500 documents quá nhỏ để suy ra p99 production.
- Storage allocation có kích thước block/overhead; tỉ lệ trên tập nhỏ rất dễ nhiễu.
- Không so raw result với collection production có workload update khác.
- Tốt nhất chạy nhiều lần trên staging có dataset đủ đại diện và ổn định.

### 16.7. Query so sánh đơn giản

```javascript
const filter = {
  runId,
  category: "demo-3"
};

for (const coll of [snappy, zstd]) {
  const result = coll.find(filter)
    .sort({ value: -1 })
    .limit(10)
    .explain("executionStats");

  printjson({
    collection: coll.getName(),
    nReturned: result.executionStats?.nReturned,
    docsExamined:
      result.executionStats?.totalDocsExamined,
    keysExamined:
      result.executionStats?.totalKeysExamined,
    executionTimeMillis:
      result.executionStats?.executionTimeMillis
  });
}
```

**Không dùng một lần `explain()` làm chứng minh compressor nào nhanh hơn.** Query 1500 documents chủ yếu minh họa cách đọc index/query stats.

### 16.8. Dọn dữ liệu demo theo `runId` và `_id`

Trước khi xóa:

```javascript
print("database=" + lab.getName());
print("runId=" + runId);
print("collections=" + collSnappyName + ", " + collZstdName);

for (const coll of [snappy, zstd]) {
  printjson({
    collection: coll.getName(),
    ownedCount: coll.countDocuments({ runId })
  });
}
```

Nếu đã xác nhận đúng hai collections và đúng runId của mình:

```javascript
for (const coll of [snappy, zstd]) {
  const ownIds = coll.find(
    { runId },
    { _id: 1, runId: 1 }
  ).toArray();

  for (const item of ownIds) {
    coll.deleteOne({
      _id: item._id,
      runId
    });
  }

  printjson({
    collection: coll.getName(),
    remainingOwnedDocs: coll.countDocuments({ runId })
  });
}
```

Các collections/indexes có thể còn lại sau khi xóa documents. Trên lab riêng, người có quyền quản trị có thể thu hồi đúng namespaces **sau khi xác minh owner**, nhưng không dùng `dropDatabase()` hay xóa mọi collection trong một database có thể chia sẻ.

**Lưu ý:** Xóa dữ liệu ở hai collections sẽ làm mất corpus để benchmark thêm. Nếu muốn đo khác biệt sau warm-up/checkpoint, hoàn tất measurements trước khi cleanup.

## 17. Giám sát tổng thể cho ổ đĩa, journal và checkpoint

### 17.1. Một dashboard hữu dụng

```text
+-----------------------------+----------------------------+
| API write p95 / p99         | MongoDB write latency      |
+-----------------------------+----------------------------+
| Host CPU / process CPU      | Read/write IOPS            |
+-----------------------------+----------------------------+
| Disk throughput MiB/s       | Disk r_await / w_await     |
+-----------------------------+----------------------------+
| Disk queue / burst credits  | Disk free + growth         |
+-----------------------------+----------------------------+
| WT dirty bytes / cache max  | WT page in / eviction      |
+-----------------------------+----------------------------+
| WT journal bytes/s          | WT journal sync time       |
+-----------------------------+----------------------------+
| Checkpoint duration         | Checkpoint write bytes/s   |
+-----------------------------+----------------------------+
| Replication lag             | Flow control/commit delay  |
+-----------------------------+----------------------------+
```

Nếu dùng Atlas, Metric names và availability có thể khác với `serverStatus` trên self-managed. Không tự đặt tên một field `checkpointP99` rồi giả định Atlas có sẵn.

### 17.2. Các metric tự xuất ở application/monitoring

Ví dụ tên **đề xuất** (không phải tiêu chuẩn MongoDB):

```text
mongo_disk_read_iops
mongo_disk_write_iops
mongo_disk_read_latency_seconds
mongo_disk_write_latency_seconds
mongo_disk_queue_depth
mongo_disk_free_bytes
mongo_wt_dirty_cache_ratio
mongo_wt_journal_bytes_per_second
mongo_wt_journal_syncs_per_second
mongo_wt_journal_sync_avg_seconds
mongo_wt_checkpoint_duration_seconds
mongo_app_write_latency_seconds
mongo_replication_lag_seconds
mongo_storage_compression_config_info
```

Đối với counters tích lũy, nên expose raw counter và tính rate trong hệ thống time-series, xử lý restart.

### 17.3. Alert nên dựa trên nhiều tín hiệu

| Alert | Kết hợp dấu hiệu |
| --- | --- |
| Storage write pressure | `w_await`/queue tăng, gần IOPS quota, API write latency tăng |
| Journal fsync pressure | Sync time/sync count tăng, write concern p95 tăng, device latency tăng |
| Checkpoint pressure | Recent/max checkpoint time tăng, dirty bytes và disk writes tăng |
| Disk full risk | Free bytes thấp + tốc độ tăng + journal/oplog headroom không đủ |
| Compression CPU pressure | CPU tăng sau đổi compressor + throughput/query p99 giảm |
| Unexpected storage growth | storageSize/indexSize/journal/oplog tăng vượt baseline |
| Replication I/O bottleneck | Secondary disk latency tăng + replication lag/majority latency tăng |

Tỉ lệ cache dirty, checkpoint time hoặc journal bytes/s cao một mình không đủ kết luận root cause.

## 18. Các kịch bản điều tra thực tế

### 18.1. Kịch bản A — Write p99 tăng, journal sync chậm

```text
API write p99: 50 -> 600 ms
Journal sync avg: tăng 8 lần
Disk w_await: 2 -> 45 ms
Disk queue: tăng
CPU: còn dư
```

Giả thuyết: storage write/fsync không theo kịp.

Quy trình:

1. Xem provisioned IOPS/throughput và cloud burst.
2. Kiểm tra backup, snapshot, bulk write, index build.
3. Xem dirty cache/eviction và checkpoint.
4. Xem replication lag/write concern.
5. Giảm burst không cấp thiết hoặc tăng I/O capacity theo quyền.
6. Kiểm chứng p99, sync time và disk queue.

**Không đổi `j:true` thành false để “đẹp latency”**; điều đó thay durability contract.

### 18.2. Kịch bản B — Checkpoint duration tăng sau bulk import

```text
Import rate: 5x
WT dirty bytes: tăng
Checkpoint recent time: tăng
Disk write throughput: gần limit
Write p95: tăng
```

Nguyên nhân có thể là workload tăng và storage capacity giới hạn, không phải lỗi checkpoint.

Biện pháp:

- Batch/throttle nhập dữ liệu.
- Giảm indexes không cần thiết trong thiết kế (không drop index production tùy tiện).
- Đo disk capacity/cost.
- Chọn maintenance window hoặc tăng provisioned throughput.
- Đảm bảo replicas theo kịp.

### 18.3. Kịch bản C — Read I/O cao dù nén đã bật

```text
snappy enabled
WT page reads/s: tăng mạnh
Disk r_await: tăng
Queries scanned docs: tăng
```

Không suy luận “đổi zstd sẽ sửa tất cả”. Hãy kiểm tra index/query plan, working set, OS cache, data access pattern. Nén mạnh hơn chỉ giúp khi số disk bytes và cache efficiency là nút thắt; COLLSCAN vẫn là vấn đề lớn.

### 18.4. Kịch bản D — Đổi compressor giúp dung lượng nhưng CPU tăng

```text
Data storage: -30%
Process CPU: +25%
Write p95: +40%
Disk queue: ổn định
```

Có thể workload **CPU-bound** và zstd level quá cao. So lại với snappy hoặc zstd level thấp hơn trên staging. Cần chọn theo mục tiêu chi phí/latency, không chỉ dung lượng.

### 18.5. Kịch bản E — Disk full dù `dbStats.totalSize` không tăng nhiều

Nguồn tăng có thể:

- Oplog.
- Journal headroom khi checkpoint/recovery bị chậm.
- WiredTiger history store.
- Tạm thời khi build index hoặc aggregation spills.
- Backup/log files cùng filesystem.
- Docker/container overlay logs.
- Data/index allocation fragmentation.

Điều tra `df`, filesystem files/managed dashboard và MongoDB stats. **Không xóa journal, oplog hoặc `WiredTigerHS.wt` bằng tay**. Thiếu journal space có thể gây crash, cần phương án tăng capacity/giảm workload và khôi phục theo runbook.

### 18.6. Kịch bản F — Secondary disk chậm gây majority write latency

```text
Primary CPU: 50%
Primary disk: ổn định
Secondary disk w_await: cao
Replication lag: tăng
Majority write latency: tăng
```

Bottleneck có thể nằm ở secondary apply/flush hoặc flow control, không phải chỉ ở primary. Cần quan sát **từng member**, cùng read preference và replication configuration.

## 19. Runbook khi có storage incident

### 19.1. Khoanh phạm vi

Ghi:

- Cluster/replica set, primary/secondary, version/FCV.
- Time window và timezone.
- API operations bị ảnh hưởng.
- Change events: deploy, index build, backup, maintenance.
- Metrics CPU, RAM, disk, journal, checkpoint, replication.
- Volume type/limits/cloud provider.
- Cấu hình nén hiện tại của các collections liên quan.

### 19.2. Thu thập bằng chứng an toàn

Trên MongoDB:

```javascript
const s = db.serverStatus();

printjson({
  uptime: s.uptime,
  wtCache: {
    current: s.wiredTiger?.cache?.[
      "bytes currently in the cache"
    ],
    max: s.wiredTiger?.cache?.[
      "maximum bytes configured"
    ],
    dirty: s.wiredTiger?.cache?.[
      "tracked dirty bytes in the cache"
    ]
  },
  journal: {
    bytes: s.wiredTiger?.log?.["log bytes written"],
    syncs: s.wiredTiger?.log?.["log sync operations"]
  },
  checkpoint: s.wiredTiger?.checkpoint
});
```

Trên Linux:

```bash
iostat -xz 1 5
free -h
vmstat 1 5
df -h
```

Các lệnh trên chủ yếu **chỉ đọc** và có scope nhỏ. Không dùng `du -sh /path` hoặc `find` scan nặng trên filesystem production vào giờ peak nếu có tooling tốt hơn; quét filesystem lớn cũng có I/O cost.

### 19.3. Xác định lớp gây nghẽn

```text
CPU-bound?
  -> query plan / aggregation / compressor CPU

Memory/cache-bound?
  -> working set / eviction / long transactions

Disk-bound?
  -> IOPS / MiB/s / latency / queue / volume throttle

Journal-bound?
  -> fsync timing / write concern / storage latency

Checkpoint pressure?
  -> dirty bytes / write burst / history / device

Replication-bound?
  -> secondary lag / oplog apply / flow control
```

### 19.4. Mitigation theo rủi ro

Ưu tiên ít rủi ro:

1. Throttle batch jobs/exports/imports không cấp thiết.
2. Dừng truy vấn tiêu tốn I/O bất thường theo change control.
3. Tăng cloud volume provisioned IOPS/throughput khi được hỗ trợ.
4. Tăng capacity/headroom với quy trình DBA.
5. Điều chỉnh query/index/workload và rollout có giám sát.
6. Xem compressor/cluster sizing sau benchmark.

Không thực hiện dưới áp lực incident khi chưa có kế hoạch:

- Tắt journal.
- Xóa WiredTiger metadata/journal.
- Drop oplog/index tùy tiện.
- Giảm write concern toàn hệ thống.
- Copy live data files không theo backup protocol.
- Restart liên tiếp khiến cache lạnh/failover.
- Chạy `compact`/`repairDatabase` chỉ để “giảm disk used”.

### 19.5. Kiểm chứng sau thay đổi

Ghi trước/sau:

- Latency p95/p99 và error rate.
- QPS/throughput.
- Journal sync avg và sync/s.
- Checkpoint duration/trend.
- Disk read/write await, queue, IOPS và MiB/s.
- Dirty cache/eviction.
- Replication lag và free capacity.

Chỉ kết luận mitigation hiệu quả khi chỉ số **người dùng** và chỉ số **storage** cải thiện bền vững với traffic tương đương.

## 20. Kế hoạch capacity cho journal, checkpoint và compression

### 20.1. Đừng chỉ lấy `dataSize` làm dung lượng cần mua

Một phép tính minh họa:

```text
Allocated collections:        400 GiB
Allocated indexes:            100 GiB
Oplog/history/logs reserve:    80 GiB
Journal/recovery headroom:     40 GiB
Expected 60-day growth:      180 GiB
Operational safety reserve:  160 GiB
------------------------------------
Capacity target:             960 GiB
```

Tùy backup location, index rebuild, burst và cloud volume size, cần safety buffer khác. Không lấy 960 GiB là mức chuẩn cho tất cả clusters.

### 20.2. Journal không có size cố định mãi

WiredTiger tự quản lý các journal files cần để recover từ checkpoint. Tài liệu đề cập mỗi journal file khoảng **100 MB** và các yếu tố như checkpoint size, compression, recovery time và preallocation.

Đừng thiết kế quota kiểu “journal luôn dưới 100 MB”. Một journal file có giới hạn khoảng 100 MB, **không phải tổng dung lượng journal directory tối đa 100 MB**.

### 20.3. Dự báo theo growth rate

\[
\text{Time to full}
\approx
\frac{\text{Free disk bytes}}
{\text{Net growth bytes per unit time}}
\]

Chỉ dùng như xấp xỉ khi net growth dương và tương đối ổn định. Storage có thể tăng đột biến khi index build, import, long-running transaction hoặc campaign; cần có margin và cảnh báo trước.

### 20.4. Capacity khi failover

Secondary có thể trở thành primary; nên provision đủ CPU/disk IOPS/write bandwidth cho mỗi member có khả năng nhận vai trò primary.

Một secondary chậm cũng ảnh hưởng write concern và replication lag. Không size toàn replica set chỉ theo primary trong điều kiện bình thường.

## 21. Triển khai thay đổi compression an toàn

### 21.1. Quy trình đề xuất

```text
Baseline metrics & SLO
          |
          v
Hypothesis: CPU vs I/O vs capacity
          |
          v
Staging corpus + query replay
          |
          v
A/B compressors, one variable at a time
          |
          v
Measure size, latency, CPU, disk, journal
          |
          v
Decide migration strategy
          |
          v
Canary / isolated new collection
          |
          v
Validate data and business queries
          |
          v
Cutover with rollback path
          |
          v
Monitor several workload cycles
```

### 21.2. Nếu cần migrate existing collection

Vì thay default blockCompressor không tự thay collections cũ, migration cần xem:

- Bản sao collection mới có compressor muốn dùng.
- Copy documents bằng công cụ/ứng dụng được hỗ trợ, giữ BSON types.
- Tạo indexes đúng thứ tự/nội dung.
- Kiểm tra uniqueness, collation, validation rules và TTL.
- Nếu có writes đồng thời, cần cơ chế sync/cutover (quiesce hoặc change streams được quản lý).
- Count/hash/application-level validation khi thích hợp.
- Bảo đảm tham chiếu namespace, read/write clients và batch jobs chuyển đúng.
- Backup và khả năng rollback còn hợp lệ.
- Không tự đổi `_id` hoặc data shape chỉ để đạt ratio tốt hơn.
- Đo dung lượng tạm cần cho **hai bản collection + indexes + oplog/journal**.

Đừng tự chạy `renameCollection`/`drop` trên production dưới danh nghĩa “chỉ đổi nén” khi chưa có kế hoạch nhất quán ghi/đọc.

### 21.3. Rollback

Một số thay đổi compression không đơn giản là đổi lại file YAML:

- Existing collection đã tạo với zstd có thể tiếp tục dùng zstd sau khi default quay về snappy.
- Dữ liệu đã migrate cần một kế hoạch cutback hoặc giữ source read-only.
- Journal compressor được cấu hình ở cấp engine/startup, có quy trình rollout riêng.
- Index prefix compression của indexes cũ không tự thay khi đổi default.

Rollback phải xác định **trạng thái dữ liệu, cấu hình, ứng dụng và backup**, không chỉ một dòng YAML.

## 22. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| “CPU còn rảnh nên disk không thể nghẽn” | Bỏ sót I/O waits | Đo queue, await, IOPS/throughput |
| “Disk 1 TiB luôn nhanh hơn 500 GiB” | Có thể IOPS quota không đổi | Đọc volume provisioned limits |
| “`%util=100%` luôn đã đạt max trên NVMe” | Chẩn đoán quá đơn giản | Xem latency/queue và thiết bị song song |
| “Write là một lần ghi đĩa” | Bỏ index/journal/checkpoint | Hiểu write amplification |
| “Journal chính là `mongod.log`” | Có thể xóa nhầm recovery files | Tách diagnostic log và WAL |
| “Tắt journal để tăng TPS” | Rủi ro durability và không hỗ trợ 6.1+ | Giữ journal, tối ưu root cause |
| “Journal chỉ sync đúng mỗi 100 ms” | Sai khi `j:true`, secondary apply hoặc file rotation | Đọc điều kiện sync |
| “`w:1` và `w:majority,j:true` như nhau” | Sai durability/failover contract | Chọn write concern theo nghiệp vụ |
| “Write concern timeout = chưa ghi gì” | Dễ tạo duplicate writes | Đối soát/idempotency |
| “Checkpoint cứ đúng 60s là xong” | Đánh giá sai spike | Đo duration thực |
| “Không có checkpoint mới nghĩa mọi write bị mất” | Bỏ qua journal recovery | Hiểu checkpoint + journal |
| “Checkpoint là backup” | Có thể không restore được | Dùng backup/snapshot hỗ trợ |
| “Dirty cache cao chắc chắn journal chưa durable” | Nhầm cơ chế | Đọc journal và dirty pages riêng |
| “Journal file 100 MB nghĩa tổng journal tối đa 100 MB” | Thiếu disk headroom | Xem nhiều files/preallocation |
| “Nén mạnh hơn luôn nhanh hơn” | CPU có thể thành bottleneck | Benchmark workload |
| “Dùng zstd cho dữ liệu ZIP luôn tiết kiệm lớn” | Dữ liệu đã nén ít lợi ích | Đo entropy/corpus |
| “Block compression và journal compressor là một” | Đọc sai tác động | Phân biệt config |
| “Index prefixCompression giống snappy cho index” | Sai cơ chế | Hiểu prefix keys |
| “Thay default zstd sẽ nén lại collections cũ” | Sai kỳ vọng capacity | Migration/rebuild có kế hoạch |
| “`dataSize` là physical disk bytes” | Sizing sai | Đọc storageSize/indexSize/filesystem |
| “Xóa documents sẽ trả disk ngay cho OS” | Tưởng mất storage | WiredTiger reuse allocated space |
| “Chỉ cần so một lần `explain()`” | Nhiễu cache/tải | Benchmark có warm-up và lặp |
| “`log bytes written` là size journal folder” | Nhầm counter với gauge | Rate/delta theo process |
| “Không cần backup KMS/replication” | Rủi ro recovery | Backup/restore/test và replication |
| “Có thể xóa `WiredTigerLog.*` bằng tay” | Có thể phá crash recovery | Không sửa file engine thủ công |
| “Mọi MongoDB Atlas tier cho đổi compressor” | Lỗi permission/unsupported | Theo deployment và docs |
| “Profiler luôn đủ để đo storage” | Thiếu OS/cloud metrics | Kết hợp 4 lớp telemetry |
| “Tăng disk capacity là tăng IOPS” | Có thể không | Provision từng giới hạn |

## 23. Bài tập tự luyện

### Bài A — Chẩn đoán I/O

Một node có:

```text
CPU used:            45%
Disk write IOPS:     gần 100% quota
w_await:             3 -> 55 ms
Disk queue:          tăng mạnh
Write p99:           80 -> 600 ms
```

1. Bằng chứng nào ủng hộ disk bottleneck?
2. Vì sao chỉ tăng CPU không chắc giúp?
3. Nếu backup cùng volume chạy, cần kiểm tra gì?
4. Đề xuất một mitigation ít rủi ro.

### Bài B — Journal và checkpoint

Sắp xếp mốc:

```text
Checkpoint A hoàn tất
Write X được journal durable
Write Y được journal durable
Process crash trước checkpoint B
Process restart
```

Giải thích vì sao X/Y có thể được khôi phục từ journal. Nếu write chưa được journal sync theo write concern, điều gì có thể xảy ra?

### Bài C — Write concern

So sánh:

```javascript
{ w: 1 }
{ w: 1, j: true }
{ w: "majority" }
{ w: "majority", j: true, wtimeout: 10000 }
```

Giải thích durability, failover, latency trade-off và vai trò `writeConcernMajorityJournalDefault`.

### Bài D — Journal metrics

Giả sử:

```text
T1: log bytes written = 2,000,000,000
T2: log bytes written = 2,600,000,000
Elapsed: 60 seconds

T1: log sync operations = 400,000
T2: log sync operations = 402,400
```

1. Tính journal bytes/s.
2. Tính syncs/s.
3. Có thể suy ra p95 fsync latency không?
4. Nếu MongoDB restart giữa hai mẫu, cần xử lý thế nào?

### Bài E — Checkpoint pressure

```text
Checkpoint recent time: 1s -> 35s
Dirty cache bytes: tăng
Disk w_await: tăng
Bulk import: vừa bắt đầu
```

1. Nguyên nhân có thể là gì?
2. Cần phân biệt nguyên nhân và hệ quả ra sao?
3. Vì sao không nên tự chỉnh checkpoint interval?
4. Chọn metric để kiểm chứng sau khi throttle bulk import.

### Bài F — Compression trade-off

Hai môi trường có cùng corpus:

```text
Snappy storage:  150 GiB
Zstd storage:     95 GiB
Snappy CPU:       55%
Zstd CPU:         80%
Snappy p95 write: 35 ms
Zstd p95 write:   52 ms
```

Nếu SLO p95 write là 45 ms, có nên chuyển thẳng toàn bộ traffic sang zstd không? Cần thử thay đổi nào hoặc xem quyết định cost/SLO ra sao?

### Bài G — Data size và disk

```text
dataSize:        300 GiB
storageSize:     180 GiB
indexSize:        50 GiB
Filesystem used: 280 GiB
```

1. Tại sao dataSize có thể lớn hơn storageSize?
2. `totalSize` dữ liệu/index theo định nghĩa bao nhiêu?
3. Khoảng chênh filesystem used có thể đến từ đâu?
4. Vì sao không coi 280 GiB là độ nén của collection?

### Bài H — Đổi compressor có ảnh hưởng existing collections?

Một DBA đổi `blockCompressor` từ snappy sang zstd trong startup YAML.

1. Collections đã tạo trước đó có đổi compressor ngay không?
2. Collections mới chịu tác động thế nào?
3. Muốn re-encode dữ liệu cũ cần lập kế hoạch gì?
4. Cần dự phòng storage/headroom bao nhiêu khi giữ hai bản trong migration?

### Bài I — Nén dữ liệu entropy cao

Collection chứa chủ yếu:
  
- JPEG images.
- Base64 của ZIP archives.
- Encrypted application blobs.

1. Vì sao block compression có thể tiết kiệm ít?
2. Có nên thử `none` không?
3. Cần đo CPU, storageSize, disk I/O và p99 thế nào?
4. GridFS hoặc object storage có thể phù hợp hơn trong những trường hợp nào?

### Bài J — Primary và secondary

Primary disk await bình thường, secondary disk write await tăng cùng replication lag và majority write latency.

1. Bottleneck nằm ở node nào khả dĩ hơn?
2. Nên đọc metrics nào từ các members?
3. Nếu chỉ đổi journal compression trên primary, kết quả có chắc tốt hơn không?
4. Cần tính failover capacity thế nào?

### Bài K — Journal disk full

Node gần đầy disk trong khi collection dataSize không tăng đáng kể. Journal directory, oplog và temporary files đều có hoạt động.

1. Cần lấy các phép đo nào trước?
2. Vì sao không được tự xóa `WiredTigerLog.*`?
3. Vì sao journal headroom là một phần capacity planning?
4. Nêu phương án an toàn theo runbook.

### Bài L — Thiết kế benchmark

Lập kế hoạch A/B Snappy vs Zstd cho dịch vụ:

- 80% reads, 20% writes.
- Cùng 2 triệu documents, có strings lặp, một phần binary.
- p99 dưới 100 ms.
- CPU headroom khoảng 25%.
- Cloud volume có giới hạn IOPS.

Hãy đề xuất dataset, control variables, warm/cold cache, metrics, number of runs, canary và rollback.

## 24. Tài liệu tham khảo chính thức

Các đặc tính cấu hình phụ thuộc MongoDB server version, storage engine, môi trường managed và loại triển khai. Nguồn ưu tiên:

- [WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/) — checkpoint, journal, block compression và prefix compression.
- [Journaling](https://www.mongodb.com/docs/manual/core/journaling/) — write-ahead log, thời gian sync, files và crash recovery.
- [Self-Managed Configuration File Options](https://www.mongodb.com/docs/manual/reference/configuration-options/) — `journalCompressor`, `blockCompressor`, `prefixCompression`, `zstdCompressionLevel` và `commitIntervalMs`.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — `w`, `j`, majority durability và timeouts.
- [`serverStatus`](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — `wiredTiger.log`, `checkpoint`, cache và transaction counters.
- [`dbStats`](https://www.mongodb.com/docs/manual/reference/command/dbStats/) — logical data, allocated collection/index storage, filesystem metrics.
- [`collStats`](https://www.mongodb.com/docs/manual/reference/command/collStats/) — storage allocation, indexes và WiredTiger statistics theo collection.
- [`create` command: Storage Engine Options](https://www.mongodb.com/docs/manual/reference/command/create/) — collection-specific WiredTiger configString.
- [Production Notes](https://www.mongodb.com/docs/manual/administration/production-notes/) — memory/filesystem/production deployment.
- [MongoDB Atlas Cluster Monitoring](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/) — resource và disk metrics trên managed deployments.
- [Database Profiler](https://www.mongodb.com/docs/manual/tutorial/manage-the-database-profiler/) — truy vấn chậm và overhead.
- [`explain`](https://www.mongodb.com/docs/manual/reference/explain-results/) — plan và execution statistics.
- [Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/) — nén và storage đặc thù.

**Lưu ý phiên bản:** các metrics/tên fields và tham số cấu hình có thể thay đổi; MongoDB 6.1+ bật journaling bắt buộc, MongoDB 8.2 mở rộng dải Zstd levels, time-series có default zstd thay vì snappy ở đa số collections. Kiểm tra chính xác server/FCV, driver, edition và permissions trước khi triển khai bất kỳ thay đổi nào.

## 25. Kết luận

Đánh giá hiệu năng lưu trữ MongoDB phải đi từ **triệu chứng API** tới **WiredTiger và phần cứng**:

1. Ổ đĩa cần đo **IOPS, throughput, latency, queue, free capacity và burst quota**, không chỉ xem dung lượng.
2. **Journal** là write-ahead log bảo vệ những ghi đã đạt durability contract giữa các checkpoints; không phải diagnostic log và không được xóa bằng tay.
3. **Checkpoint** đưa một trạng thái dữ liệu nhất quán xuống disk; chu kỳ thường 60 giây nhưng thời gian thực hiện phụ thuộc dirty pages, I/O và workload.
4. **Write concern** quyết định khi nào client được xác nhận; `j:true` và `w:"majority"` có vai trò khác nhau.
5. **Collection compression, journal compression và index prefix compression** là ba cơ chế riêng, có default và phạm vi tác động khác nhau.
6. **Snappy, Zstd, Zlib và none** phải được lựa chọn bằng benchmark trên corpus và query thật, cân bằng storage, CPU, disk I/O và p95/p99.
7. Đổi default compression **không tự re-compress existing collections/indexes**. Migration cần backup, capacity headroom, data validation và rollback.
8. Khi sự cố, không tắt journal, không xóa file WiredTiger, không giảm durability theo phản xạ. Thu thập metrics theo thời gian và sửa tại đúng lớp đang nghẽn.

**Nguyên tắc cốt lõi:** tối ưu MongoDB storage không phải tìm một “tham số nhanh nhất”, mà là chứng minh một cấu hình giúp **đạt SLO ứng dụng và durability với chi phí tài nguyên chấp nhận được**, trong khi dữ liệu vẫn có thể khôi phục và hệ thống vẫn vận hành an toàn.
