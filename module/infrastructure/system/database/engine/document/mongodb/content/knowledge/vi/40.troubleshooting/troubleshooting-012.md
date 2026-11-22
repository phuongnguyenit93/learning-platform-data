# Đầy ổ đĩa, áp lực bộ nhớ và ưu tiên hành động khôi phục an toàn trong MongoDB

Một hệ thống MongoDB đang vận hành ổn định bỗng bắt đầu trả lỗi ghi, ứng dụng Java timeout và biểu đồ độ trễ tăng mạnh. Dashboard báo filesystem chứa `dbPath` chỉ còn vài trăm MiB; đồng thời một số container MongoDB bị restart vì `OOMKilled`. Người trực vận hành có thể bị thúc ép “giải phóng dung lượng ngay”, nhưng lựa chọn sai — xóa file WiredTiger, xóa oplog, drop index, restart cả replica set hoặc chạy compact trên ổ đã đầy — có thể biến một sự cố tài nguyên còn cứu được thành **mất dữ liệu hoặc ngừng dịch vụ kéo dài**.

Bài **“Đầy ổ đĩa, áp lực bộ nhớ và ưu tiên hành động khôi phục an toàn”** thuộc chương **Xử lý sự cố** của module **Database Engine Document MongoDB**. Trọng tâm là **quyết định khi đang có sự cố**: quan sát tín hiệu nào trước, phân biệt root cause, giảm tải thế nào, hành động nào an toàn và có thể đảo ngược, khi nào phải mở rộng tài nguyên, cách khôi phục từng member mà không làm mất quorum, và xác nhận dữ liệu/ứng dụng sau can thiệp.

Mục tiêu:

1. Phân biệt **disk capacity full**, **inode/quota full**, **filesystem read-only**, **disk I/O saturation** và **memory pressure/OOM**.
2. Đọc nhanh những tín hiệu quan trọng từ Linux, `mongod`, Docker, Kubernetes và MongoDB Atlas.
3. Hiểu vì sao file WiredTiger, journal và oplog **không phải rác có thể xóa thủ công**.
4. Chọn thứ tự **ngăn tác hại → xác minh topology → bảo toàn dữ liệu → tăng tài nguyên/giảm tải → khôi phục → đối soát**.
5. Tránh “chữa triệu chứng” bằng `compact`, `repair`, xóa hàng triệu documents hoặc tăng replica count khi dữ liệu đang nguy cấp.
6. Kiểm soát backpressure, retry và idempotency phía Java/Spring Boot để ứng dụng không làm database kiệt sức thêm.
7. Xây runbook cho standalone, replica set, sharded cluster và môi trường container/Atlas.
8. Thiết lập kiểm thử khôi phục, cảnh báo dựa trên tốc độ tăng dữ liệu, RPO/RTO và postmortem.

> **Nguyên tắc an toàn:** ví dụ lệnh chủ yếu là **đọc trạng thái**. Những thay đổi như resize volume, thay cgroup limit, restart MongoDB, step down primary, tắt nguồn ghi, xóa dữ liệu, đổi TTL, resync member hoặc restore phải được thực hiện theo runbook được duyệt, có đánh giá topology/backup và quyền vận hành. Không thực hiện thao tác hủy dữ liệu chỉ vì một câu lệnh có vẻ giúp `df` giảm ngay.

## 1. Bốn tầng cần xác định trước khi can thiệp

```text
Ứng dụng Java / API
  |
  | request rate, retry storm, bulk writes
  v
MongoDB mongod / mongos
  |
  | WiredTiger cache, journal, checkpoints,
  | oplog, replication, query execution
  v
Hệ điều hành / container / cgroup
  |
  | RAM limit, OOM killer, page cache,
  | file descriptors, mount, inode, quota
  v
Storage backend
  |
  | capacity, IOPS, throughput, latency,
  | snapshots, attached volumes, failures
  v
Disk / managed storage
```

Một lỗi ở tầng dưới có thể biểu hiện ở tầng trên:

- Disk I/O quá chậm → `mongod` trả kết quả chậm → driver chờ lâu → API timeout → client retry → số requests tăng → disk càng chậm.
- Memory limit thấp → `mongod` bị OOM kill → ứng dụng thấy connection reset → retry nhiều → recovery/checkpoint chịu thêm tải.
- Volume hết dung lượng → journal/checkpoint/write thất bại → member không phục vụ bình thường → replica set mất đa số → ứng dụng không ghi được.
- Path mount sai → MongoDB khởi động trên filesystem khác hoặc trống → biểu hiện “mất dữ liệu” dù volume gốc còn.

Vì vậy, **không nên chỉ đọc một stack trace từ Java rồi chọn thay đổi ngay ở MongoDB**.

## 2. Phân biệt “đầy ổ” với “database chậm”

| Hiện tượng | Bằng chứng thường tìm | Không nên suy luận vội |
| --- | --- | --- |
| **Hết bytes** | `df -h` gần hoặc bằng 100%, `ENOSPC` | Mọi lỗi ghi đều do document quá lớn |
| **Hết inodes** | `df -i` đầy, không tạo được file | `df -h` còn nhiều GiB nghĩa là an toàn |
| **Disk quota** | Filesystem còn chỗ nhưng user/project quota đã tới hạn | Cứ tăng size cloud volume là đủ |
| **Read-only filesystem** | Mount options `ro`, kernel I/O errors | Chỉ cần chown/chmod |
| **I/O saturation** | Latency/queue cao, IOPS hoặc throughput chạm giới hạn | Disk còn 40% trống nghĩa là đủ performance |
| **WiredTiger cache pressure** | Eviction/dirty pages/reads from disk tăng | Toàn bộ memory RSS là cache |
| **OOM kill** | K8s `OOMKilled`/kernel logs/cgroup event | MongoDB tự crash vì bug |
| **OS page cache biến động** | RAM “free” thấp nhưng “available” còn | Cứ RAM free thấp là phải restart |

Các tín hiệu có thể xảy ra **đồng thời**. Một ổ đĩa nghẽn làm eviction/checkpoint chậm; thiếu RAM làm tăng đọc disk; viết retries làm oplog tăng nhanh hơn. Điều tra nên tìm **chuỗi nguyên nhân** thay vì gán một nhãn duy nhất.

## 3. Sơ đồ quyết định trong 5 phút đầu

```text
Alert: write errors / p99 latency / mongod restart
                  |
                  v
          Có dữ liệu có nguy cơ mất?
                  |
          +-------+--------+
          |                |
         Có               Chưa rõ
          |                |
          v                v
   Giữ bằng chứng       Kiểm tra backup/
   và ngăn thao tác     topology/RPO
   phá dữ liệu               |
          +--------+--------+
                   |
                   v
        Host / PVC / Atlas storage đầy?
             /          \
           Có            Không
           |              |
           v              v
       bytes/inode/     OOM / cache /
       quota/RO/IOPS    CPU/I/O/network
           \              /
            \            /
             v          v
         Xác định member và vai trò
         (primary/secondary/config shard)
                   |
                   v
      Giảm nguồn phát sinh lỗi, bảo vệ quorum
                   |
                   v
      Thao tác ít phá hủy nhất có thể
                   |
                   v
       Verify dữ liệu + replication + API
```

Đây là **trật tự suy nghĩ**, không phải cam kết mọi incident được giải quyết trong năm phút. Đôi khi việc **ngừng ghi không thiết yếu** ngay là ưu tiên cao hơn thu thập thêm metric nặng.

## 4. Ưu tiên an toàn: việc gì làm trước, việc gì làm sau?

| Mức ưu tiên | Hành động | Mục đích | Điều kiện |
| --- | --- | --- | --- |
| P0 | Ngừng lệnh phá hủy tự phát | Tránh mất dữ liệu thứ cấp | Áp dụng ngay |
| P0 | Xác định topology/quorum/role của member | Tránh làm cluster tê liệt | Trước restart/stepdown |
| P0 | Giảm write burst/retry storm không thiết yếu | Chặn tốc độ tình trạng xấu thêm | Phối hợp app owner |
| P0 | Kiểm tra backup/recovery options | Biết dữ liệu có thể khôi phục đến đâu | Không chờ tới lúc xóa dữ liệu |
| P1 | Đo chính xác bytes, inode, mount, quota, IO latency/RAM | Chọn nguyên nhân thật | Dùng read-only commands |
| P1 | Mở rộng volume/RAM/IOPS theo cách được hỗ trợ | Tạo headroom mà không xóa data | Kiểm tra backend/topology |
| P1 | Dọn **artifacts ngoài dbPath** đã xác minh an toàn | Giải phóng chỗ tạm nếu cần | Đúng file, owner và retention |
| P1 | Khôi phục member theo thứ tự duy trì quorum | Trả lại availability | Theo runbook replica set |
| P2 | Sửa workload/index/retention, tối ưu cache | Ngăn tái phát | Sau khi đã ổn định |
| P2 | Resize lại resource, cải thiện alerts | Capacity/performance planning | Có metrics thực |

**Không phải P0:** `rm -rf /var/lib/mongodb/journal`, `rm WiredTiger*`, `db.dropDatabase()`, `rs.reconfig(..., {force:true})`, restart tất cả members, bật `--repair` như phản xạ, hoặc xóa volume/PVC. Những thao tác này có rủi ro lớn hơn nhiều so với việc thêm dung lượng hay điều tiết nguồn ghi.

## 5. Thu thập thông tin tối thiểu mà không tăng tải

Thông tin nên ghi lại:

```text
Incident ID:
Thời điểm bắt đầu:
Cluster / environment:
MongoDB version:
Standalone / replica set / sharded:
Vai trò node: primary / secondary / config server / mongos
Storage path / mount / PVC / volume ID:
Disk bytes free / inode free:
Disk I/O latency / queue:
Process memory RSS / cgroup memory limit:
Restart count / OOM events:
Replication health / lag / majority available:
Write error samples / app request rate:
Backup cuối cùng đã xác minh:
RPO / RTO yêu cầu:
Recent deploy / migration / data import:
```

Không đưa credentials/PII, full BSON records hoặc internal keys vào incident ticket không được bảo vệ. Log nên có correlation ID và những metric đã sanitize.

### Tại sao ghi baseline trước?

Nếu ngay lập tức restart, một số counters và evidence trong memory sẽ mất. Nếu xóa file/volume, chứng cứ phục hồi có thể không còn. Tuy nhiên **không trì hoãn hành động giảm tải an toàn** chỉ để lấy một bản `serverStatus` rất lớn khi hệ thống đã nghẽn nghiêm trọng.

## 6. Phân loại mức độ ảnh hưởng

Sự cố “disk 95%” chưa chắc nghiêm trọng bằng “primary không thể journal và ứng dụng không ghi được”. Có thể phân loại:

| Mức | Tình huống | Hành động điển hình |
| --- | --- | --- |
| **Sev 1 / khẩn** | Primary hoặc phần lớn members không ghi/phục vụ; nguy cơ loss/quorum | Incident command, giảm writes, bảo toàn dữ liệu, tăng capacity/khôi phục theo topology |
| **Sev 2 / cao** | Một secondary đầy và lag lớn; primary vẫn khỏe | Bảo vệ quorum, phục hồi secondary có kiểm soát |
| **Sev 3 / cảnh báo** | Disk còn ít nhưng service vẫn tốt; dự báo sớm đầy | Lên kế hoạch resize và xử lý tăng trưởng |
| **Sev 3 / suy giảm** | Memory pressure/cache eviction làm p99 tăng nhưng chưa crash | Sizing/điều tiết workload, theo dõi risk |

Đây là ví dụ phân loại, không thay hệ thống severity nội bộ. Ưu tiên thực tế phải dựa trên **customer impact, dữ liệu có rủi ro, quorum, write availability, tốc độ cạn tài nguyên và RTO/RPO**, không chỉ một ngưỡng phần trăm.

## 7. Kiểm tra filesystem chứa `dbPath` trên Linux

Đầu tiên xác định `storage.dbPath` thực tế từ config/startup arguments của **mongod đang chạy**, không đoán từ package:

```bash
# Lệnh quan sát; không thay đổi dữ liệu.
ps -eo user,pid,cmd | grep '[m]ongod'
systemctl cat mongod
```

Giả sử `dbPath` là `/var/lib/mongodb`, kiểm tra:

```bash
df -hT /var/lib/mongodb
df -i /var/lib/mongodb
findmnt -T /var/lib/mongodb
lsblk -f
```

Ý nghĩa:

- `df -hT`: dung lượng và filesystem type của volume.
- `df -i`: inodes còn lại.
- `findmnt -T`: mount thực sự đang chứa path, bao gồm mount options.
- `lsblk -f`: block devices/filesystems; trên managed/container environment cần đọc cùng cloud/CSI metadata.

### Cảnh báo: mount sai còn nguy hiểm hơn disk nhỏ

Một host lẽ ra mount disk dữ liệu ở `/var/lib/mongodb` nhưng mount thất bại có thể khiến thư mục này nằm trên **root filesystem**. Process có thể ghi lên root disk hoặc đọc database trống tùy cấu hình và filesystem hiện hữu.

Đừng tạo data mới và “chấp nhận database trống” trước khi kiểm tra mount. Xác minh volume ID, filesystem UUID, path và nội dung theo runbook. Việc attach một volume cũ vào node sai cũng có thể gây lỗi ownership/format/security.

## 8. Hết bytes: `ENOSPC` và hậu quả

`ENOSPC` thường biểu thị “No space left on device”. Khi filesystem chứa `dbPath` không còn khả năng cấp phát:

- MongoDB có thể không thể tạo/ghi những file cần thiết.
- Journal/checkpoint/storage writes có thể gặp lỗi.
- Index build, import, initial sync hoặc temporary files có thể thất bại.
- Log hoặc diagnostics có thể không ghi thêm được nếu cùng filesystem.
- Member có thể dừng hoặc trở nên không khỏe tùy server/storage failure mode.
- Ứng dụng thấy timeout, write failures và failover tùy topology.

**Không mặc định một `insertOne()` bị timeout nghĩa là không ghi được gì**. Nếu client không nhận acknowledgment, kết quả có thể mơ hồ; dùng business idempotency key để đối soát thay vì tạo bản ghi mới vô điều kiện.

### Không phải lúc nào dung lượng “MongoDB logical data” tăng bằng dung lượng filesystem

Disk usage bị ảnh hưởng bởi:

```text
WiredTiger data files
 + index storage
 + journal/checkpoint internals
 + oplog của replica set
 + temporary/index-build files
 + log files/backup artifacts nếu chung filesystem
 + filesystem metadata / snapshots / quotas
```

Chỉ nhìn `db.stats().dataSize` có thể bỏ sót indexes, oplog, journal, overhead và những file khác trên cùng volume.

## 9. Hết inode và quota: `df -h` chưa đủ

Filesystem có thể còn nhiều GiB nhưng không tạo được file mới vì:

- Hết **inodes** (đặc biệt khi có nhiều file nhỏ).
- User/project/container bị **quota** giới hạn.
- Đạt giới hạn volume/thin provisioning/snapshot pool.
- Filesystem đã chuyển sang read-only vì lỗi I/O.

Kiểm tra:

```bash
df -hT /var/lib/mongodb
df -i /var/lib/mongodb
findmnt -T /var/lib/mongodb
```

Nếu `df -h` còn chỗ nhưng ghi lỗi, cần kiểm tra events/logs/quota/backing storage. Không tự kết luận vấn đề nằm ở BSON document hoặc lỗi permission.

### Đừng “tạo thử file” trong `dbPath`

Trong incident, không viết các file thử nghiệm vào thư mục WiredTiger để xem có ghi được không. Nếu cần thử filesystem write, làm theo runbook trên một path test riêng có quyền và dung lượng nhỏ, hoặc dùng metric/diagnostics hiện có; không làm đầy thêm data volume.

## 10. Filesystem read-only và I/O errors

Một filesystem có thể được remount ở chế độ `ro` khi kernel/storage phát hiện lỗi. Khi đó `chmod`, `chown`, restart hoặc thêm credentials **không giải quyết nguyên nhân**.

Lệnh quan sát:

```bash
findmnt -T /var/lib/mongodb
journalctl -k --no-pager -n 100
```

Tìm tín hiệu:

- `I/O error`.
- Filesystem metadata errors.
- Device disconnect/timeout.
- Read-only remount.
- Storage backend unavailable.

**Không cố ép filesystem sang read-write** khi chưa hiểu vì sao nó tự chuyển read-only. Có thể đang có lỗi phần cứng hoặc metadata cần xử lý qua quy trình storage/OS vendor. Trước mọi repair ở cấp filesystem phải có backup/snapshot và quyết định của người quản trị storage.

## 11. Disk chưa đầy nhưng I/O saturation

Disk capacity và tốc độ I/O là hai vấn đề khác nhau:

| Metric | Câu hỏi |
| --- | --- |
| Free bytes | Còn chỗ lưu data không? |
| IOPS | Disk xử lý được bao nhiêu operations/giây? |
| Throughput | Disk truyền bao nhiêu MiB/giây? |
| I/O latency | Mỗi operation phải chờ bao lâu? |
| Queue depth | Có bao nhiêu I/O đang chờ? |
| Cloud burst credits | Đã cạn tốc độ burst tạm thời chưa? |

Một SSD cloud volume có thể còn 50% trống nhưng chạm giới hạn IOPS/throughput. Mongod khi đó có thể chậm checkpoint/journal, đọc index/data chậm và secondary lag.

Nếu có `sysstat`:

```bash
# Chỉ đọc một cửa sổ ngắn; xem device thật đang chứa dbPath.
iostat -xz 1 5
```

Trong cloud/Kubernetes, cần đối chiếu metrics của volume/CSI vì số liệu trên host/container có thể thiếu hoặc bao gồm nhiều workload khác. Đừng chỉ tăng kích thước disk nếu performance bottleneck là IOPS policy; và đừng chỉ tăng vCPU nếu mọi thread đang chờ storage.

## 12. Xác định nguồn tăng disk space

Các khả năng thường gặp:

1. Tốc độ insert/ingest tăng mạnh.
2. Index mới hoặc index build trên collection lớn.
3. Oplog được sizing lớn hơn/đang tăng trong workload tương ứng.
4. Backup/dump hoặc export được ghi **cùng volume** với `dbPath`.
5. Log application/system/MongoDB không rotation.
6. File tạm, staging data, snapshot/cache khác chiếm chỗ.
7. Dữ liệu cũ không được TTL/retention xử lý đúng.
8. Quá trình resync/index migration tạo workload lưu trữ lớn.
9. Cloud snapshot/thin-provisioning/volume quotas có giới hạn ẩn.

### Ưu tiên khảo sát cấp filesystem

```bash
# Đọc dung lượng các mount liên quan:
df -hT /var/lib/mongodb /var/log

# Quan sát thư mục log nếu đã xác minh đúng path:
ls -lh /var/log/mongodb
```

Một lệnh thống kê tổng thể như `du -x -h -d 1 /var/lib/mongodb` có thể đọc rất nhiều metadata, gây thêm I/O trên disk đã quá tải. **Không chạy recursive scan nặng theo phản xạ**; chọn thời điểm, phạm vi và ưu tiên metrics/observability đã có.

### Deleted-but-open files

Trên Linux, một file log đã bị xóa nhưng process vẫn giữ handle mở có thể tiếp tục chiếm disk space cho tới khi handle đóng. Với quyền phù hợp và khi thật cần điều tra:

```bash
# Có thể tốn tài nguyên; chỉ chạy khi được phép và cần thiết.
lsof +L1
```

Không tự restart `mongod` chỉ để giải phóng một log open handle; phải đánh giá topology/quorum và xem có cơ chế log rotation/reopen an toàn.

## 13. Vì sao không được xóa file WiredTiger, journal hoặc oplog?

Những file bên trong `dbPath` là **state nội bộ** của storage engine/server:

```text
dbPath/
  WiredTiger* ...
  collection/index data files ...
  journal/ ...
  internal metadata ...
```

Tên file và layout thay đổi theo phiên bản; không coi chúng là cấu trúc thư mục ổn định để thao tác thủ công.

Xóa một file có thể gây:

- Không khởi động được storage engine.
- Inconsistent metadata hoặc dữ liệu bị hỏng.
- Không thể thực hiện crash recovery đúng.
- Secondary không theo kịp/không thể resume oplog.
- Thời gian restore và data-loss risk tăng.

**Tuyệt đối không xử lý sự cố đầy ổ bằng cách xóa `journal/`, `WiredTiger.wt`, các collection-*.wt hay tự cắt `local.oplog.rs`.**

MongoDB có cơ chế quản lý journal, checkpoint, storage reuse, oplog sizing/retention riêng. Chỉ sử dụng **database commands hoặc vận hành được MongoDB hỗ trợ** theo runbook, không chỉnh file trực tiếp.

## 14. Thứ tự giảm tải khi filesystem sát đầy

Trình tự thường ít rủi ro hơn xóa dữ liệu:

1. **Ngưng nhập liệu không thiết yếu**: batch import, ETL, analytics jobs tạo dữ liệu, rebuild index không khẩn.
2. **Dừng retry storm** từ application: tăng backoff, giới hạn concurrency, mở circuit breaker theo policy.
3. **Đánh giá business-critical writes**: không tự ngừng thanh toán/đơn hàng nếu làm mất giao dịch; phối hợp product/incident lead.
4. **Dự báo thời gian tới khi đầy** dựa trên slope dung lượng, không chỉ phần trăm hiện tại.
5. **Mở rộng storage an toàn**, ưu tiên đường không hủy dữ liệu và hỗ trợ bởi platform.
6. **Giải phóng artifacts ngoài dbPath** chỉ khi đã xác minh chúng là bản tạm/rotated logs không còn được sử dụng và retention cho phép.
7. **Xác nhận MongoDB health và business data** sau khi có headroom.

Đây không phải “đóng mọi API ghi ngay lập tức”. Một hệ thống tài chính có thể cần **đưa request vào queue bền vững** hoặc trả lỗi tạm thời rõ nghĩa, tránh nhận thành công khi write chưa được xác nhận.

## 15. Mở rộng volume: tại sao thường an toàn hơn xóa data?

Nếu storage backend cho phép resize, **tăng capacity** thường giúp MongoDB tiếp tục hoạt động mà không phải xóa documents, indexes hoặc oplog.

Tuy nhiên có nhiều lớp:

```text
Cloud block volume size
        |
        v
Partition / logical volume
        |
        v
Filesystem capacity
        |
        v
MongoDB dbPath available bytes
```

**Tăng size của cloud volume không luôn làm `df -h` tăng ngay**. Có thể còn bước mở rộng partition/LVM/filesystem tùy hệ điều hành/backend.

### An toàn khi resize

- Xác minh đúng **volume ID, mount path, filesystem**.
- Có snapshot/backup và plan nếu backend yêu cầu.
- Đọc thủ tục online/offline grow hỗ trợ cho filesystem (XFS/ext4, v.v.).
- Đánh giá replication/quorum nếu buộc restart.
- Không resize nhầm root disk trong khi data nằm ở PV khác.
- Xác nhận quota/IOPS chính sách sau resize.
- Sau thao tác, đọc lại `df` và metrics thực tế.

Không đưa một lệnh `resize2fs`/`xfs_growfs` duy nhất làm công thức cho mọi storage layout. Đường chạy phải theo vendor/OS/filesystem và change process đã phê duyệt.

## 16. Có nên xóa logs để lấy dung lượng?

**Chỉ với logs được nhận diện rõ, ngoài `dbPath` và theo retention policy.**

Ví dụ log đã rotate thành file cũ ở `/var/log/mongodb/` có thể được archive/xóa theo policy, nhưng:

- Đừng xóa file log **đang được process mở** rồi mặc định dung lượng sẽ được trả lại ngay.
- Không xóa audit logs đang thuộc legal hold hoặc incident investigation.
- Kiểm tra logs có thực sự nằm trên **cùng filesystem** đang đầy không.
- Dọn logs trên filesystem khác không giải quyết vấn đề `dbPath` đầy.
- Log rotation/truncation phải dùng cơ chế hỗ trợ, với owner/permissions đúng.

### Mục tiêu không phải “tìm file lớn nhất rồi xóa”

Một file có dung lượng lớn có thể là **data file hợp lệ** của WiredTiger. Những file này phải được quản lý qua MongoDB operations, không thông qua `rm`. Nếu có backup archive/temporary export nằm cạnh data, cần kiểm tra có phải bản sao duy nhất hoặc đang được dùng không.

## 17. Vì sao `deleteMany()` không phải giải pháp disk-full tức thì?

MongoDB:

```javascript
db.events.deleteMany({ createdAt: { $lt: cutoff } });
```

có thể xóa logical documents, nhưng trên WiredTiger:

- Storage engine có thể giữ pages/data files để **tái sử dụng**, nên `df -h` không giảm ngay theo số bytes document đã xóa.
- Delete một lượng lớn documents còn tạo **writes, journal và oplog**, có thể làm storage chậm hơn trong incident.
- Secondary phải replicate và xử lý deletes; nếu đang lag, công việc có thể tăng áp lực.
- Cần đảm bảo business retention và legal requirements.

Vì vậy trong tình huống gần hết bytes, **không tung một `deleteMany` khổng lồ chỉ vì muốn cứu disk**. Nếu dữ liệu thật sự hết vòng đời, dùng retention/TTL/batch cleanup có kế hoạch, có headroom và kiểm tra khả năng OS reclamation theo storage semantics.

### TTL không phải công tắc xóa tức thì

TTL monitor chạy bất đồng bộ; không hứa rằng dữ liệu sẽ biến mất ngay khi expiry hoặc ngay sau khi tạo TTL index. Một lần chạy dồn quá nhiều TTL deletes còn có thể tăng I/O/oplog pressure.

## 18. Tại sao `compact` không được dùng như thao tác cứu hỏa mặc định?

MongoDB có `compact` và những cơ chế quản lý/reclaim storage tùy phiên bản. Nhưng `compact` có thể:

- Đọc/ghi nhiều dữ liệu, tốn I/O và thời gian.
- Có yêu cầu free-space/headroom.
- Tác động tới availability/performance.
- Có semantics/limitations khác nhau theo version/topology.

Nếu node đang ở trạng thái disk-full hoặc I/O bão hòa, chạy compact có thể **làm tình hình xấu hơn** hoặc thất bại.

**Thứ tự hợp lý:** khôi phục headroom/availability trước; sau incident đánh giá fragmentation, storage reuse, thiết kế collections/indexes và whether compact/rebuild có thực sự cần thiết. Không đồng nhất xóa documents với việc file system phải giảm bytes.

## 19. Oplog: tại sao không được cắt ngắn tùy tiện?

Replica set dùng oplog để replicate operations. Oplog size/retention liên quan tới:

- Secondary lag và khả năng bắt kịp.
- Change streams resume windows.
- Khả năng resync nếu secondary offline lâu.
- Dung lượng volume cần dự trù.

Khi disk đầy, **xóa tay oplog hoặc thay đổi cấu hình oplog không có kế hoạch** có thể khiến secondary phải initial sync, CDC consumers mất resume token hoặc cluster rơi vào recovery kéo dài.

### Làm gì thay vì xóa oplog?

1. Đo lag và oplog window theo metrics phù hợp.
2. Xác định member nào đang chịu write pressure.
3. Tăng storage đúng cách nếu volume không đủ.
4. Giảm write surge, batch load/retries.
5. Xây kế hoạch oplog sizing và CDC retention **sau khi hệ thống ổn định**.

Trong tình trạng có nhiều lagging members, không nên giảm oplog window chỉ để tiết kiệm dung lượng trước mắt.

## 20. Replica set: sự cố một secondary khác sự cố primary

Giả sử:

```text
Replica set (3 voting data-bearing members):

node-a  PRIMARY    disk 97%
node-b  SECONDARY  disk 60%
node-c  SECONDARY  disk 65%
```

Nếu primary gần đầy, hệ thống vẫn có hai secondaries, nhưng điều đó **không cho phép restart/stepdown mù quáng**:

- Kiểm tra secondaries có khỏe và bắt kịp oplog không.
- Kiểm tra majority/quorum hiện có.
- Xác minh write concern và application failover behavior.
- Quyết định mở rộng primary storage trực tiếp hay chuyển tải theo planned failover.
- Tránh gây election liên tiếp khi server đã có resource pressure.

### Trường hợp secondary đầy

```text
node-a  PRIMARY    disk 60%
node-b  SECONDARY  disk 99%
node-c  SECONDARY  disk 60%
```

Ưu tiên thường là **cứu node-b mà không làm ảnh hưởng node-a/node-c**. Nhưng nếu replica set đã mất members khác, ngừng node-b có thể làm mất majority. Phải nhìn **toàn bộ topology** trước khi đưa quyết định.

### Không restart tất cả members cùng lúc

Nếu một node có thể recovery được sau tăng volume, hãy xử lý từng node theo runbook và xác nhận nó trở lại healthy trước khi động tới node khác. Restart đồng thời cả replica set có thể làm mất availability/quorum không cần thiết.

## 21. Khi nhiều members cùng đầy: nguy cơ correlated failure

Một tình huống nguy hiểm hơn:

```text
node-a PRIMARY    99%
node-b SECONDARY  99%
node-c SECONDARY  98%
```

Vì workload và data được replicate, ba members có thể tăng dung lượng gần như cùng tốc độ. “Để primary failover sang secondary” không sửa được nếu **secondary cũng gần đầy**.

Hành động ưu tiên:

1. Declare incident và xác định RPO/RTO.
2. Hạn chế ingest/retry storm ở cấp ứng dụng.
3. Giữ members online nếu còn có thể; không đồng loạt restart.
4. Xác định volume nào cần resize trước để tránh mất majority.
5. Đảm bảo storage backends có đủ capacity/IOPS thực.
6. Sau resize từng node, xác nhận replication/health.
7. Theo dõi growth slope để không tái đầy sau vài phút.

Nếu tất cả members phụ thuộc cùng một shared storage failure domain, đây còn là vấn đề **kiến trúc độ sẵn sàng**, không chỉ capacity của một node.

## 22. Sharded cluster: shard và config servers

Trong sharded MongoDB, có:

```text
App -> mongos routers
         |
         +--> Shard A replica set
         +--> Shard B replica set
         +--> Shard C replica set
         |
         +--> Config server replica set
```

Phải biết volume nào đang đầy:

- **Shard data node**: ảnh hưởng tập dữ liệu/chunks và queries trên shard ấy.
- **Config server node**: metadata/configuration critical; sự cố có thể ảnh hưởng toàn cluster.
- **mongos host**: router thường không giữ collection data như mongod; disk ở đây có thể liên quan logs/OS.

Không xem tất cả hosts có port MongoDB như nhau. Việc resync/restart config servers phải thận trọng đặc biệt và tuân theo hướng dẫn topology/version.

### Chunk migration không phải giải pháp cấp cứu phổ quát

Sharding có thể phân phối dữ liệu theo shard key và migration policies. Nhưng khi disk gần đầy, chunk movement:

- Gây thêm network/disk I/O.
- Cần capacity ở shard đích.
- Không giải quyết nhanh lỗi liên quan filesystem/inode/read-only.
- Có thể bị giới hạn bởi cluster state.

Không kích hoạt rebalance/moveChunk hàng loạt khi disk đang nghẽn mà chưa kiểm tra headroom và plan.

## 23. Backup trước khi làm gì?

**Backup không đồng nghĩa có thể lấy ngay backup mới trong incident.** Nếu disk đã đầy, khởi động một `mongodump` ghi archive lên **cùng volume** sẽ làm tình trạng nghiêm trọng hơn.

Các câu hỏi cần trả lời:

1. Backup hợp lệ gần nhất có từ khi nào?
2. RPO tối đa cho phép mất bao nhiêu dữ liệu?
3. Backup có consistent và đã test restore chưa?
4. Có snapshot/managed backup không cần ghi dữ liệu tạm lên volume đang đầy?
5. Destination restore có đủ dung lượng và quyền truy cập không?
6. Có yêu cầu preserve incident evidence trước khi thay filesystem/storage không?

### Không copy live dbPath tùy tiện

```bash
# KHÔNG coi đây là backup nhất quán của mongod đang ghi:
cp -r /var/lib/mongodb /backup/mongo-copy
```

Các files có thể được copy tại nhiều thời điểm khác nhau và không nhất quán với journal/checkpoints. Dùng phương thức **mongodump/snapshot/managed backup** được MongoDB hỗ trợ theo topology và consistency requirements.

### Backup không thay headroom

Có backup vẫn nên bảo vệ data đang chạy; restore nhiều TiB có thể tốn thời gian, vượt RTO hoặc gây khó khăn về đồng bộ dữ liệu mới phát sinh.

## 24. Memory pressure là gì?

MongoDB và hệ điều hành sử dụng RAM cho nhiều thành phần:

```text
RAM host / cgroup limit
    |
    +--> MongoDB process
    |      |
    |      +--> WiredTiger internal cache
    |      +--> Query execution
    |      +--> Connections / threads / stacks
    |      +--> Metadata / allocator overhead
    |
    +--> OS filesystem page cache
    +--> Kernel allocations
    +--> Other services / agents
```

**WiredTiger cache size không phải giới hạn tổng RAM của `mongod`.** Nếu cache là 2 GiB, process có thể cần thêm RAM cho network buffers, aggregation, connections và các cấu trúc khác.

Áp lực bộ nhớ xảy ra khi working set, cache, query buffers và những thành phần khác đòi hỏi RAM vượt khả năng cấp phát/giới hạn, dẫn tới:

- Tăng eviction/page reads.
- Swap thrashing hoặc major page faults.
- Latency cao.
- OOM kill/crash.
- Container restart liên tục.

### “RAM free ít” không tự nghĩa là OOM

Linux dùng RAM cho filesystem cache. Nên xem `MemAvailable`/áp lực swap/OOM cùng workload metrics, không chỉ cột `free`. Một host có free thấp nhưng available lớn và không có eviction/OOM có thể vẫn vận hành bình thường.

## 25. Đọc nhanh memory metrics trên Linux

Các lệnh chỉ đọc:

```bash
free -h
vmstat 1 5
ps -eo pid,user,rss,vsz,%mem,%cpu,cmd | grep '[m]ongod'

# Khi có quyền đọc kernel logs:
journalctl -k --no-pager -n 100
```

Ý nghĩa:

- `free -h`: total/used/free/available, swap.
- `vmstat`: trạng thái VM, swap in/out và I/O trong khoảng quan sát.
- `ps`: RSS/process memory và CPU tương đối.
- Kernel logs: có thể ghi `Out of memory` hoặc process bị kill.

**RSS không phải toàn bộ footprint của hệ thống.** Cgroup memory accounting có thể bao gồm filesystem cache/kernel memory và phụ thuộc phiên bản cgroup. Đối với container, xem metrics của **container và host** để tránh đọc nhầm.

### Swap có phải luôn bị cấm?

Khuyến nghị swap/kernel tuning phụ thuộc MongoDB version/OS và deployment. Swap quá nhiều có thể làm latency tăng nghiêm trọng; nhưng việc tắt swap trong môi trường thiếu RAM có thể khiến OOM xảy ra sớm hơn. Điều quan trọng là sizing và production notes phù hợp, không áp dụng một mệnh lệnh chung cho mọi hệ thống.

## 26. WiredTiger cache và eviction pressure

WiredTiger sử dụng internal cache để xử lý dữ liệu/index và quản lý dirty pages. Khi working set lớn hơn cache hoặc quá nhiều dirty content:

```text
High write rate / queries
            |
            v
WiredTiger cache pressure
            |
            v
Eviction work tăng
            |
            +--> Đọc từ disk nhiều hơn
            +--> Checkpoint/flush cạnh tranh I/O
            +--> Application operations chậm
```

Các metrics và field names phụ thuộc MongoDB version/storage engine:

```javascript
const s = db.adminCommand({ serverStatus: 1 });

printjson(s.wiredTiger?.cache);
printjson(s.mem);
printjson(s.connections);
```

Đây là lệnh quan sát từ `mongosh` với role có quyền giám sát phù hợp. Không giả định mọi server/tier trả cùng fields hoặc cho phép truy cập mọi metric.

### Không tăng WiredTiger cache ngay khi query chậm

Nếu vấn đề là **cgroup memory limit thấp**, tăng cache có thể khiến OOM nhanh hơn. Nếu vấn đề là **disk full**, cache lớn không tạo thêm disk bytes. Nếu vấn đề là **index thiếu**, query scan lớn và cache thrash — cần xử lý query/index sau khi ổn định.

Khuyến nghị: đọc đúng memory limit của host/container, memory pressure, cache/evictions, process RSS và workload trước khi thay `storage.wiredTiger.engineConfig.cacheSizeGB`.

## 27. Khi `mongod` bị OOMKilled

Trong Kubernetes, Pod có thể bị restart:

```text
Last State: Terminated
Reason: OOMKilled
Exit Code: 137
```

Exit code 137 gợi ý process bị SIGKILL, nhưng **không phải chỉ từ số 137 đã chứng minh OOM**; đọc thêm `Reason`, kernel/container events và limits.

Nguyên nhân thường gặp:

- Container memory limit thấp so với workload.
- WiredTiger cache sizing không phù hợp với cgroup.
- Query aggregation/sort/group tiêu thụ RAM lớn.
- Connection/request surge.
- Nhiều workload cùng tranh RAM trên node.
- Memory leak hoặc unexpected allocation ở app/sidecars.
- Page cache/cgroup accounting làm tăng memory pressure.

### Tránh restart loop

Restart tự động không giải quyết root cause nếu cùng workload/memory limit tái diễn. Mỗi lần `mongod` restart còn có thể cần recovery/đọc data, làm tăng I/O trong lúc disk đã bận.

Hành động ưu tiên:

1. Xác minh `OOMKilled` thật.
2. Giảm workload gây đột biến.
3. Kiểm tra resource requests/limits, WiredTiger cache và host memory.
4. Mở rộng RAM/giới hạn có hỗ trợ hoặc giảm cache **theo phân tích**, không tùy tiện.
5. Bảo đảm PVC persistent và còn đủ disk headroom.
6. Theo dõi phục hồi và query latency.

## 28. Docker: memory cap khác memory bên trong process

Ví dụ container cấu hình:

```bash
docker inspect mongo-lab
docker stats mongo-lab
docker logs --tail 100 mongo-lab
```

Cần xác định:

- Container image/version.
- `HostConfig.Memory` hoặc giới hạn tương ứng.
- Cgroup CPU/memory policies.
- Volume mounts và actual `dbPath`.
- Exit status/OOM flags.

Một container có memory limit 2 GiB **không tự bảo đảm** WiredTiger cache chọn đúng cho mọi phiên bản MongoDB/runtime; giá trị mặc định liên quan đến môi trường và server version. Không sao chép hướng dẫn “cache bằng X% RAM” từ host bare-metal sang container mà không xác minh cgroup awareness của phiên bản đang chạy.

### Volume và OOM

Nếu container bị OOMKill nhưng dùng named/persistent volume đúng, storage engine có thể recovery từ dữ liệu bền vững khi process restart. Nếu dùng writable layer tạm và container bị recreate, có thêm nguy cơ mất dữ liệu. **Memory fix không thay storage durability plan.**

## 29. Kubernetes: quan sát Pod, PVC và node

Các lệnh đọc:

```bash
kubectl get pods -n mongodb
kubectl describe pod mongo-0 -n mongodb
kubectl logs mongo-0 -n mongodb --previous
kubectl top pod -n mongodb

kubectl get pvc -n mongodb
kubectl describe pvc mongo-data-mongo-0 -n mongodb
```

Tên Pod/PVC chỉ là ví dụ; lấy tên thực từ `kubectl get`. `kubectl top` cần metrics server và chỉ phản ánh một cửa sổ hiện tại.

### Phân biệt các trường hợp

| Kubernetes signal | Khả năng | Bước kiểm tra |
| --- | --- | --- |
| `OOMKilled` | Chạm memory limit | cgroup, requests/limits, cache/query load |
| `Evicted` | Node pressure hoặc policies | Node conditions/events, ephemeral storage |
| `CrashLoopBackOff` | Process restart lặp | Previous logs + last state |
| PVC `Pending` | CSI/quota/storage class/topology | `describe pvc`, events |
| Volume attach error | Zone/attachment conflict | CSI/Node scheduling/volume status |
| `No space left on device` | Filesystem/PVC/ephemeral storage | Xác định path/mount thật |
| Pod Ready nhưng DB chậm | Disk I/O/cache/queries | MongoDB metrics và app latency |

### PVC tăng size không phải lúc nào cũng tức thì

PVC expansion phụ thuộc StorageClass/CSI support, filesystem resizing và topology. Đôi khi volume expansion được thực hiện online, đôi khi cần Pod restart hoặc bước filesystem cụ thể. Đừng patch PVC size rồi coi như incidents đã giải quyết khi chưa đo lại available bytes trong Pod.

### Không xóa PVC để “reset lỗi”

Xóa PVC có thể khiến data volume bị xóa tùy reclaim policy và StorageClass. **Không dùng `kubectl delete pvc` như cleanup tạm** khi MongoDB đang có dữ liệu cần giữ.

## 30. Atlas: operator không can thiệp file nội bộ

Với MongoDB Atlas-managed deployment, operator thường không có quyền SSH/chown/xóa journal của managed MongoDB nodes. Các hướng xử lý:

- Xem Atlas metrics và alerts: storage usage, growth, CPU, memory/working set, IOPS, replication lag.
- Kiểm tra cluster tier/storage size và những giới hạn/tính năng của tier.
- Xem có autoscaling storage/compute hỗ trợ và đang bật không.
- Tăng capacity/cluster tier theo quy trình managed service khi cần.
- Giảm ingest, bulk migrations, heavy aggregation hoặc retries phía app.
- Kiểm tra backup và restore options.
- Mở support case nếu platform/storage health bất thường hoặc scaling không kịp.

Không giả định Atlas tự động tăng storage **trên mọi cluster tier**, hoặc autoscaling tăng ngay khi vượt ngưỡng. Cần xác minh cấu hình và giới hạn thực của deployment.

### Không xử lý Atlas bằng `db.repairDatabase()`

Các thao tác tự quản lý storage files/repair không được áp dụng như công thức chung cho Atlas-managed nodes. Dùng managed controls và support workflow.

## 31. Java Driver: ứng dụng thấy gì khi database thiếu tài nguyên?

Các triệu chứng:

- `MongoSocketTimeoutException`.
- `MongoTimeoutException` khi chọn server không thành công trong thời gian giới hạn.
- `MongoWriteException` cho write errors cụ thể.
- `MongoWriteConcernException` hoặc lỗi write concern.
- Command errors liên quan storage/availability.
- Connection pool saturation/wait queue timeout.
- Latency cao dù API không nhận một error code ổn định.

Các exception phụ thuộc driver/server/version, nên **không có một exception duy nhất đại diện cho “disk full” hoặc “OOM”**.

### Vì sao stack trace Java không đủ?

Một MongoDB server bị OOM kill có thể khiến client thấy connection reset — triệu chứng **network**, root cause lại là memory. Một server disk I/O nghẽn có thể khiến client timeout; tăng socket timeout chỉ làm request chờ lâu hơn, không giải quyết disk latency.

Khi incident, kết hợp:

1. Driver/server error codes và error labels.
2. Application request rate, retries, pool utilization.
3. MongoDB server logs/metrics.
4. Host/PVC/cloud storage metrics.
5. Replica set topology/health.

## 32. Retry storm làm sự cố nặng hơn

Một phản ứng nguy hiểm:

```text
MongoDB write latency tăng
        |
        v
API timeout
        |
        v
5 instances x mỗi request retry 5 lần
        |
        v
Lượng write traffic tăng nhiều lần
        |
        v
Journal/oplog/cache/CPU/disk áp lực hơn
        |
        v
More timeouts
```

**Không retry vô hạn** và không cấu hình mọi service đồng loạt retry lập tức.

Hành vi ứng dụng mong muốn:

- Exponential backoff + jitter và giới hạn attempts/deadline.
- Circuit breaker/load shedding với endpoint không thiết yếu.
- Queue bền vững cho tác vụ có thể trì hoãn, nhưng kiểm tra queue capacity/retention.
- Idempotency keys ổn định cho writes có thể retry.
- Không tự retry các non-idempotent side effects (payment/email).
- Ưu tiên những writes thiết yếu theo business policy.
- Quan sát rate-limit/rejection như một tín hiệu bảo vệ, không luôn là lỗi cần “ẩn đi”.

### Driver retryable writes khác retry vòng ngoài

Java Driver có các tính năng retryable reads/writes theo conditions phù hợp, nhưng chúng không thay hoàn toàn application idempotency. Nếu service tự retry thêm, phải tính **tổng số attempts** để tránh retry amplification.

## 33. Ví dụ Java: phản ứng an toàn với kết quả ghi mơ hồ

Giả sử ứng dụng ghi một request có unique business ID:

```java
import com.mongodb.MongoException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public final class RequestWriter {
    public static Document register(
            MongoCollection<Document> collection,
            String requestId,
            String payloadHash) {

        Document doc = new Document("_id", requestId)
            .append("payloadHash", payloadHash)
            .append("status", "RECEIVED");

        try {
            collection.insertOne(doc);
        } catch (MongoException ex) {
            // Không kết luận ngay là write chưa xảy ra.
            Document existing = collection.find(
                Filters.eq("_id", requestId)).first();

            if (existing != null &&
                payloadHash.equals(
                    existing.getString("payloadHash"))) {
                return existing; // Một dạng idempotent replay.
            }

            // Chưa thể xác định outcome hoặc payload xung đột.
            throw ex;
        }

        Document saved = collection.find(
            Filters.eq("_id", requestId)).first();
        if (saved == null) {
            throw new IllegalStateException(
                "Write acknowledged nhưng không đọc thấy record");
        }
        return saved;
    }
}
```

Đây là **mô hình ý tưởng**, không phải bộ xử lý lỗi production hoàn chỉnh:

- Phải có unique `_id`/business key và acknowledged write concern.
- Read sau lỗi cũng có thể thất bại nếu cluster chưa phục hồi.
- Một read từ secondary có thể lag; lựa chọn read preference/concern phù hợp rất quan trọng.
- Duplicate key do payload khác **không được coi là thành công**.
- Không ghi external side effects trong đoạn có thể retry nếu thiếu idempotency.
- Production cần phân loại lỗi, deadline, fallback và reconcile workflow chính thức.

Điểm mấu chốt: **khi outcome chưa rõ, không tạo request ID mới và không mù quáng lặp lại payment**.

## 34. Tạm giảm tải không đồng nghĩa giảm độ bền ghi

Một giải pháp hấp tấp là đổi `writeConcern` từ majority xuống `w:0` để ứng dụng “đỡ chờ”.

Điều này không làm disk khỏe hơn và có thể:

- Khiến client mất thông tin write success/error.
- Tăng nguy cơ không biết write đã được áp dụng hay chưa.
- Vi phạm RPO/durability contract.
- Làm business transaction thấy “thành công” khi không có acknowledgment.

**Không hạ write concern hay tắt journal chỉ để vượt qua sự cố tài nguyên** khi chưa có quyết định rủi ro dữ liệu được phê duyệt. Cách an toàn thường là giảm throughput nonessential hoặc tăng capacity/IOPS/RAM.

### Throttling cần giữ contract

Nếu hệ thống phải từ chối tạm thời, API nên trả trạng thái có thể hiểu (ví dụ 503/429 theo contract) thay vì trả 200 khi write chưa hoàn tất. Nếu đưa request vào queue, chỉ trả accepted khi queue thực sự **durably accepted** và có idempotency/expiry phù hợp.

## 35. Không restart `mongod` như hành động đầu tiên

Restart có thể hữu ích khi:

- Đã sửa lỗi mount/permission/config.
- Đã cấp thêm resources nhưng runtime cần restart mới áp dụng.
- Cần controlled restart theo runbook có quorum/backup.

Nhưng restart **không tự giải phóng disk** và có thể:

- Làm mất primary availability trong election.
- Kích hoạt crash recovery, tăng đọc/ghi disk.
- Làm mất metrics/evidence trong process.
- Tạo lặp OOM nếu memory limit không đổi.
- Khi volume mount sai, khiến database khởi động với path không mong đợi.

**Trước restart:** kiểm tra node role, replica health, backup, data path, available disk và nguyên nhân. Trên replica set, thao tác từng member theo hướng dẫn hỗ trợ.

## 36. `mongod --repair` là gì và vì sao không phải nút cứu hộ?

`--repair` tồn tại trong những tình huống recovery/self-managed đặc thù, nhưng **không phải lựa chọn đầu tiên** khi chỉ thiếu disk/memory. Nó có thể cần nhiều tài nguyên, có hạn chế theo storage/version và có rủi ro mất dữ liệu trong tình trạng corruption nghiêm trọng.

Nếu log chỉ báo `ENOSPC`, không chạy `--repair` như phản xạ. Phải:

1. Xác minh thực sự có corruption hay chỉ là thiếu tài nguyên/mount.
2. Thu thập bằng chứng và xác định backup.
3. Nếu replica set có healthy secondary, cân nhắc resync/replacement theo quy trình hỗ trợ.
4. Đối chiếu tài liệu MongoDB đúng server version.
5. Có đủ disk/RAM cho thao tác recovery.

**Không tự xóa files trong dbPath trước hoặc sau repair**. Mọi can thiệp file-level cần runbook chuyên biệt và phê duyệt.

## 37. Quy trình cứu một secondary bị đầy disk

Tình huống:

```text
Replica set:
  node-a primary healthy
  node-b secondary disk full
  node-c secondary healthy
```

Một runbook khái niệm:

1. Xác minh `node-a/node-c` còn healthy và majority.
2. Kiểm tra lag/oplog window của node-b.
3. Xác nhận data path, volume ID, quyền và nguyên nhân disk-full của node-b.
4. Nếu có thể, **tăng volume** của node-b mà không đụng data files.
5. Nếu cần restart node-b, làm theo quy trình single-member với trạng thái cluster đã xác minh.
6. Theo dõi node-b recovery, replication progress và log errors.
7. Xác nhận node-b trở lại SECONDARY và lag ổn định.
8. Kiểm tra app/quorum/backup alert về bình thường.

Nếu node-b đã mất oplog history cần thiết, có thể phải initial sync/resync. Đây là thao tác **tốn I/O/disk và có nguy cơ dữ liệu cục bộ bị thay thế**; không tự xóa `dbPath` để “resync” khi chưa có plan và secondary healthy source.

## 38. Quy trình xử lý primary sắp đầy

Tình huống nguy hiểm hơn vì primary chịu ghi:

1. Điều phối incident lead, app owner và DBA.
2. Xác định majority availability, secondary lag và các flow critical.
3. Giảm ingest/retry không thiết yếu ngay nếu tốc độ cạn tài nguyên cao.
4. Mở rộng primary storage/IOPS nếu có phương án online an toàn.
5. Nếu cần failover/stepdown, chỉ làm khi healthy secondaries đủ điều kiện và change được duyệt.
6. Tránh **election loop** do stepdown lặp hoặc members khác cũng thiếu tài nguyên.
7. Xác nhận primary mới/retained, write concern và application write results.
8. Đối soát dữ liệu những requests có timeout/unknown outcome.

Không nên ra lệnh `rs.stepDown()` theo thói quen khi chưa nhìn topology. Một secondary có thể đang lag hoặc cũng đầy; failover sang node yếu không giúp hệ thống phục hồi.

## 39. Thứ tự khôi phục khi cả disk và RAM đều thiếu

Một tình huống kết hợp:

```text
Disk free thấp
WiredTiger dirty pages / eviction tăng
OS memory pressure
Ứng dụng retry storm
```

Trật tự hợp lý:

1. **Ngăn tạo thêm tải**: giới hạn ingest và retries không thiết yếu.
2. **Giữ tính toàn vẹn dữ liệu**: không xóa files/index/journal/oplog.
3. **Xác định giới hạn nào đang chạm hard failure**: disk bytes/inodes, read-only storage, cgroup OOM, IOPS.
4. **Tăng headroom cho hard limit**: capacity/volume trước nếu disk đã không thể ghi; RAM/limit khi OOM thật.
5. **Phục hồi service từng node**, tránh tăng restart volume và retry traffic.
6. **Quan sát cải thiện**: disk latency, cache eviction, RSS, replica health, API success.
7. Sau ổn định mới tune cache/index/query/retention.

Không có quy tắc “luôn tăng RAM trước” hay “luôn tăng disk trước”. **Ưu tiên hard blocker đang đe dọa durability/availability** và chọn can thiệp ít phá hủy nhất.

## 40. Sự cố đầy ổ do backup/export trên cùng filesystem

Giả sử:

```text
/var/lib/mongodb   90 GiB data
/var/lib/mongodb/backups  20 GiB dump tạm
Filesystem        100 GiB
```

Đây là thiết kế không tốt: backup archive đang chiếm cùng filesystem như data. Trong incident, không vội xóa bản dump nếu nó là bản duy nhất hoặc đang được upload. Hãy:

1. Xác minh file backup thuộc job nào và trạng thái hoàn tất.
2. Xác minh backup ở destination khác có bản được kiểm chứng không.
3. Nếu là **artifacts tạm ngoài data files** và có thể xóa theo policy, thực hiện cleanup có kiểm soát.
4. Chuyển chiến lược backup sang destination riêng, tránh ghi archive tạm lên data volume.
5. Theo dõi backup job và disk headroom trước lần chạy tiếp theo.

Một storage path nằm **bên dưới `dbPath`** nhưng không thuộc WiredTiger vẫn nguy hiểm nếu thao tác nhầm. Tốt nhất thiết kế backup path độc lập ngay từ đầu.

## 41. Sự cố vì index build hoặc migration

Một deploy tạo nhiều indexes mới trên collection lớn có thể:

- Tăng disk consumption.
- Gây load CPU/RAM/I/O.
- Cạnh tranh với writes/queries.
- Làm secondary lag hoặc tăng write latency theo workload.

### Điều tra

1. Xem recent schema migrations/deploys.
2. Kiểm tra index sizes và index build status bằng metrics/commands được hỗ trợ.
3. Đánh giá có operations chạy đồng thời không.
4. Tạm dừng **jobs tiếp theo** khi có thể mà không can thiệp nguy hiểm vào operation hiện hành.
5. Tăng capacity/IOPS hoặc lập kế hoạch index builds theo windows phù hợp.

Không dùng `killOp` hoặc drop index một cách mù quáng trên production. Việc hủy một index build đang chạy có semantics/impact tùy version; cần đánh giá cùng DBA và backup/recovery strategy.

## 42. Sự cố vì query/aggregation gây memory pressure

Một query:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $group: { _id: "$customerId", total: { $sum: "$amount" } } },
  { $sort: { total: -1 } }
]);
```

có thể cần nhiều memory tùy số documents/groups/indexes.

### Khi server đang OOM

Không mặc định bật `allowDiskUse:true` là giải pháp:

- Nó có thể cho phép một số aggregation stages ghi temporary files ra disk.
- Nếu **disk cũng gần đầy hoặc I/O nghẽn**, disk spill có thể làm sự cố nặng hơn.
- Một số operators có restrictions/limits riêng.

Ưu tiên:

1. Xác định endpoint/batch job phát sinh query nặng.
2. Tạm dừng/throttle job nếu noncritical.
3. Kiểm tra query plan/index sau khi service đủ khỏe.
4. Cân nhắc pre-aggregation, pagination, projection, limit hoặc thay data model.
5. Đo cache/memory/disk spill và capacity trước khi bật tính năng sử dụng disk.

## 43. Khi Java app thiếu RAM, không phải mongod

Một luồng nghiệp vụ:

```text
MongoDB server khỏe
    |
    v
Java service tải 3 triệu documents vào List
    |
    v
JVM heap OOM
    |
    v
API crash / retry / reconnect
```

Đây là **lỗi client-side**, không phải thiếu WiredTiger cache.

Trong Java:

- Dùng cursor/streaming hoặc bounded pagination.
- Không gọi `into(new ArrayList<>())` trên tập không giới hạn.
- Dùng projections để giảm bytes/objects.
- Đặt batch size và concurrency theo memory budget.
- Giải phóng cursor/client resources đúng lifecycle.
- Đo JVM heap/GC, thread pools, connection pools.

Nếu chỉ tăng memory cho `mongod`, lỗi JVM heap vẫn còn. Incident triage phải xác định **process nào** bị OOM.

## 44. Sự cố connection pool và retry backpressure

Driver connection pool cạn có thể biểu hiện như server chậm:

```text
API requests tăng
    |
    v
Threads chờ MongoDB connections
    |
    v
Wait queue timeouts
    |
    v
Retries / fan-out tăng
```

Nguyên nhân có thể là MongoDB response chậm do disk I/O, nhưng cũng có thể do application mở quá nhiều clients, leak cursors, workload fan-out hoặc thread pool sizing.

### Chẩn đoán

- Xem pool utilization và wait times của driver.
- Đo active operations trên server với quyền monitoring phù hợp.
- Đọc request rates, queue lengths và latencies.
- Phân biệt **server timeout**, **socket timeout** và **pool wait timeout**.
- Giảm concurrency khi server không còn throughput, thay vì chỉ tăng max pool size.

Tăng connection pool không tự làm server có thêm IOPS/RAM. Quá nhiều connections còn tiêu thụ memory và file descriptors.

## 45. Kiểm tra MongoDB metrics khi server còn phục vụ

Với `mongosh` và role monitoring phù hợp:

```javascript
const status = db.adminCommand({ serverStatus: 1 });

printjson(status.uptime);
printjson(status.connections);
printjson(status.mem);
printjson(status.wiredTiger?.cache);

const info = db.getSiblingDB("appdb").stats();
printjson({
  dataSize: info.dataSize,
  storageSize: info.storageSize,
  indexSize: info.indexSize
});
```

Trong replica set:

```javascript
rs.status();
```

Hoặc:

```javascript
db.adminCommand({ replSetGetStatus: 1 });
```

### Cẩn trọng với metrics trong incident

- Một số commands không hoạt động trên `mongos` hoặc khi member không healthy.
- Field names/availability tùy MongoDB version.
- `serverStatus` rất lớn; khi incident chỉ lấy fields cần.
- `db.stats()` cho logical/storage metrics nhưng không phải thay `df` cho available bytes.
- Secondary lag/majority status cần đọc ở đúng topology và thời điểm.
- Không dùng lệnh profiling toàn bộ workload hoặc full collection scan khi server đã quá tải.

## 46. Cách diễn giải `db.stats()` so với `df -h`

Giả sử:

```text
db.stats().dataSize    = 50 GiB
db.stats().storageSize = 28 GiB
db.stats().indexSize   = 8 GiB
df used                = 70 GiB
```

Không cần coi các số này “mâu thuẫn”:

- `dataSize` phản ánh logical data size theo semantics server.
- `storageSize` phản ánh storage allocated cho collections theo engine.
- `indexSize` phản ánh index storage.
- Filesystem còn có journal, oplog, logs, backup/export, metadata, snapshots và các file không thuộc database stats.
- Compression và storage reuse khiến logical size khác physical size.

**Không lấy `dataSize + indexSize` làm phép tính duy nhất cho dung lượng host.** Khi root cause disk-full, filesystem/volume metrics là nguồn trực tiếp cho available capacity; MongoDB metrics giúp giải thích data growth.

## 47. Phục hồi xong: xác nhận gì?

Chỉ thấy `mongod` process chạy lại **chưa đủ**. Cần kiểm tra:

| Lớp | Xác nhận |
| --- | --- |
| Filesystem | Bytes/inodes free có headroom, mount đúng, không read-only |
| Disk | Latency/queue/IOPS ổn định |
| Memory | Không còn OOM loop, RSS/cache/evictions phù hợp |
| MongoDB process | Không có startup/recovery errors mới |
| Replica set | Healthy members, primary, majority, lag giảm |
| Sharding | Shards/config servers/routers khỏe, routing bình thường |
| Application | Reads/writes nghiệp vụ thành công |
| Durability | Write concern đúng, không hạ bảo đảm ngầm |
| Idempotency | Không tạo request/payment trùng sau retry |
| Backups | Backup jobs tiếp tục và restore strategy còn hợp lệ |
| Alerts | Incident alerts thực sự trở về mức bình thường |

### Test dữ liệu nghiệp vụ

Ví dụ:

- Đọc một đơn hàng tồn tại trước incident.
- Tạo thử một record an toàn theo workflow/fixture được phép và xác nhận acknowledgment.
- Kiểm tra read-after-write theo consistency contract.
- Đối soát các request nhận timeout/unknown outcome.
- Kiểm tra consumers/change streams nếu ứng dụng có CDC.

Không chạy một test destructive hoặc chèn test data vào production thật nếu không có policy và cleanup rõ ràng.

## 48. Dữ liệu đã ACK có thể mất không?

Điều này phụ thuộc:

- `writeConcern` (`w:1`, `majority`, `j:true` theo semantics version).
- Replica set topology/majority health.
- Storage backend durability.
- Failover timing/rollback scenarios.
- Transaction/application behavior.

**Không suy từ “client timeout” rằng write chắc chắn chưa được áp dụng.** Cũng không suy từ “w:1 ACK” rằng write luôn sống sót qua mọi failover. Khi có sự cố tài nguyên, hệ thống phải giữ nguyên RPO/business contract và thiết kế idempotent reconciliation cho những operations không rõ kết quả.

### Retry reconciliation

Một bảng xử lý nghiệp vụ có thể là:

| Kết quả client | Hành động an toàn hơn |
| --- | --- |
| Write acknowledged | Theo semantics ACK/transaction, cập nhật trạng thái |
| Duplicate key cùng idempotency key | Đọc existing record, so payload/result |
| Timeout không rõ outcome | Đọc theo stable ID, không tạo ID mới ngay |
| Write concern timeout | Có thể đã applied; đối soát trước retry |
| Authorization/validation error | Sửa quyền/schema, không retry mù |
| Server unavailable | Giới hạn attempts, backoff, queue/reject theo policy |

## 49. Ưu tiên theo RPO/RTO, không chỉ phần trăm dung lượng

**RPO (Recovery Point Objective)** là mức mất dữ liệu tối đa chấp nhận được theo thời gian/trạng thái. **RTO (Recovery Time Objective)** là thời gian dịch vụ cần được phục hồi.

Ví dụ:

```text
Ứng dụng A:
  RPO ~ 0 cho thanh toán đã xác nhận
  RTO 15 phút

Ứng dụng B:
  Tác vụ analytics có thể chạy lại
  RPO vài giờ
  RTO vài giờ
```

Khi cả hai cùng tác động tới MongoDB, cần ưu tiên resource cho A và giảm/tạm dừng B theo quy trình phê duyệt.

**Không hy sinh dữ liệu đã ACK chỉ để làm latency dashboard đẹp hơn.** Nếu sự cố yêu cầu ngừng tiếp nhận writes, phải truyền trạng thái rõ ràng tới upstream và có cơ chế replay/bảo đảm không thất lạc yêu cầu.

## 50. Sizing headroom dựa trên tốc độ tăng

Một biểu đồ disk 85% không đủ để biết nguy hiểm. Cần đo:

```text
Available capacity = A GiB
Net growth rate    = G GiB/giờ

Thời gian dự báo tới khi hết chỗ ≈ A / G
  (nếu G > 0 và xu hướng giữ nguyên)
```

Ví dụ:

```text
Volume còn 80 GiB
Tốc độ tăng ròng 20 GiB/giờ
=> khoảng 4 giờ theo giả định tuyến tính
```

Đây chỉ là **ước lượng điều hành**, không phải mô hình dự báo chắc chắn:

- Bulk import có thể tăng đột biến.
- Index build làm disk tăng không đều.
- Backups/compaction/recovery cần temporary space.
- TTL/delete không giải phóng OS bytes ngay.
- Storage autoscaling có độ trễ và giới hạn.

Alert nên so **time-to-full** với thời gian cần cấp thêm volume/can thiệp và RTO, không chỉ một threshold cố định như 90%.

### Disk performance headroom

Ngay cả khi còn capacity, cần chừa performance headroom cho failover, backup, initial sync và traffic peaks. Volume chạm ngưỡng throughput/IOPS liên tục có thể gây incident trước khi `df` báo đầy.

## 51. Bộ chỉ số cảnh báo khuyến nghị

| Nhóm | Signal | Mục đích |
| --- | --- | --- |
| Capacity | Free bytes/inodes, projected time-to-full | Cảnh báo trước ENOSPC |
| Storage | I/O latency, queue depth, IOPS/throughput | Phát hiện bão hòa |
| Filesystem | Read-only remount, kernel I/O errors | Phát hiện backend corruption/failure |
| Memory | RSS, cgroup usage/limit, OOM events | Tránh crash loops |
| WiredTiger | Cache dirty/eviction/reads, checkpoint behavior | Hiểu pressure bên trong |
| Process | Restart count, crash logs | Chẩn đoán availability |
| Replica set | Member states, lag, majority, oplog window | Bảo vệ consistency/availability |
| Workload | Write rate, query latency, retry rate | Tìm nguồn gây pressure |
| App | Pool wait, timeouts, 5xx, queue depth | Đánh giá trải nghiệm khách hàng |
| Backups | Last successful backup, restore drills | Đảm bảo recovery |
| Change streams | Resume lag/history-loss errors | Bảo vệ CDC |
| Capacity changes | Autoscale failures, PVC resize events | Xác nhận remediation thật sự áp dụng |

Không có một con số ngưỡng đúng cho mọi deployment. Alert nên gắn với **baseline, tốc độ tăng, thời gian ứng cứu, topology và criticality**.

## 52. Bảng “nên làm / tránh làm” khi khẩn cấp

| Triệu chứng | Nên làm trước | Tránh làm |
| --- | --- | --- |
| `df` gần 100% | Giảm ingest, xác minh volume, tăng capacity | Xóa WiredTiger/journal |
| `df -i` đầy | Kiểm tra inode/quota, tìm file sources | Chỉ tăng GiB rồi thôi |
| Filesystem read-only | Xem kernel/storage errors, escalations | Ép read-write không điều tra |
| Disk latency cao | Kiểm tra IOPS/queue/cloud limits | Chỉ tăng vCPU |
| Secondary disk full | Đánh giá quorum/lag, resize member | Restart cả replica set |
| Primary disk full | Bảo vệ majority, giảm writes, resize | Stepdown mù quáng |
| `OOMKilled` | Xem cgroup/cache/RSS/workload | Restart loop liên tục |
| RAM free thấp | Xem available/swap/evictions | Kết luận OOM chỉ từ free |
| Aggregation spill | Giảm query load, kiểm tra disk headroom | Bật disk spill vô điều kiện |
| Large TTL/delete backlog | Lập batch cleanup sau ổn định | Xóa hàng triệu rows khẩn cấp |
| Error timeout | Giữ idempotency key, reconcile | Retry vô hạn với ID mới |
| Atlas capacity alert | Xem scaling/metrics/support | SSH/xóa file managed node |
| PVC gần đầy | Kiểm tra CSI expansion support | Xóa PVC để “reset” |
| Index build pressure | Hoãn jobs tiếp theo, plan capacity | Drop index không review |

## 53. Bài tập thực hành có đáp án

### Bài 1. Disk đầy, lệnh đầu tiên?

Primary MongoDB báo filesystem 100%. Một người đề xuất `rm -rf /var/lib/mongodb/journal` để có chỗ. Có nên làm không?

**Đáp án:** Không. Journal là state nội bộ cần cho durability/recovery. Ưu tiên giảm write pressure, xác minh volume và mở rộng storage an toàn.

### Bài 2. Dung lượng còn, vẫn lỗi ENOSPC

`df -h` còn 20 GiB nhưng một số thao tác tạo file thất bại. Kiểm tra gì tiếp?

**Đáp án:** `df -i`, filesystem quota, read-only remount, storage backend và mount path; không chỉ nhìn bytes.

### Bài 3. Disk lớn nhưng query chậm

Volume còn 60% free nhưng I/O latency tăng mạnh. Tăng dung lượng chắc giải quyết?

**Đáp án:** Không chắc. Có thể chạm IOPS/throughput limit hoặc queue depth; cần đo performance và cloud volume settings.

### Bài 4. Mount sai

Sau reboot, `/var/lib/mongodb` nằm trên root filesystem vì data disk chưa mount. Có nên để mongod ghi tiếp?

**Đáp án:** Không nên khi chưa xác minh data path. Cần khôi phục mount đúng, kiểm tra volume ID và đánh giá dữ liệu có thể bị ghi nhầm.

### Bài 5. Delete rất nhiều documents

DBA chạy `deleteMany()` hàng triệu docs để cứu filesystem sát đầy. Vì sao nguy hiểm?

**Đáp án:** Delete tạo writes/oplog và có thể không trả OS disk bytes ngay; tăng I/O pressure. Cần headroom/retention plan.

### Bài 6. TTL

Vừa tạo TTL index, tất cả expired docs sẽ biến mất lập tức và `df` giảm ngay?

**Đáp án:** Không. TTL asynchronous; WiredTiger có thể tái sử dụng file space thay vì trả ngay cho OS.

### Bài 7. Compact

Node đang 99% disk, I/O saturating. Có nên chạy `compact` để thu nhỏ file?

**Đáp án:** Không coi là cứu hỏa mặc định. Compact có thể cần thêm space và I/O, làm tải xấu hơn. Phục hồi headroom trước.

### Bài 8. Oplog

Một secondary lag 20 phút; operator muốn giảm oplog size mạnh để tiết kiệm disk. Rủi ro?

**Đáp án:** Giảm oplog window có thể làm secondary không bắt kịp và CDC mất history, dẫn tới initial sync hoặc rebootstrap.

### Bài 9. Quorum

Replica set ba members, một secondary đã offline, primary sắp đầy. Có nên tắt primary để “nghỉ” ngay?

**Đáp án:** Rất nguy hiểm nếu tắt làm mất majority. Phải xác minh topology, giảm tải và chọn thay đổi giữ quorum.

### Bài 10. Primary vs secondary

Ba-node replica set: primary khỏe, một secondary đầy, secondary còn lại khỏe. Nên xử lý thế nào?

**Đáp án:** Tập trung khôi phục secondary bị đầy và kiểm tra lag/oplog, không restart toàn bộ cluster.

### Bài 11. Atlas

Atlas cluster báo disk capacity alert. Có nên tìm đường SSH vào node để xóa WiredTiger files?

**Đáp án:** Không. Dùng Atlas metrics/scaling/backup/support và giảm workload; managed nodes không vận hành bằng cách xóa file nội bộ.

### Bài 12. OOMKilled

Kubernetes Pod last state `OOMKilled`, memory limit chỉ 2 GiB. Tăng cacheSizeGB lên 4 GiB có tốt?

**Đáp án:** Không; dễ làm tình hình xấu hơn. Đánh giá memory cap, WiredTiger cache, RSS, workload và sizing phù hợp.

### Bài 13. Linux free memory

Linux báo free RAM gần 0 nhưng MemAvailable còn lớn, không có swap/OOM. Có đủ kết luận memory incident không?

**Đáp án:** Chưa. Linux dùng page cache; cần xem pressure/evictions/RSS/latency và các signals khác.

### Bài 14. Restart loop

MongoDB container bị OOMKilled và tự khởi động lại mỗi phút. Chỉ tăng số retries ứng dụng có giúp không?

**Đáp án:** Không; retry storm có thể tăng tải. Cần giảm workload, sửa memory/cgroup/cache sizing và khôi phục có kiểm soát.

### Bài 15. App OOM

MongoDB khỏe nhưng Java API gọi `find().into(new ArrayList<>())` trên hàng triệu documents rồi JVM OOM. Root cause?

**Đáp án:** Client-side unbounded materialization. Dùng cursor/projection/bounded processing thay vì tăng WiredTiger cache.

### Bài 16. Aggregation

Server memory pressure và disk cũng gần đầy. Bật `allowDiskUse:true` cho mọi aggregation có an toàn không?

**Đáp án:** Không. Disk spill có thể làm tăng storage/I/O pressure. Cần giảm query load, thiết kế index/pipeline sau ổn định và đánh giá headroom.

### Bài 17. Timeout

Client nhận write timeout, lập tức tạo ID mới và insert lại cùng request thanh toán. Rủi ro?

**Đáp án:** Write đầu có thể đã thành công, tạo duplicate business operation. Dùng stable idempotency key và reconcile.

### Bài 18. Write concern

Để giảm latency khi disk bận, team đổi `w:majority` sang `w:0`. Tại sao không nên làm bừa?

**Đáp án:** Đánh mất acknowledgment và thay RPO/durability contract, không giải quyết I/O; dễ không biết operation đã thành công hay chưa.

### Bài 19. Backup lên cùng disk

`mongodump --out` ghi vào data volume đang gần đầy. Có giúp khôi phục an toàn?

**Đáp án:** Có thể làm disk đầy nhanh hơn; backup cần destination/quy trình nhất quán và không dùng chung volume gây pressure.

### Bài 20. Read-only filesystem

Filesystem tự remount `ro` sau I/O errors. Một người muốn sửa bằng `chmod 777`. Đúng không?

**Đáp án:** Không. Read-only/storage error khác ownership. Cần điều tra backend/kernel/filesystem theo thủ tục vendor.

### Bài 21. Cloud resize

Cloud volume đã tăng từ 100 lên 200 GiB nhưng `df -h` vẫn thấy 100 GiB. Có nhất thiết MongoDB lỗi?

**Đáp án:** Không. Partition/filesystem có thể chưa được grow; cần xác minh volume, LVM/partition/filesystem và thủ tục được hỗ trợ.

### Bài 22. PVC

Kubernetes StatefulSet dùng PVC. Operator đề xuất `kubectl delete pvc` để tạo volume mới, tránh crash. Rủi ro?

**Đáp án:** Có thể mất data volume tùy PV reclaim policy; không dùng xóa PVC như reset không có backup/recovery plan.

### Bài 23. Performance

Sau tăng RAM cho mongod, query vẫn chậm vì disk I/O queue dài. Điều gì cần xem?

**Đáp án:** Bottleneck IOPS/throughput, query plans/indexes và workload; tăng RAM không tự tăng disk performance.

### Bài 24. Replica set đồng loạt

Ba members cùng gần đầy. Có nên stepdown primary vì hai secondaries cũng có thể thành primary?

**Đáp án:** Không mặc định. Failover sang node cũng gần đầy không cứu capacity và có thể gây election churn. Giảm ingest và tăng headroom có kế hoạch.

### Bài 25. Time-to-full

Volume còn 40 GiB, net growth 10 GiB/h. Theo tuyến tính còn bao lâu?

**Đáp án:** Khoảng 4 giờ nếu tốc độ không đổi. Cần cộng dự phòng cho index builds/backups và thời gian can thiệp; không coi đây là cam kết chắc chắn.

### Bài 26. p99 và OOM

Memory free thấp, p99 cao, nhưng không có OOM và disk latency rất cao. Kết luận chắc là thiếu RAM?

**Đáp án:** Chưa đủ. Có thể nghẽn disk hoặc query pattern, cần đối chiếu cache/evictions/RSS/OS pressure.

### Bài 27. Logs

Một log đã được `rm` nhưng disk usage không giảm. Vì sao?

**Đáp án:** Process có thể vẫn giữ file descriptor mở. Cần kiểm tra deleted-but-open files và dùng log rotation/reopen an toàn, không restart primary mù quáng.

### Bài 28. Incident closure

Sau restart, `ping` trả 1. Có thể đóng incident ngay?

**Đáp án:** Chưa. Cần xác nhận mounts/capacity, latency, memory, replica health, business reads/writes và những requests có kết quả mơ hồ.

### Bài 29. Sharded cluster

Một config server member đầy disk nhưng shard data nodes còn nhiều chỗ. Có thể bỏ qua vì dữ liệu ứng dụng nằm ở shards?

**Đáp án:** Không. Config server replica set giữ metadata quan trọng; sự cố có thể ảnh hưởng cluster operations/availability. Cần runbook theo topology.

### Bài 30. Hành động ít phá hủy

Có hai phương án: (A) mở rộng volume đã xác minh đúng mount theo thủ tục hỗ trợ; (B) xóa các file WiredTiger không rõ chức năng. Chọn gì?

**Đáp án:** Ưu tiên A, cùng đánh giá backup/rollback và quorum. B có nguy cơ corruption/mất dữ liệu.

## 54. Bảng checklist dành cho người trực vận hành

### Triage

- [ ] Xác nhận môi trường, server version và topology.
- [ ] Xác định member role/majority trước mọi restart/stepdown.
- [ ] Ghi lại incident timestamp, request errors và recent changes.
- [ ] Xác định `dbPath`, mount, PV/volume ID thực tế.
- [ ] Đo bytes, inodes, quota, read-only status và disk latency.
- [ ] Đo RSS/cgroup memory, OOM events, WiredTiger cache pressure.
- [ ] Phân biệt mongod OOM với JVM/application OOM.
- [ ] Xác định backup/recovery options và RPO/RTO.

### Giảm tác hại

- [ ] Hoãn ingest/index builds/analytics jobs không thiết yếu.
- [ ] Giảm retries không kiểm soát, dùng backoff/jitter.
- [ ] Duy trì business idempotency keys và write acknowledgment contract.
- [ ] Không xóa journal/oplog/WiredTiger data files.
- [ ] Không xóa PVC/volume hay drop indexes/collections theo phản xạ.
- [ ] Không dùng `compact`/`--repair` khi chưa xác định đúng mục đích.
- [ ] Không restart đồng loạt MongoDB members.

### Khôi phục

- [ ] Chọn phương án mở rộng capacity/IOPS/RAM ít phá hủy nhất.
- [ ] Chỉ cleanup artifacts ngoài dbPath đã xác minh theo retention.
- [ ] Xử lý từng replica set member, giữ majority.
- [ ] Đối chiếu giới hạn resource với cgroup/StorageClass/Atlas tier.
- [ ] Kiểm tra `df`, memory pressure và I/O sau thay đổi.
- [ ] Xác nhận replica health, lag, startup/recovery logs.
- [ ] Thử read/write nghiệp vụ theo policy và đối soát ambiguous outcomes.

### Sau incident

- [ ] Theo dõi time-to-full và cloud autoscaling limits.
- [ ] Xem lại quota/IOPS/cache/query/index/TTL retention.
- [ ] Kiểm tra backup/restore drills và CDC oplog window.
- [ ] Đặt alerts theo growth slope, latency, OOM, replication lag.
- [ ] Phân tích retry amplification và capacity headroom khi failover.
- [ ] Viết postmortem về root cause, quyết định và các safeguards.

## 55. Postmortem: cải thiện để không lặp lại

Một postmortem nên tránh dừng ở kết luận **“disk đầy, đã tăng disk”**. Nó cần trả lời:

1. **Tại sao** dữ liệu tăng nhanh hơn dự báo?
2. Có ingest/job/index build nào mới được deploy trước incident?
3. Alert có tới đủ sớm so với thời gian cần cấp thêm storage không?
4. Tại sao autoscale hoặc quota không giúp?
5. Vì sao failover/quorum tạo hay không tạo availability?
6. Ứng dụng có retry storm hoặc trả success khi write outcome chưa rõ không?
7. Có mất dữ liệu/duplicate operations nào cần reconcile không?
8. Backup/restore có đáp ứng RPO/RTO không?
9. Những thao tác khẩn cấp nào từng được đề xuất nhưng có nguy cơ phá dữ liệu?
10. Cần thay đổi gì trong deployment, capacity budgets, monitoring, ownership và runbook?

### Hành động phòng ngừa theo tầng

| Tầng | Cải thiện |
| --- | --- |
| Product/app | Rate limits, queue budgets, idempotency, retry budget |
| MongoDB query | Indexes phù hợp, bounded aggregation, avoid full scans |
| Data lifecycle | TTL/retention có kiểm soát, partition/archive policy |
| Storage | Capacity/IOPS headroom, autoscale limits, multi-zone failure domains |
| Memory | Cache sizing theo runtime, cgroup requests/limits, connection budgets |
| Replica | Lag/oplog window, staged recovery, tested failover |
| Observability | Free bytes + time-to-full + latency + OOM + user impact |
| Operations | Change review, verified backup, restore drill, safe incident actions |

## 56. Tổng kết

Khi MongoDB gặp **đầy ổ đĩa**, **áp lực bộ nhớ** hoặc **I/O bão hòa**, điều quan trọng nhất không phải tìm một lệnh làm biểu đồ đỏ chuyển xanh nhanh nhất. Mục tiêu ưu tiên là **bảo toàn dữ liệu đã được xác nhận, tránh phá replica set/quorum, giới hạn nguồn tải làm sự cố xấu đi và khôi phục đúng lớp tài nguyên đang thiếu**.

Hãy phân biệt đầy bytes, hết inodes/quota, filesystem read-only và disk latency cao. Đối với RAM, phân biệt cache pressure, JVM OOM, MongoDB OOM/cgroup limits và OS page cache. Không xóa file WiredTiger/journal/oplog hoặc xóa PVC, không dùng `compact`/`--repair`/restart toàn cluster theo phản xạ. Thường nên giảm ingest/retry không thiết yếu, xác nhận mount/volume và mở rộng capacity/IOPS/RAM qua đường được hỗ trợ trước khi tối ưu sâu.

Sau khi tài nguyên có headroom, **service chạy lại chưa đồng nghĩa sự cố đã kết thúc**. Cần xác nhận replication, write concern, latency, application reads/writes và những operations có kết quả không rõ do timeout. Về dài hạn, cảnh báo theo **time-to-full**, memory/OOM, I/O latency, retry rate và tested backups giúp giảm rủi ro trước khi một ngưỡng kỹ thuật trở thành sự cố dữ liệu.

### Tài liệu tham khảo chính thức theo phiên bản

- [MongoDB Manual — Production Notes](https://www.mongodb.com/docs/manual/administration/production-notes/)
- [MongoDB Manual — Configuration Options](https://www.mongodb.com/docs/manual/reference/configuration-options/)
- [MongoDB Manual — WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/)
- [MongoDB Manual — Journaling](https://www.mongodb.com/docs/manual/core/journaling/)
- [MongoDB Manual — Replica Set Operations](https://www.mongodb.com/docs/manual/replication/)
- [MongoDB Manual — Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/)
- [MongoDB Manual — serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/)
- [MongoDB Manual — db.stats()](https://www.mongodb.com/docs/manual/reference/method/db.stats/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — compact](https://www.mongodb.com/docs/manual/reference/command/compact/)
- [MongoDB Atlas — Monitor Clusters](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/)
- [Kubernetes Documentation — Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [Kubernetes Documentation — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
