# Lưu trữ bền vững, quyền thư mục và giới hạn tài nguyên môi trường chạy trong MongoDB

Một ứng dụng Java có thể kết nối MongoDB thành công, ghi dữ liệu trong nhiều ngày và vượt qua tất cả bài kiểm tra chức năng, nhưng vẫn mất dữ liệu khi container bị tạo lại, không thể khởi động sau khi chuyển volume sang máy mới, hoặc liên tục bị hệ điều hành dừng tiến trình vì thiếu bộ nhớ. Các lỗi này thường không nằm ở lệnh `insertOne()` hay ở thiết kế collection; chúng xuất phát từ **môi trường vận hành MongoDB**.

Trong chương **Vận hành và nâng cấp** của module **Database Engine Document MongoDB**, bài này tập trung vào ba nhóm trách nhiệm:

1. **Lưu trữ bền vững:** bytes của database, journal, metadata, index và log nằm ở đâu; khi container hoặc host thay đổi thì dữ liệu còn không; khi crash có thể khôi phục thế nào.
2. **Quyền thư mục:** tài khoản hệ điều hành thực thi `mongod` phải có quyền phù hợp với `dbPath`, thư mục log và các file cấu hình; quyền không được mở rộng quá mức chỉ để vượt qua lỗi `Permission denied`.
3. **Giới hạn tài nguyên:** disk capacity, IOPS, CPU, RAM, WiredTiger cache, file descriptors, container limits, filesystem và cơ chế scheduling ảnh hưởng độ ổn định của MongoDB ra sao.

Bài cũng giải thích những khác biệt quan trọng giữa triển khai **Linux VM/bare metal**, **Docker/Compose**, **Kubernetes** và **MongoDB Atlas**, kèm ví dụ cấu hình, cách chẩn đoán, runbook và bài tập.

> **Phạm vi và an toàn:** các lệnh liên quan tới `chown`, `chmod`, mount, systemd, Docker volume, PVC hoặc nâng cấp dịch vụ chỉ là hướng dẫn/ ví dụ cho môi trường được phép quản trị. Không chạy thay đổi quyền, `docker compose down -v`, xóa file database hay restart cluster production nếu chưa kiểm tra backup, topology, owner của volume và kế hoạch rollback.

## 1. Ba khái niệm cần phân biệt ngay

| Thuộc tính | Câu hỏi cần trả lời | Dấu hiệu khi sai |
| --- | --- | --- |
| **Persistence** | Dữ liệu còn sau khi process/container bị thay thế không? | Container mới lên nhưng database trống |
| **Durability** | Những write đã được xác nhận có thể sống sót qua lỗi nào? | Crash/failover làm mất một số write |
| **Availability** | Khi một node chết, hệ thống còn phục vụ không? | Database không truy cập được dù dữ liệu trên disk còn |

Ba thuộc tính liên quan nhưng **không đồng nghĩa**:

- Một **persistent volume** giúp lưu bytes ngoài vòng đời container, nhưng không tự bảo đảm `writeConcern: "majority"` hoặc backup.
- Một **replica set** giúp chịu lỗi node và có thể tăng độ bền của write theo chính sách xác nhận, nhưng nếu ứng dụng đặt dữ liệu trên volume tạm hoặc xóa nhầm toàn bộ deployment, replica set không thay thế backup.
- Một bản **backup** có thể khôi phục dữ liệu nhưng không đảm bảo hệ thống luôn sẵn sàng trong lúc restore.
- Một MongoDB container đang chạy và trả `ping: 1` không chứng minh nó có persistent storage hoặc còn đủ disk space.

### Sơ đồ lớp lưu trữ

```text
Ứng dụng
   |
   | BSON reads/writes
   v
MongoDB mongod
   |
   +--> WiredTiger cache trong RAM
   |
   +--> data files / indexes
   +--> journal và metadata cần thiết
   |
   v
dbPath bên trong môi trường chạy
   |
   +--> VM/bare metal: mounted filesystem
   |
   +--> Docker: named volume / bind mount
   |
   +--> Kubernetes: PVC -> PV -> storage backend
   |
   v
Storage device / block volume
   |
   +--> Disk controller, filesystem, flush semantics
   +--> Snapshot/backup (phải được tổ chức riêng)
```

Mỗi lớp có thể hỏng theo cách khác nhau. Khi điều tra, cần xác định lỗi phát sinh ở **process**, **filesystem**, **container mount**, **storage backend** hay **replication/backup**.

## 2. `storage.dbPath` là gì?

MongoDB tự quản lý sử dụng `storage.dbPath` để chỉ thư mục đặt dữ liệu của tiến trình `mongod`.

Ví dụ một cấu hình Linux:

```yaml
# Một phần mongod.conf dùng để minh họa.
storage:
  dbPath: /var/lib/mongodb
  journal:
    enabled: true

systemLog:
  destination: file
  path: /var/log/mongodb/mongod.log
  logAppend: true

net:
  bindIp: 127.0.0.1
  port: 27017
```

Ở đây:

- `/var/lib/mongodb` là thư mục **dữ liệu** được chọn cho deployment.
- `/var/log/mongodb/mongod.log` là **file log**; nó khác data files.
- `dbPath` không phải connection string hay database name.
- Những đường dẫn thực phụ thuộc package, container image và cấu hình. Không đoán rằng mọi máy đều dùng `/var/lib/mongodb`.

Các bản MongoDB hiện đại sử dụng **WiredTiger** cho phần lớn triển khai phổ biến; cấu hình và hỗ trợ cụ thể phụ thuộc phiên bản. Những file bên trong `dbPath` thuộc trách nhiệm của storage engine và server.

**Không coi `dbPath` là một thư mục chứa các JSON files có thể chỉnh tay.** Sửa, di chuyển, xóa hoặc copy các file WiredTiger khi `mongod` còn chạy có thể tạo bản sao không nhất quán hoặc gây lỗi khởi động.

### Những gì thường có trong `dbPath`

Tùy phiên bản và storage configuration, thư mục có thể chứa những file có tên liên quan tới:

- WiredTiger metadata và storage files.
- Dữ liệu collections và indexes.
- Journal files/thư mục journal.
- Thông tin quản lý khóa hoặc các cấu trúc nội bộ khác.

Tên file và layout **không phải API nghiệp vụ** ổn định. Ứng dụng phải truy cập bằng driver/database commands, không tự mở file dữ liệu trong `dbPath`.

## 3. Persistence: tiến trình chết khác volume bị xóa

Hãy phân biệt:

```text
Tình huống A:
  mongod crash/restart
  -> cùng filesystem và dbPath vẫn còn
  -> storage engine thực hiện recovery theo cơ chế hỗ trợ

Tình huống B:
  Docker container bị xóa
  -> named volume vẫn còn, được mount lại đúng chỗ
  -> dữ liệu có thể vẫn còn

Tình huống C:
  Docker container bị xóa
  -> chỉ lưu trong writable layer của container
  -> dữ liệu không được bảo đảm còn sau khi tạo lại

Tình huống D:
  Kubernetes Pod bị thay thế
  -> Pod mới gắn lại PVC/PV đúng
  -> dữ liệu có thể tiếp tục tồn tại

Tình huống E:
  PVC/PV hoặc disk backend bị xóa/mất
  -> storage đã không còn
  -> phải dùng replica/backup theo kế hoạch phục hồi
```

**Persistent volume không phải backup.** Nếu người vận hành xóa nhầm toàn bộ collection, thao tác xóa đó cũng được ghi vào persistent volume; replica set có thể sao chép hành động xóa sang các members khác.

### Vòng đời tách biệt

| Tài nguyên | Có thể bị thay thế khi deploy? | Chức năng |
| --- | --- | --- |
| Container/Pod | Có | Đóng gói và chạy tiến trình |
| Database process | Có thể restart | Xử lý truy vấn và ghi dữ liệu |
| Data volume/PV | Phải có chính sách giữ riêng | Lưu trạng thái database |
| Backup/snapshot | Quản lý ngoài vòng đời service | Khôi phục sau mất/corruption/xóa nhầm |
| Secret/certificate | Quản lý qua secret lifecycle | Authentication/TLS, không thay data volume |

Thiết kế đúng cần đặt ra câu hỏi: **Khi deploy mới tạo lại Pod/container, thành phần nào vẫn giữ định danh volume và quyền truy cập tới dữ liệu cũ?**

## 4. WiredTiger, cache, checkpoint và journal

WiredTiger sử dụng cache và cơ chế ghi dữ liệu ra storage theo những quy tắc của engine. Về mặt khái niệm:

```text
Client write
     |
     v
MongoDB / WiredTiger
     |
     +--> thay đổi trong cache
     |
     +--> journal/đường bền vững theo cấu hình
     |
     v
Checkpoint và ghi data files
     |
     v
Filesystem / storage device
```

**Checkpoint** và **journal** cùng hỗ trợ khả năng khôi phục sau sự cố. Khi process bị dừng đột ngột, engine có thể dùng thông tin bền vững tương ứng để trở lại một trạng thái nhất quán theo các bảo đảm của server và write concern.

Những điểm quan trọng:

1. Dữ liệu vừa xuất hiện trong cache **không đồng nghĩa** nó đã được ghi bền vững lên storage.
2. Một lệnh ghi thành công theo `w:1` không có cùng đặc tính chịu failover với `w:"majority"`.
3. Journal hỗ trợ recovery nhưng không thay **replication**, **backup** hay phần cứng lưu trữ đáng tin cậy.
4. Đường ghi, checkpoint và journal làm tăng nhu cầu **disk I/O**; không được tính capacity chỉ bằng kích thước documents.
5. Mức độ bền vững phụ thuộc cả storage engine, write concern, cấu hình và khả năng storage backend thực hiện flush/fsync đúng.

### Có nên xóa thư mục `journal` để tiết kiệm disk?

**Không.** Journal và những file nội bộ thuộc MongoDB storage engine. Xóa thủ công khi server đang chạy hoặc trong quá trình recovery có thể phá hỏng khả năng phục hồi và tính toàn vẹn của database.

Nếu ổ đĩa gần đầy, phương án phù hợp là tìm nguyên nhân, nâng dung lượng, quản lý retention/index/backup hoặc làm theo runbook của phiên bản MongoDB. Không “dọn rác” bằng cách xóa các file trong `dbPath` mà bạn không hiểu.

## 5. Write concern và durability không trùng với persistence

Giả sử một replica set có ba members. Ứng dụng ghi:

```javascript
db.orders.insertOne(
  { orderNo: "ORD-1001", status: "NEW" },
  { writeConcern: { w: "majority" } }
);
```

Theo cấu hình replica set và khả năng của server, `w:"majority"` yêu cầu acknowledgment từ đa số voting data-bearing members phù hợp trước khi báo kết quả. Đây là một phần của chính sách bền vững khi failover.

So sánh:

| Write concern | Điều kiện được xác nhận | Điều không nên suy diễn |
| --- | --- | --- |
| `w:1` | Primary xác nhận theo cấu hình | Không bảo đảm write sống sót sau mọi lần failover |
| `w:"majority"` | Đa số members liên quan xác nhận theo quy tắc server | Không bảo vệ khỏi thao tác xóa nhầm được replicate |
| `j:true` | Yêu cầu điều kiện ghi journal được xác nhận trong trường hợp hỗ trợ | Không thay replication/backup hoặc bảo vệ khỏi mất toàn bộ host |
| `wtimeout` | Giới hạn thời gian chờ mức write concern | Timeout **không có nghĩa** thao tác chắc chắn chưa được ghi |

Hành vi journal của majority write concern và các defaults đã thay đổi theo MongoDB version/replica set configuration. Không áp một câu “mọi majority write đều được fsync trên tất cả node” cho mọi deployment.

### Ví dụ Java MongoDB Sync Driver

```java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

// collection được lấy từ MongoDatabase đã cấu hình kết nối.
MongoCollection<Document> durableOrders =
    collection.withWriteConcern(WriteConcern.MAJORITY);

durableOrders.insertOne(
    new Document("orderNo", "ORD-1001")
        .append("status", "NEW")
);
```

Trong production, cần cân nhắc độ trễ majority acknowledgment, retryable writes, idempotency và transaction boundaries. **Không coi một request timeout là bằng chứng insert chưa thành công**; cần đối soát bằng một khóa nghiệp vụ duy nhất trước khi retry.

### Read concern và quan sát dữ liệu

Read concern chi phối tính nhất quán của giá trị được đọc; write concern chi phối điều kiện xác nhận write. Hai thứ liên quan nhưng độc lập về chức năng. Với workflow nhạy cảm, cần lựa chọn read concern, write concern và session/transaction semantics theo hợp đồng nhất quán của ứng dụng.

## 6. Dung lượng disk: tính nhiều hơn bytes tài liệu

Một ước tính capacity cho MongoDB phải gồm:

```text
Database logical documents
   + index data
   + WiredTiger storage overhead / compression effects
   + journal/checkpoint overhead
   + oplog (nếu replica set)
   + temporary files/sort/migration/build indexes
   + filesystem metadata
   + dung lượng dự phòng khi upgrade/restore
```

Không chỉ nhân số document với kích thước JSON xem trên màn hình rồi coi là dung lượng storage thật. BSON, compression, index, update/fragmentation và workload đều làm kết quả thay đổi.

### Sự khác nhau giữa logical size và storage size

MongoDB có thể báo các metric như `dataSize`, `storageSize`, `indexSize` và các chỉ số collection/DB khác. Mỗi metric trả lời một câu hỏi khác nhau.

Ví dụ trong `mongosh`:

```javascript
use appdb

db.stats();
db.orders.stats();
```

Nếu dữ liệu được nén tốt, storage size có thể khác đáng kể logical data size. Indexes và oplog vẫn tiêu thụ dung lượng riêng. Cần tham chiếu metric thật của target version và theo dõi **xu hướng tăng**.

### Headroom quan trọng

Ổ đĩa không nên chạy liên tục sát 100%. Cần chừa không gian cho:

- Phép ghi và các batch ingest tăng đột biến.
- Index builds, compact/migrations/rebuild.
- Checkpoint/journal hoạt động.
- Thay đổi trong quá trình nâng cấp hoặc failover.
- Việc tạo backup tạm, export hoặc restore nếu thực hiện trên cùng host.

Không có một tỷ lệ headroom áp dụng cho mọi hệ thống. Mức dự phòng phải dựa trên tốc độ tăng dữ liệu, kích thước collection/index và thao tác bảo trì lớn nhất dự kiến.

## 7. Storage throughput, IOPS và latency

Database không chỉ cần **đủ byte**, mà còn cần **đủ tốc độ đọc/ghi**.

Các metric cần phân biệt:

| Metric | Ý nghĩa | Tác động MongoDB |
| --- | --- | --- |
| Capacity (GiB/TiB) | Tổng chỗ trống | Giới hạn phát triển dữ liệu |
| IOPS | Số thao tác I/O mỗi giây | Ảnh hưởng workload nhiều random reads/writes |
| Throughput (MiB/s) | Bytes đọc/ghi mỗi giây | Quan trọng khi scan, backup, initial sync |
| I/O latency | Thời gian hoàn thành một I/O | Tác động trực tiếp query latency/checkpoint |
| Queue depth | Độ tồn đọng I/O | Dấu hiệu storage không kịp workload |
| Burst credits/limits | Khả năng tăng tốc tạm thời của cloud disk | Khi hết credit có thể chậm đột ngột |

Một volume 1 TiB có thể vẫn quá chậm nếu chỉ được cấp mức IOPS thấp cho 10.000 writes/s. Ngược lại, SSD tốc độ cao nhưng quá nhỏ vẫn dễ gặp `No space left on device`.

### Disk saturation ảnh hưởng thế nào?

```text
Application writes
        |
        v
MongoDB dirty pages / journal
        |
        v
Storage I/O queue quá dài
        |
        +--> write latency tăng
        +--> checkpoints chậm
        +--> replication lag
        +--> reads bị ảnh hưởng
        +--> timeout ở ứng dụng
```

Không chỉ nhìn CPU: một MongoDB process sử dụng CPU thấp nhưng truy vấn rất chậm có thể đang **chờ disk I/O**.

## 8. Chọn filesystem và storage backend

Đối với self-managed MongoDB dùng WiredTiger, filesystem và storage backend phải đáp ứng những yêu cầu về durability và hiệu năng của phiên bản cụ thể.

Những câu hỏi cần đặt:

1. Filesystem nào được MongoDB khuyến nghị/hỗ trợ cho OS và storage engine hiện tại?
2. Storage backend có tuân thủ các đảm bảo flush/fsync cần thiết không?
3. Disk có random I/O latency/IOPS phù hợp?
4. Có snapshot/backup nhất quán và thử restore được không?
5. Có thể mở rộng dung lượng hoặc thay volume mà không mất dữ liệu không?
6. Khi host đổi, volume có thể attach/mount lại đúng máy/zone không?
7. Storage có encryption-at-rest và key management phù hợp không?

Trên Linux, các filesystem như **XFS** và **ext4** thường được nhắc đến trong MongoDB deployment guidance; lựa chọn cuối cùng cần đối chiếu **production notes theo phiên bản**, đặc biệt với WiredTiger và các khuyến nghị về filesystem. Không chọn NFS/SMB/shared network filesystem chỉ vì mount dễ dàng; cần kiểm tra hỗ trợ và đặc tính khóa/durability/performance trước khi dùng làm `dbPath`.

### Mount options và driver configuration

Không sao chép một danh sách mount options từ máy khác mà không kiểm tra filesystem, OS, cloud provider và khuyến nghị MongoDB. Một option làm tăng tốc I/O có thể thay đổi semantics mà durability dựa vào.

### Tách data và log

Việc đặt `systemLog.path` khác `storage.dbPath` giúp phân biệt chức năng; ở workload lớn có thể cân nhắc disk/filesystem riêng. Tuy nhiên, tách thư mục **không tự tách I/O** nếu chúng vẫn nằm trên cùng volume vật lý.

Một log quá lớn có thể làm đầy filesystem nếu không có log rotation phù hợp. Ngược lại, xóa log không đúng cách khi process giữ file handle mở có thể không giải phóng dung lượng theo kỳ vọng. Cần dùng log rotation và quy trình của hệ điều hành/MongoDB.

## 9. Quyền thư mục: MongoDB chạy bằng user nào?

Trên Linux, dịch vụ MongoDB thường chạy dưới một **service account** không phải root. Tên account và group phụ thuộc package, ví dụ `mongodb` hoặc `mongod` trong những distribution khác nhau.

Trước tiên, cần xác định process thật:

```bash
# Đọc thông tin process; không thay đổi hệ thống.
ps -eo user,group,pid,cmd | grep '[m]ongod'

# Nếu service do systemd quản lý:
systemctl status mongod
systemctl cat mongod
```

Không tự kết luận rằng một distro phải có user `mongodb`. Nếu package dùng `mongod` hoặc custom user, chown sai người có thể khiến dịch vụ mất quyền.

### Tại sao không chạy `mongod` bằng root?

Root có quyền rất rộng trên host. Nếu MongoDB process hoặc extension có lỗ hổng, việc chạy root làm tăng phạm vi ảnh hưởng. Service account riêng với quyền tối thiểu giúp hạn chế thiệt hại.

### Những quyền cần thiết

Service identity cần:

- **Traverse/search** các thư mục cha dẫn tới `dbPath`.
- **Read/write** dữ liệu, journal và metadata trong `dbPath` theo yêu cầu engine.
- Quyền tạo/đổi tên/xóa các file mà MongoDB cần quản lý trong đường dẫn dữ liệu.
- Quyền ghi file log hoặc socket/pid directory nếu cấu hình cần.
- Quyền đọc certificate/keyfile, config/secrets theo chính sách bảo mật.

Không nên cho user khác đọc private key, database files hay dump backups nếu không có nhu cầu.

## 10. Kiểm tra quyền `dbPath` trên Linux

Giả sử `dbPath` là `/var/lib/mongodb`.

```bash
# Read-only inspection:
ls -ld /var/lib/mongodb
stat /var/lib/mongodb
namei -l /var/lib/mongodb

# Xác nhận mount chứa đường dẫn:
df -hT /var/lib/mongodb
```

Ví dụ đầu ra:

```text
drwx------  mongodb mongodb ... /var/lib/mongodb
```

Đây chỉ là một **mẫu minh họa**: user/group thực và permission bits phụ thuộc deployment. Lệnh `namei -l` giúp xem quyền trên **các thư mục cha**, quan trọng vì process có thể có quyền đối với thư mục cuối nhưng không traverse được một thư mục cha.

### Phân biệt ownership và mode bits

- `owner`: user được gán cho file/directory.
- `group`: nhóm owner.
- `r/w/x`: quyền đọc/ghi/thực thi hoặc traverse.
- `ACL`: quyền mở rộng có thể bổ sung/giới hạn hành vi theo OS.
- `SELinux/AppArmor`: policy kiểm soát truy cập **ngoài** Unix mode bits.

Một thư mục `chmod 777` không phải giải pháp thích hợp khi gặp `Permission denied`: nó mở quyền ghi cho mọi user/process có thể tới đường dẫn đó.

## 11. Xử lý `Permission denied` đúng cách

Tình huống: MongoDB không khởi động sau khi gắn volume mới.

```text
mongod
  -> opening WiredTiger files
  -> Permission denied
  -> process exits
```

Quy trình:

1. Xác định user/group của tiến trình qua service/container configuration.
2. Kiểm tra `dbPath` thực tế đang dùng.
3. Kiểm tra mount đã gắn đúng volume chưa.
4. Kiểm tra owner, group, mode bits và quyền traverse của các thư mục cha.
5. Kiểm tra filesystem có đang mount **read-only** không.
6. Nếu OS có SELinux/AppArmor, kiểm tra policy/audit logs.
7. Xác nhận UID/GID nhìn từ container có khớp owner của host files không.
8. Chỉ thay quyền/owner **trên đường dẫn đã xác minh** và khi an toàn.

### Ví dụ thay owner chỉ trong lab

Giả sử bạn đã xác nhận service account **thật sự tên `mongodb`** và đường dẫn **chỉ chứa dữ liệu của dịch vụ đó**:

```bash
# Ví dụ cho môi trường lab, sau khi dừng dịch vụ đúng quy trình.
# Không chạy nếu chưa xác minh đường dẫn, mount, user và quyền.
sudo chown mongodb:mongodb /var/lib/mongodb
sudo chmod 700 /var/lib/mongodb
```

Lệnh trên chỉ chỉnh **thư mục gốc**, không tự sửa toàn bộ file bên dưới. Với lỗi ownership trên các file con, cần điều tra nguồn gốc và chọn cách sửa phù hợp; **không chạy `chown -R` vào đường dẫn chưa xác minh**. Đặc biệt, nếu `/var/lib/mongodb` vô tình là một mount point khác, thao tác đệ quy có thể ảnh hưởng cả dữ liệu không thuộc dịch vụ.

### Vì sao không dùng `chmod -R 777`?

Nó có thể cho user không được phép đọc/ghi/xóa các file database. Đó vừa là rủi ro bảo mật vừa che giấu lỗi identity/mount/SELinux. Quyền rộng không sửa được read-only filesystem, disk đầy hoặc path sai.

## 12. SELinux, AppArmor và các policy bổ sung

Trên một số Linux distribution, ngoài owner/mode bits còn có:

- **SELinux labels/policy**.
- **AppArmor profiles**.
- Systemd sandboxing hoặc giới hạn quyền truy cập filesystem.
- Container security profiles, user namespaces và rootless mode.

Ví dụ cùng một thư mục:

```text
Owner = mongod
Mode  = rwx------
SELinux context = không đúng policy
```

Process vẫn có thể bị từ chối. Nếu tự move `dbPath` sang một mount path khác, có thể cần cấu hình context theo chính sách hệ thống. Không tắt SELinux/AppArmor toàn hệ thống chỉ để cho database khởi động; cần kiểm tra deny logs và điều chỉnh policy/labels một cách có kiểm soát.

### Systemd sandboxing

Systemd service có thể dùng `ReadWritePaths`, `ProtectSystem`, `DynamicUser` hoặc các giới hạn bảo vệ khác. Nếu thay `dbPath` ngoài những đường dẫn được phép, `mongod` có thể không ghi được dù Unix permissions trông đúng.

Hãy xem **effective unit configuration** bằng `systemctl cat mongod` và những drop-in overrides. Không chỉnh file vendor unit trực tiếp nếu muốn giữ khả năng nâng cấp package.

## 13. Docker: writable layer không phải data volume

Một container có nhiều lớp lưu trữ:

```text
MongoDB container
  /data/db  <-- dbPath trong image thông dụng
     |
     +--> Không mount volume:
     |       writable layer container
     |       bị mất khi container được xóa
     |
     +--> Mount named volume:
             dữ liệu ở Docker-managed volume
             có thể được tái sử dụng
```

Với image MongoDB thông dụng, `/data/db` thường là đường lưu data. Nhưng **xác minh cấu hình image/tag cụ thể** và mọi tham số `--dbpath`/config trước khi mount; không mặc định container nào cũng dùng cùng path.

### Named volume

```bash
# Chạy trong lab Docker đã được phép.
docker volume create mongo_lab_data

docker run --name mongo-lab \
  --mount source=mongo_lab_data,target=/data/db \
  mongo:8.0
```

Lệnh này minh họa **gắn persistent volume**, không phải cấu hình database production hoàn chỉnh: chưa có user/auth/TLS, network isolation được kiểm chứng, secrets, backup hay replica set. Không publish cổng MongoDB ra public interface.

Nếu container được dừng/xóa và tạo lại với **cùng named volume**, dữ liệu có cơ hội được tái sử dụng. Nhưng nếu tạo container mới mà quên gắn volume, kết quả có thể là **database trống**, dù volume cũ vẫn còn tồn tại.

### Docker Compose

```yaml
services:
  mongodb:
    image: mongo:8.0
    volumes:
      - mongodb_data:/data/db
    # Không publish MongoDB ra host trong ví dụ này.
    # Auth, TLS, secrets và network policy phải cấu hình riêng.

volumes:
  mongodb_data:
```

Compose trên minh họa **persistence**, không được coi là mẫu bảo mật hoàn chỉnh. Trong production, nên pin version hoặc digest đã kiểm thử, dùng chính sách network và credentials phù hợp, và đặt backup ngoài volume vòng đời deploy.

### Lệnh nguy hiểm: xóa volume

```bash
# KHÔNG chạy trong hệ có dữ liệu cần giữ:
docker compose down -v
```

Tham số `-v` yêu cầu xóa những volumes phù hợp với project theo semantics của Compose. Đây là sự khác biệt lớn với `docker compose down` thông thường. Đừng kết luận volume luôn bị xóa hoặc luôn được giữ mà không hiểu khai báo named/external/anonymous volume và lifecycle.

## 14. Docker bind mount và lỗi UID/GID

Named volume và bind mount không giống nhau.

| Loại | Điểm mạnh | Rủi ro vận hành |
| --- | --- | --- |
| **Named volume** | Docker quản lý đường lưu trữ, dễ tái sử dụng giữa container | Có thể bị xóa nếu cleanup không đúng |
| **Bind mount** | Operator tự chọn thư mục host | UID/GID, SELinux labels, host permissions và path phải đúng |
| **Container writable layer** | Dễ chạy demo một lần | Không phải lựa chọn bền vững cho database được recreate |
| **Tmpfs** | Nằm trong bộ nhớ/tạm | Không dùng làm data store bền vững |

Ví dụ bind mount trong lab:

```bash
docker run --name mongo-lab-bind \
  --mount type=bind,source=/srv/mongo-lab-data,target=/data/db \
  mongo:8.0
```

Đường dẫn nguồn `/srv/mongo-lab-data` phải tồn tại, nằm trên filesystem được hỗ trợ và có quyền phù hợp với **UID/GID thực của process trong container**.

### Vì sao “đã chmod trên host” vẫn lỗi?

Container có thể chạy với user namespace hoặc UID khác với tên user trên host. Tên `mongodb` ở trong container không nhất thiết tương đương owner name trên host, mặc dù kernel đánh giá numeric UID/GID theo ánh xạ namespace.

Các câu hỏi cần kiểm tra:

1. Container process đang chạy với UID/GID nào?
2. Host directory có owner/mode/ACL nào?
3. Docker daemon có rootless/userns-remap không?
4. SELinux/AppArmor có policy/label phù hợp không?
5. Path ở host có đúng là mount nguồn mà container đang dùng không?

Không sửa bằng `chmod 777` hoặc chạy container như root vô điều kiện. Sửa identity/mount semantics và quyền tối thiểu.

## 15. Docker: quan sát volume và resource limits

Các lệnh đọc trạng thái:

```bash
docker inspect mongo-lab
docker volume inspect mongo_lab_data
docker stats mongo-lab
docker logs --tail 100 mongo-lab
```

Mục tiêu:

- `docker inspect` cho thấy mounts, image, runtime config.
- `docker volume inspect` cho thấy metadata volume, không phải backup contents.
- `docker stats` hiển thị CPU/memory/network/block I/O theo môi trường.
- `docker logs` giúp thấy lỗi permission, storage hoặc startup.

**Không chỉnh sửa file WiredTiger bằng cách vào container và tự sửa `/data/db`.** Nếu container startup fail, hãy đọc log và xác minh mount/permission trước.

### Giới hạn CPU và memory của container

Docker có các tùy chọn giới hạn tài nguyên, ví dụ:

```bash
# Ví dụ khái niệm cho container thử nghiệm.
docker run --rm \
  --memory=2g \
  --cpus=1.5 \
  --mount source=mongo_lab_data,target=/data/db \
  mongo:8.0
```

Giới hạn 2 GiB RAM là giả định lab, **không phải khuyến nghị phổ quát** cho MongoDB production. Cấu hình WiredTiger cache, concurrency, workload và các process khác phải phù hợp. Nếu memory cap thấp hơn working set, query có thể chậm do I/O; nếu process vượt cgroup limit, container có thể bị OOM-killed.

## 16. Kubernetes: Pod không phải nơi giữ dữ liệu

Trong Kubernetes, Pod được tạo lại khi node thay đổi, deploy image mới hoặc controller thực hiện rolling update. Một database không nên phụ thuộc vào **writable filesystem tạm của Pod** để giữ dữ liệu.

Kiến trúc lưu trữ:

```text
StatefulSet / MongoDB Operator
        |
        v
Pod mongo-0
        |
        v
PersistentVolumeClaim (PVC)
        |
        v
PersistentVolume (PV)
        |
        v
StorageClass / block storage backend
```

Các khái niệm:

- **PVC:** yêu cầu storage của workload.
- **PV:** tài nguyên volume đáp ứng yêu cầu.
- **StorageClass:** mô tả cách cấp phát storage, topology và một số thông số provisioner.
- **StatefulSet:** giúp quản lý stable identity và volume claim templates trong workloads cần state.
- **MongoDB Operator/Helm deployment:** có thể quản lý replica set và storage, nhưng phải đọc defaults/config thực tế.

**StatefulSet tự nó không thay thế MongoDB replica set hoặc backup.** StatefulSet giữ identity/storage naming ở cấp Kubernetes; MongoDB replication xử lý tính nhất quán giữa database members.

## 17. StatefulSet và `volumeClaimTemplates`

Một cấu hình Kubernetes chỉ để minh họa **ý tưởng PVC per Pod**:

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: mongo-lab
spec:
  serviceName: mongo-lab
  replicas: 1
  selector:
    matchLabels:
      app: mongo-lab
  template:
    metadata:
      labels:
        app: mongo-lab
    spec:
      containers:
        - name: mongod
          image: mongo:8.0
          volumeMounts:
            - name: mongo-data
              mountPath: /data/db
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              cpu: "2"
              memory: "2Gi"
  volumeClaimTemplates:
    - metadata:
        name: mongo-data
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: "20Gi"
```

Đây là **trích đoạn giải thích storage**, không phải manifest triển khai MongoDB production: còn thiếu Service, MongoDB replica set configuration, auth/TLS, readiness/liveness, resource tuning, storageClass, backups, topology spread và các yêu cầu operator khác.

### `ReadWriteOnce` có nghĩa gì?

Về mặt Kubernetes, `ReadWriteOnce` quy định volume được mount read-write bởi **một node tại một thời điểm** theo semantics của volume/plugin; nó **không phải** cơ chế khóa một tiến trình `mongod` duy nhất trong mọi tình huống. Tránh gắn cùng `dbPath` để hai process MongoDB độc lập cùng ghi mà không có kiến trúc hỗ trợ.

### Một PVC cho mỗi replica set member

Một replica set cần các members độc lập, mỗi member có data path/volume riêng theo deployment. Không cho tất cả members cùng ghi chung một data directory với hy vọng đó là “shared database”.

```text
mongo-0 -> PVC mongo-data-mongo-0
mongo-1 -> PVC mongo-data-mongo-1
mongo-2 -> PVC mongo-data-mongo-2
```

MongoDB replication giao tiếp qua mạng và oplog; nó **không thay thế** bằng shared filesystem giữa các mongod processes.

## 18. Kubernetes securityContext, `runAsUser` và `fsGroup`

Pod/container có thể chạy dưới UID/GID không root và cần quyền ghi vào PVC. Có thể gặp cấu hình kiểu:

```yaml
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1001
    runAsGroup: 1001
    fsGroup: 1001
```

Các UID/GID `1001` chỉ mang tính **minh họa**, không phải identity của mọi MongoDB image. Phải xác nhận image/Operator đang dùng hỗ trợ đúng user và permissions.

### `fsGroup` không phải phép màu

Kubernetes/runtime/storage driver có thể sử dụng `fsGroup` để cấp quyền group trên volume theo cơ chế tương ứng. Nhưng:

- Không phải mọi CSI driver/backend hỗ trợ giống nhau.
- Một số cấu hình cần thay đổi ownership, có thể tốn thời gian trên volume chứa hàng triệu files.
- Existing permissions/ACL/SELinux vẫn có thể chặn.
- Rootless/user namespace và image user có thể làm mapping phức tạp.

Nếu PVC không mount/ghi được, xem events, effective UID/GID và storage-driver behavior. Không tự thêm một init container chạy root chown toàn bộ volume production mà chưa đánh giá rủi ro và thời gian downtime.

### Các lệnh quan sát PVC và Pod

```bash
kubectl get pvc -n mongo-lab
kubectl describe pvc mongo-data-mongo-lab-0 -n mongo-lab
kubectl describe pod mongo-lab-0 -n mongo-lab
kubectl logs mongo-lab-0 -n mongo-lab --tail=100
```

Tên PVC trong ví dụ được suy từ template/statefulset theo một pattern thường gặp; trên cluster thật dùng tên do `kubectl get pvc` trả về.

## 19. StorageClass, topology và quyền truy cập volume

Một PVC có thể bị `Pending` vì:

- Chưa có StorageClass phù hợp.
- Backend không còn quota/capacity.
- StorageClass có ràng buộc zone/topology.
- Provisioner/CSI controller lỗi.
- Access mode hoặc volume mode không được hỗ trợ.
- Secret/permission của storage backend không hợp lệ.

### Zone awareness

Nếu volume được cấp ở availability zone A nhưng Pod được scheduler đặt ở zone B, block storage có thể không attach được. Cần topology/scheduler/storage configuration phù hợp, nhất là khi failover/reschedule.

### Reclaim policy và PVC deletion

Kubernetes PV có reclaim policies như `Retain` hoặc `Delete`; hành vi cụ thể phụ thuộc StorageClass/PV và controller. Ngoài ra, StatefulSet có chính sách retention PVC khi scale/down/delete trong các phiên bản Kubernetes tương ứng.

**Không giả định xóa StatefulSet là chắc chắn giữ mọi PVC**, cũng không giả định xóa PVC không ảnh hưởng disk backend. Trước mọi thay đổi phải đọc actual retention/reclaim configuration và backup.

### `emptyDir`

`emptyDir` được tạo cho Pod và không có mục tiêu persistence sau khi Pod bị xóa. Nó phù hợp cho **dữ liệu tạm**, không phải `dbPath` lâu dài. Một Pod restart container bên trong Pod có thể vẫn thấy `emptyDir`, nhưng điều đó không có nghĩa nó sống qua toàn bộ vòng đời Pod.

## 20. RAM: WiredTiger cache không phải toàn bộ mức dùng bộ nhớ

MongoDB tiêu thụ RAM cho nhiều thành phần:

```text
Process RSS / memory usage
   |
   +--> WiredTiger internal cache
   +--> Query execution buffers
   +--> Connections, threads, stacks
   +--> Internal metadata/structures
   +--> Allocator / memory overhead
   +--> TLS, compression và driver interaction

OS memory
   |
   +--> Filesystem page cache
   +--> Kernel memory
   +--> Các process khác trên host
```

**Không lấy giới hạn WiredTiger cache làm giới hạn tổng RAM của process.** Nếu cache được cấu hình 1 GiB, process có thể dùng nhiều hơn 1 GiB vì còn các thành phần khác.

### Tại sao chỉ nhìn `free -m` dễ gây hiểu nhầm?

Linux dùng RAM trống cho page cache để tăng hiệu quả I/O. Một máy có ít “free” nhưng nhiều “available” không nhất thiết đang thiếu RAM nghiêm trọng. Cần xem áp lực thực sự: swap/major faults, cache eviction, OOM events, memory usage và latency.

### WiredTiger cache config

MongoDB có những cấu hình như `storage.wiredTiger.engineConfig.cacheSizeGB`. Giá trị mặc định và cách xác định trong môi trường container/cgroup **phụ thuộc phiên bản, platform và resource limits**. Không sao chép một giá trị cứng từ server 64 GiB RAM sang Pod bị giới hạn 2 GiB.

Nếu cache quá lớn so với memory cap, process có thể bị OOM-killed. Nếu cache quá nhỏ so với working set, database có thể tăng đọc disk và query latency. Chọn cache cần dựa trên metrics và workload.

## 21. Container OOM và CPU throttling

Khi Kubernetes/Docker giới hạn RAM:

```text
MongoDB memory pressure
       |
       v
Container vượt memory limit
       |
       v
OOM kill / container restart
       |
       v
MongoDB recovery trên cùng persistent volume
       |
       v
Workload bị gián đoạn
```

Nếu volume là ephemeral, restart/recreate có thể đi kèm mất dữ liệu. Nếu volume bền vững, storage engine có thể recovery theo cơ chế hỗ trợ, nhưng downtime và crash frequency vẫn là sự cố nghiêm trọng.

### CPU requests và limits

- **CPU request** giúp scheduler đặt Pod dựa trên tài nguyên dự trù.
- **CPU limit** có thể gây throttling khi workload muốn dùng nhiều CPU hơn quota.
- **Memory request/limit** ảnh hưởng scheduling/OOM behavior.

Ví dụ set CPU limit quá thấp trên workload nhiều aggregations có thể làm p95/p99 latency tăng dù ổ đĩa không bận. Ngược lại, không giới hạn/không điều phối đúng có thể làm MongoDB cạnh tranh tài nguyên với các dịch vụ khác.

### Đọc signals từ Kubernetes

```bash
kubectl top pod -n mongo-lab
kubectl describe pod mongo-lab-0 -n mongo-lab
```

Kiểm tra `Last State: OOMKilled`, restart count, events và metrics từ cgroup/Prometheus nếu có. `kubectl top` cần metrics server tương ứng và không thay thế lịch sử monitoring.

## 22. File descriptors và `ulimit`

Mỗi network connection, socket và file mở có thể tiêu thụ **file descriptor** của process trên Unix-like systems. Khi MongoDB phục vụ nhiều kết nối và truy cập nhiều data files, giới hạn quá thấp có thể gây lỗi mở file/socket.

Các lệnh kiểm tra trong môi trường Linux:

```bash
# Giới hạn của shell hiện tại (không nhất thiết là mongod):
ulimit -n

# Xem limits của tiến trình mongod đang chạy:
pidof mongod
cat /proc/<mongod-pid>/limits
```

Trong lệnh cuối, thay `<mongod-pid>` bằng PID thực trước khi chạy; đây là ký hiệu placeholder, **không phải cú pháp shell trực tiếp**.

### Vì sao thay `ulimit -n` ở terminal chưa chắc sửa được service?

Một `mongod` do systemd khởi động nhận resource limits từ **service manager/unit configuration**, không nhất thiết từ terminal SSH của operator.

Ví dụ đọc:

```bash
systemctl show mongod -p LimitNOFILE -p TasksMax -p MemoryMax
systemctl cat mongod
```

Khi cần thay đổi thực tế, nên dùng systemd drop-in theo quy trình cấu hình và restart có kiểm soát, thay vì sửa vendor unit file hoặc đặt `ulimit` trong một shell không phải parent của service.

### Những giới hạn khác

| Giới hạn | Ảnh hưởng |
| --- | --- |
| Number of open files (NOFILE) | Connections/file handles |
| Max processes/threads (NPROC/TasksMax) | Threads và tài nguyên process |
| Virtual memory/address space | Khả năng cấp phát memory |
| cgroup memory limit | OOM kill nếu vượt giới hạn |
| cgroup CPU quota | CPU throttling |
| PID limit | Không tạo được thêm threads/processes |
| Disk quota/inodes | Không tạo/ghi thêm files |
| Connection limit | Client bị từ chối hoặc queue ở server |

Những giá trị khuyến nghị cụ thể phải tra đúng **MongoDB production notes cho version/OS/topology**. Không có một con số `ulimit -n` duy nhất phù hợp mọi quy mô.

## 23. Filesystem đầy, inode đầy và read-only remount

Ba lỗi khác nhau có thể đều biểu hiện là MongoDB không ghi được:

1. **Hết bytes:** `df -h` cho thấy filesystem đầy.
2. **Hết inodes:** `df -i` cho thấy inode allocation hết, dù còn byte capacity.
3. **Filesystem chuyển read-only:** do lỗi I/O, policy hoặc vấn đề disk, không thể tạo/ghi file.

Lệnh đọc trạng thái:

```bash
df -hT /var/lib/mongodb
df -i /var/lib/mongodb
findmnt /var/lib/mongodb
```

Lệnh `findmnt` giúp xác định mount thực tế và options; đường dẫn có thể khác deployment. Nếu mount không tồn tại nhưng service vẫn khởi động, `dbPath` có thể vô tình nằm trên **root filesystem** của host thay vì data disk dự kiến.

### Không xử lý disk-full bằng cách xóa file WiredTiger

Việc xóa một file data/index/journal trong `dbPath` có thể gây lỗi corruption. Các biện pháp phù hợp hơn:

- Xác định volume thật và growth trend.
- Tăng capacity/IOPS theo phương thức hỗ trợ.
- Kiểm tra oplog/index/retention/logs/backups để xác định nguồn chiếm dung lượng.
- Dọn dữ liệu nghiệp vụ thông qua MongoDB API và policy, không qua filesystem.
- Chuẩn bị recovery plan nếu disk đã vào trạng thái lỗi.

Thậm chí xóa nhiều MongoDB documents không nhất thiết làm dung lượng filesystem giảm ngay: storage engine có thể giữ pages để tái sử dụng. Không dùng `df` giảm ngay làm thước đo duy nhất cho cleanup thành công.

## 24. Swap, memory pressure và kernel tuning

Các khuyến nghị về transparent huge pages (THP), swap, kernel limits và memory management **thay đổi theo MongoDB version và hệ điều hành**. Không tự đặt một công thức “luôn tắt THP” hay “luôn bật THP” cho mọi MongoDB release.

Trước khi thay kernel/VM tuning:

1. Ghi nhận MongoDB version, OS/kernel và storage engine.
2. Đối chiếu MongoDB **production notes** tương ứng.
3. Kiểm tra hiện trạng cùng metrics.
4. Thử nghiệm ở môi trường gần production.
5. Đặt rollback và bảo đảm thay đổi tồn tại sau reboot nếu cần.

### Swap có thể gây gì?

Khi hot working set bị đẩy vào swap, query latency có thể tăng mạnh. Nhưng cố “tắt mọi swap” trên host thiếu RAM cũng có thể khiến process OOM sớm hơn. Cần sizing RAM và cgroup đúng thay vì coi swap là nguyên nhân duy nhất.

## 25. Quyền của log, socket, certificate và backup

Nhiều người chỉ kiểm tra `dbPath` nhưng quên những đường dẫn khác:

| Thành phần | Ví dụ | Quyền cần lưu ý |
| --- | --- | --- |
| Data | `/var/lib/mongodb` | Mongod cần read/write/traverse |
| Log | `/var/log/mongodb/mongod.log` | Mongod cần ghi file và traverse thư mục |
| TLS private key | `/etc/mongodb/tls/server.pem` | Mongod cần đọc, không cấp cho mọi user |
| Internal keyfile | `/etc/mongodb/keyfile` | Quyền rất hạn chế theo security requirements |
| PID/socket directory | `/run/mongodb` | Có thể được systemd/tmpfiles quản lý |
| Backup archive | `/backup/mongodb/...` | Backup service cần ghi, access kiểm soát riêng |

### Không đặt TLS key trong data volume công khai

Private keys và credentials cần được quản lý qua secret/certificate lifecycle. Không chuyển chúng vào một thư mục chia sẻ có quyền rộng chỉ để container đọc được.

### Backup cần đủ quyền nhưng không nên có toàn quyền host

Backup tool/agent cần đọc dữ liệu qua API hoặc snapshot mechanism và ghi vào backup destination. Nó không cần nhất thiết có quyền `chmod -R 777` trên data directory. Áp dụng least privilege và dùng credentials riêng cho backup/restore.

## 26. Replica set: persistence và durability ở nhiều node

Một replica set có nhiều `mongod`:

```text
Application
      |
      v
Primary mongod    -> data volume A
      |
      +--> Secondary 1 -> data volume B
      |
      +--> Secondary 2 -> data volume C
```

Mỗi member cần **data path riêng và persistent storage riêng**. Replica set sao chép operations qua MongoDB replication mechanism; các members không cùng ghi vào một data directory.

### Những điều vẫn có thể sai dù có ba members

- Cả ba volumes nằm chung một storage failure domain.
- Backup chỉ chụp một volume không nhất quán.
- Client dùng write concern không phù hợp với RPO.
- Một operator xóa nhầm collection và xóa được replicate.
- Disk saturation đồng thời trên nhiều members.
- Permissions bị thay đổi khi nâng cấp image/package làm nhiều members không khởi động.

Replica set giúp **availability và fault tolerance** trong những giới hạn thiết kế, không thay thế mọi yêu cầu backup, data validation hoặc capacity planning.

### Oplog và disk

Oplog lưu lịch sử operations phục vụ replication/change streams theo cơ chế phù hợp. Kích thước/retention oplog ảnh hưởng:

- Khả năng secondary theo kịp primary.
- Khả năng resume change streams trong lịch sử còn lại.
- Dung lượng disk cần dự trù.

Oplog không phải backup tùy ý và không thể xem là một kho lịch sử bất biến vô hạn. Khi sizing phải xét lưu lượng write, downtime tối đa, replication lag và nhu cầu CDC.

## 27. Backup nhất quán quan trọng hơn việc copy thư mục

Một anti-pattern:

```bash
# KHÔNG dùng như phương thức backup an toàn của MongoDB đang chạy:
cp -r /var/lib/mongodb /tmp/mongo-backup
```

Khi `mongod` đang ghi, việc copy file tuần tự có thể lấy những data/journal files tại **các thời điểm khác nhau**, tạo backup không nhất quán.

Các lựa chọn cần đánh giá theo phiên bản/topology:

- **Logical backup** bằng `mongodump` khi phù hợp.
- **Filesystem/storage snapshots** dùng phương thức tạo snapshot nhất quán được MongoDB hỗ trợ.
- Backup agent/managed backup service có thể thực hiện PIT/cluster-aware backups.
- **MongoDB Atlas managed backup** trên tier/cấu hình hỗ trợ.

### Backup cũng cần môi trường vận hành riêng

- Đừng lưu mọi bản backup trên cùng ổ đĩa chứa database.
- Kiểm tra quyền và encryption cho backup.
- Áp dụng retention và backup immutability khi yêu cầu.
- Đo tốc độ restore và tính toàn vẹn của dữ liệu.
- Xác minh backup bao gồm đúng databases, roles/configuration và dependencies cần phục hồi.

**Backup chưa được restore thử là backup chưa chứng minh được khả năng sử dụng.**

## 28. Ví dụ giám sát disk, process và storage bằng các lệnh chỉ đọc

Trên Linux:

```bash
# Dung lượng và mount:
df -hT /var/lib/mongodb
df -i /var/lib/mongodb
findmnt /var/lib/mongodb

# RAM và CPU:
free -h
vmstat 1 5

# Process và resource limits:
ps -eo user,group,pid,rss,cmd | grep '[m]ongod'
systemctl show mongod -p LimitNOFILE -p TasksMax -p MemoryMax

# Storage devices:
lsblk -f
```

Nếu có công cụ sysstat:

```bash
iostat -xz 1 5
```

Trên một số môi trường container/cloud, lệnh/metric có thể không hiển thị trực tiếp toàn bộ block-device I/O. Cần đối chiếu với metrics của cloud volume, cgroup và monitoring server.

### Đọc metrics từ MongoDB

Trong `mongosh`, với quyền thích hợp:

```javascript
db.adminCommand({ serverStatus: 1 });

db.getSiblingDB("appdb").stats();

db.getSiblingDB("appdb").orders.stats();
```

Khi tập trung vào WiredTiger cache:

```javascript
const status = db.adminCommand({ serverStatus: 1 });
printjson(status.wiredTiger?.cache);
```

Các field metrics cụ thể thay đổi theo MongoDB version/storage engine và có thể yêu cầu privileges. Đừng copy metric names rồi giả định mọi server trả đúng cùng cấu trúc.

### Không công bố `serverStatus` ra Internet

Metrics và cấu hình server có thể bộc lộ thông tin vận hành nhạy cảm. Hãy giới hạn quyền monitor, dashboard và logging theo chính sách tổ chức.

## 29. Những tín hiệu cần alert trước khi sự cố xảy ra

| Nhóm | Ví dụ signal | Hành động điều tra |
| --- | --- | --- |
| Disk | Free space giảm nhanh | Dự báo ngày đầy, xem growth/index/oplog |
| Disk I/O | Latency và queue depth tăng | Kiểm tra volume limits, burst credits, concurrent jobs |
| Memory | OOM kills, cache pressure, swap | Xem cgroup, WiredTiger cache, working set |
| CPU | Sustained saturation/throttling | Xem queries, aggregation và CPU quota |
| Filesystem | Read-only remount, I/O errors | Điều tra storage/backend, tránh tiếp tục ghi |
| Process | Mongod restart bất thường | Đọc logs, systemd/Kubernetes events |
| Limits | Too many open files | Kiểm tra NOFILE và connection growth |
| Replication | Lag tăng hoặc member unhealthy | Kiểm tra network/disk/CPU/oplog |
| Backups | Job fail hoặc restore test fail | Khắc phục trước sự cố thật |
| K8s | PVC Pending, VolumeAttachment errors | Kiểm tra CSI/topology/quota |
| Security | Ownership/ACL/cert thay đổi | Review deployment/automation |

Thresholds cần dựa trên workload và thời gian phản ứng mong muốn. Một database nhỏ tăng 1 GiB/ngày khác hoàn toàn với workload tăng 100 GiB/giờ.

## 30. Những sự cố phổ biến và cách phân lớp nguyên nhân

### Sự cố A: Container mới lên, collection biến mất

Khả năng:

- Container cũ dùng writable layer thay vì named volume.
- Container mới mount **volume khác**.
- Compose project đổi tên, tạo một named volume mới.
- `dbPath` thay đổi nhưng mount vẫn trỏ path cũ.
- App dùng nhầm database/connection URI khác.

Kiểm tra:

```bash
docker inspect mongo-lab
docker volume ls
docker volume inspect mongo_lab_data
```

Không vội chạy `mongorestore` lên container mới khi chưa xác định **volume cũ có còn tồn tại**. Có thể chỉ là mount nhầm, không phải mất dữ liệu thật.

### Sự cố B: MongoDB không khởi động sau khi chuyển volume

Khả năng:

- UID/GID/permissions khác.
- Mount read-only hoặc mount path sai.
- SELinux/AppArmor label không khớp.
- Image/server version không tương thích data files.
- Filesystem/storage I/O errors.

Đọc logs và kiểm tra mount/owner trước. Không dùng `--repair` như phản xạ mặc định; các thao tác sửa chữa storage có rủi ro, phải tuân theo recovery procedure và backup của phiên bản MongoDB.

### Sự cố C: Pod `CrashLoopBackOff`

Khả năng:

- OOMKilled do memory limit thấp.
- PVC Pending/attach thất bại.
- Permission denied.
- Config/TLS/internal auth lỗi.
- Health probes không phù hợp với thời gian recovery.

Chẩn đoán:

```bash
kubectl describe pod mongo-lab-0 -n mongo-lab
kubectl logs mongo-lab-0 -n mongo-lab --previous
kubectl describe pvc mongo-data-mongo-lab-0 -n mongo-lab
```

Đừng tăng memory limit khi root cause là storage mount, và đừng `chown` PVC khi lỗi là OOM.

### Sự cố D: Database chậm trong khi CPU thấp

Khả năng:

- Disk latency cao, throughput/IOPS cap.
- Working set lớn hơn cache/RAM.
- Page faults hoặc swap.
- Một backup/index build cạnh tranh I/O.

Đọc `iostat`, cloud disk metrics và WiredTiger cache/eviction metrics, thay vì chỉ tăng số vCPU.

## 31. Nâng cấp MongoDB: kiểm tra storage trước khi thay binary

Nâng cấp MongoDB có thể tác động tới:

- Metadata/storage format và khả năng tương thích với bản trước.
- Filesystem/OS support.
- Index builds hoặc background operations.
- Resource usage mặc định.
- Kernel tuning recommendations.
- Driver/protocol compatibility.
- Feature Compatibility Version (FCV) và quy trình rolling upgrade.

**Không lấy data files của một phiên bản mới hơn rồi tùy ý khởi động binary cũ trên cùng `dbPath`.** Tính tương thích và đường nâng/hạ cấp có ràng buộc theo MongoDB version.

### Preflight storage and resource checklist

1. Xác định source/target MongoDB version, FCV, topology và OS.
2. Đọc **release notes** và **upgrade path** tương ứng.
3. Xác nhận đủ disk headroom cho index/migration/temporary operations.
4. Đo IOPS, CPU, RAM/cache và replication lag khi tải bình thường.
5. Xác nhận data volumes, mount paths và ownership được giữ sau deployment.
6. Xem image/package có đổi service user UID/GID hoặc paths không.
7. Kiểm tra `ulimit`/systemd/cgroup và kernel recommendations của bản mới.
8. Có backup được xác minh và đã diễn tập restore.
9. Thử nâng cấp trên môi trường có volume/dữ liệu đại diện.
10. Có rollback plan **theo hướng dẫn được hỗ trợ**, không chỉ đổi lại image tag.

### Rolling upgrade không có nghĩa “restart tất cả cùng lúc”

Với replica set, thường phải tuân theo thứ tự và yêu cầu quorum/primary availability của MongoDB. Với sharded cluster, còn có quy trình cho config servers, shards và routers. Không tự restart tất cả nodes hoặc xóa StatefulSet/PVC chỉ vì muốn deploy image mới.

## 32. Vì sao quyền thư mục có thể thay đổi sau nâng cấp?

Một gói hệ điều hành hoặc container image mới có thể dùng:

- Tên user/group dịch vụ khác.
- Numeric UID/GID khác.
- Đường dẫn dữ liệu/log/config khác.
- Systemd sandboxing chặt hơn.
- Security profiles hoặc file labels khác.
- Cơ chế mount volume khác do chart/operator thay đổi.

Ví dụ:

```text
Trước upgrade:
  /srv/mongo-data owned by UID 999

Sau upgrade:
  mongod chạy dưới UID 1001

Nếu không có group/ACL phù hợp:
  Permission denied khi mở data files
```

Đây là tình huống minh họa, **không khẳng định một MongoDB image cụ thể sử dụng UID 999 hay 1001**. Cần xem release notes và inspect image/process thật.

Để tránh:

1. Pin image/package versions được kiểm thử.
2. Ghi nhận effective service UID/GID hiện tại.
3. Test upgrade với **bản sao volume** trong lab.
4. Kiểm tra filesystem ownership và SELinux/AppArmor policy.
5. Đặt change plan nếu cần sửa permissions.
6. Không đổi ownership hàng triệu files giữa downtime mà chưa ước lượng I/O/time.

## 33. Quy trình chuyển dữ liệu sang disk mới

Giả sử muốn chuyển `dbPath` từ disk nhỏ sang volume lớn.

**Không** chỉ thêm một dòng `storage.dbPath` mới rồi restart khi dữ liệu cũ vẫn ở path trước; MongoDB có thể thấy một thư mục trống và khởi động như database mới, hoặc gặp lỗi config.

Một kế hoạch khái niệm:

1. Xác định topology (standalone/replica set/sharded).
2. Chọn phương thức migration được MongoDB hỗ trợ: ví dụ bổ sung member mới và initial sync, backup/restore hoặc dừng dịch vụ rồi copy dữ liệu theo quy trình nhất quán được phép.
3. Bảo đảm backup và RPO/RTO đã được duyệt.
4. Chuẩn bị filesystem/disk, mount point, owner/permissions.
5. Chuyển hoặc đồng bộ dữ liệu bằng quy trình **consistent**, không copy live files tùy tiện.
6. Cập nhật `dbPath`/volume mapping và cấu hình service.
7. Khởi động và kiểm tra logs/recovery, replica status, collections/indexes.
8. Đối chiếu checksum/business data theo policy.
9. Giữ old volume trong khoảng rollback được quy định, không xóa ngay.

### Replica set có thể giúp giảm downtime

Thay vì copy live files của primary, có thể lập kế hoạch thay thế từng member có volume mới và để MongoDB thực hiện initial sync/replication theo thủ tục được hỗ trợ. Cách này cần đủ disk/CPU/network và quan tâm replication lag/quorum. Không xem đây là một lệnh “thay volume” tự động cho mọi topology.

## 34. MongoDB Atlas: những gì do dịch vụ quản lý

Với MongoDB Atlas, người dùng thường không trực tiếp:

- Chown thư mục `dbPath` trên node do Atlas quản lý.
- Sửa systemd limits trên các MongoDB hosts.
- Mount PVC vào Atlas-managed mongod.
- Xóa journal/data files ở node.

Atlas cung cấp cấu hình capacity, storage và những tùy chọn managed service theo cluster tier/deployment. Người vận hành vẫn chịu trách nhiệm:

- Chọn cluster size/storage đủ theo workload.
- Theo dõi CPU, memory, disk, IOPS/latency, replication lag qua metrics được cung cấp.
- Quản lý database users, network access và application permissions.
- Thiết lập backup/restore, retention và thử nghiệm phục hồi.
- Theo dõi cảnh báo capacity/autoscaling nếu có.
- Kiểm tra tác động upgrade, driver compatibility và application behavior.

**Không áp một hướng dẫn chmod/chown của Linux VM lên Atlas-managed nodes.** Nếu Atlas cluster có giới hạn resource hoặc storage, dùng cơ chế scaling/configuration/managed support phù hợp thay vì tìm cách thay file nội bộ.

## 35. Bảng so sánh theo môi trường chạy

| Tiêu chí | Linux VM/bare metal | Docker/Compose | Kubernetes | Atlas |
| --- | --- | --- | --- | --- |
| Data path | `storage.dbPath` trên filesystem | `dbPath` trong container, mount volume | PVC/PV qua StatefulSet/Operator | Managed |
| Persistence | Volume/partition do operator quản lý | Named volume/bind mount | PVC/PV và reclaim policy | Managed infrastructure |
| Quyền file | OS user/group/ACL/SELinux | UID/GID/container namespace/host mount | runAsUser/fsGroup/CSI/security context | Không chỉnh trực tiếp |
| RAM/CPU | Host/process limits | Docker/cgroup limits | Requests/limits/cgroup | Cluster tier/config |
| Open files | ulimit/systemd | Host/container limits | Container/runtime/node limits | Managed |
| Disk metrics | df/iostat/cloud disk | Docker/host disk metrics | PVC/CSI/cloud volume metrics | Atlas metrics |
| Backup | Self-managed hoặc backup service | Backup ngoài container volume | Operator/cluster-aware backup | Managed backup tùy tính năng |
| Upgrade | Package/binary + FCV procedure | Image + data volume compatibility | Operator/StatefulSet upgrade | Atlas release/upgrade policy |
| Rủi ro hay gặp | Wrong permissions, disk full | Mất volume/mount sai | PVC/attach/zone/OOM | Sizing/backup/network/migration |

Không có môi trường nào loại bỏ nhu cầu **giám sát storage, tài nguyên và khôi phục dữ liệu**; chỉ khác việc ai có quyền và trách nhiệm xử lý từng lớp.

## 36. Một runbook chẩn đoán khi MongoDB không lên sau deploy

### Bước 1 — Xác định phạm vi

```text
Service process crash?
Container OOMKilled?
Pod PVC Pending?
MongoDB start nhưng database trống?
Secondary unhealthy hay toàn cluster offline?
```

### Bước 2 — Không làm hỏng bằng chứng

- Không xóa files trong `dbPath`.
- Không tạo một volume mới rồi ghi đè volume cũ mà chưa hiểu trạng thái.
- Không chạy `mongod --repair` tùy tiện.
- Không sửa quyền toàn bộ thư mục bằng `777`.
- Giữ logs, events và thông tin mount/UID/GID trước thao tác.

### Bước 3 — Kiểm tra môi trường

| Hệ | Thông tin cần lấy |
| --- | --- |
| VM | `systemctl status`, logs, `df`, `findmnt`, `ls -ld`, limits |
| Docker | `docker inspect`, logs, volume name, image, memory limits |
| Kubernetes | Pod events, PVC/PV, storage class, security context, OOM state |
| Atlas | Cluster alerts, metrics, backup status, recent configuration changes |

### Bước 4 — Phân loại root cause

```text
Permission denied -> owner/mode/ACL/SELinux/UID
No space left      -> capacity/inodes/quota
Read-only FS       -> storage/backend/filesystem
OOMKilled          -> memory limit/cache/query load
Too many files     -> NOFILE/connections
Volume not found   -> mount/PVC/StorageClass/topology
Invalid config     -> image/package/version change
Data corruption    -> backup/recovery protocol; không sửa tay
```

### Bước 5 — Khôi phục có kiểm soát

Sau khi xác định nguyên nhân và có backup/rollback plan:

1. Thực hiện thay đổi tối thiểu vào đúng lớp.
2. Khởi động lại theo thứ tự/quorum phù hợp.
3. Xác nhận `mongod`/members healthy.
4. Đọc data và query nghiệp vụ; không chỉ `ping`.
5. Kiểm tra replication lag/write concern.
6. Theo dõi CPU, RAM, disk latency, errors.
7. Ghi incident report và hành động ngăn lặp lại.

## 37. Các lỗi phổ biến

| Triệu chứng | Nguồn gốc có thể | Cách tiếp cận |
| --- | --- | --- |
| Container mới có DB trống | Quên mount volume hoặc dbPath khác | Inspect mounts, tìm volume cũ |
| `Permission denied` khi mở WiredTiger | UID/GID/ACL/SELinux không đúng | Xác nhận user/mount/policy, sửa tối thiểu |
| `No space left on device` | Data/index/journal/oplog/log đầy | Dự báo capacity, tăng storage, policy cleanup |
| `Read-only file system` | FS bị remount RO hoặc volume policy | Điều tra storage backend |
| `Too many open files` | NOFILE thấp hoặc leak connections | Xem process limits và workload |
| `OOMKilled` | Memory cap/WiredTiger cache/query pressure | Sizing memory, metrics/cache |
| CPU throttling, p99 tăng | cgroup CPU quota thấp | Đo quota, query load, tune resources |
| PVC Pending | CSI/quota/StorageClass/zone | Describe PVC/events |
| Pod không attach được PV | Topology/attachment conflict | Kiểm tra node zone và AccessMode |
| MongoDB chậm nhưng CPU thấp | Disk I/O latency, page faults/swap | Iostat và WiredTiger cache |
| Data files trên root FS thay vì disk mới | Mount sai hoặc chưa mount | Findmnt/df và kiểm tra trước ghi |
| Backup không restore được | Copy live files hoặc backup thiếu consistency | Chuyển sang backup supported và restore test |
| Mất dữ liệu sau `down -v` | Docker volumes bị xóa | Restore backup, thay deploy runbook |
| Primary failover gây mất write | Write concern/RPO không phù hợp | Review write concern và replica health |
| Thay image xong lỗi startup | UID/version/storage incompatibility | Preflight upgrade, backup, rollback |
| Cùng PVC cho nhiều members | Ghi chung dbPath, thiếu isolation | Volume riêng từng member |
| Disk lớn nhưng query vẫn chậm | IOPS/latency thấp | Đo storage performance thay vì chỉ capacity |
| Database ổn nhưng log làm đầy volume | Log rotation/retention thiếu | Cấu hình log lifecycle |

## 38. Bài tập có đáp án

### Bài 1. MongoDB chạy được nhưng container bị xóa thì dữ liệu biến mất

Một developer chạy MongoDB container, không mount volume. Sau `docker rm` và tạo lại, database trống. Vì sao?

**Đáp án:** Dữ liệu nằm trong writable layer của container cũ, không có persistent volume được tái sử dụng. Cần named volume/bind mount phù hợp tại `dbPath` và backup riêng.

### Bài 2. Có volume rồi còn cần backup không?

MongoDB dùng named Docker volume; developer xóa nhầm toàn bộ collection. Volume có giúp lấy lại dữ liệu cũ không?

**Đáp án:** Không. Volume lưu cả tác động của lệnh xóa. Cần backup/snapshot/PIT strategy phù hợp.

### Bài 3. `bindIp` và quyền filesystem

`mongod` log báo `Permission denied` khi mở WiredTiger file. Đổi `bindIp` thành `0.0.0.0` có giúp không?

**Đáp án:** Không. Đây là lỗi quyền filesystem, không phải network listener. Kiểm tra dbPath, service UID/GID, owner, mount và SELinux/AppArmor.

### Bài 4. Ownership

Thư mục `/srv/mongo-data` có owner root, nhưng MongoDB service chạy bằng UID không root. Có nên chạy `chmod -R 777`?

**Đáp án:** Không. Xác nhận UID/GID và đường dẫn/mount thật rồi cấp quyền tối thiểu qua owner/group/ACL/policy phù hợp.

### Bài 5. Khi disk gần đầy

Operator thấy journal/data files chiếm nhiều dung lượng và muốn xóa thủ công trong `dbPath`.

**Đáp án:** Không được. Đây là file nội bộ của storage engine. Cần điều tra dung lượng, tăng capacity, dùng retention/cleanup qua API và theo runbook chính thức.

### Bài 6. Write concern

Ứng dụng dùng `w:1` trên replica set và primary mất đột ngột. Có thể khẳng định mọi write đã ACK tồn tại sau failover không?

**Đáp án:** Không. `w:1` không có cùng đảm bảo majority acknowledgement. Phải chọn write concern theo RPO và hiểu cấu hình replica set.

### Bài 7. `majority` có thay backup không?

Một user xóa nhầm dữ liệu và thao tác xóa được replicate tới majority.

**Đáp án:** Majority giúp xác nhận thao tác được replicated theo policy, kể cả lệnh xóa nhầm. Nó không giúp phục hồi lịch sử đã bị xóa; cần backup/PIT.

### Bài 8. Cache

Pod có memory limit 2 GiB, WiredTiger cache được cấu hình gần bằng toàn bộ 2 GiB. Rủi ro?

**Đáp án:** MongoDB còn dùng RAM ngoài WiredTiger cache; Pod có thể bị OOM-killed. Cần sizing cache/cgroup phù hợp và đo actual RSS/working set.

### Bài 9. CPU

MongoDB p95 latency tăng sau khi đặt CPU limit rất thấp; disk metrics bình thường. Có thể do đâu?

**Đáp án:** CPU throttling có thể làm query chậm. Kiểm tra cgroup CPU metrics và query workload, điều chỉnh requests/limits có căn cứ.

### Bài 10. Storage

Volume có 500 GiB trống nhưng I/O latency luôn cao, database chậm. Tăng storage size có chắc giải quyết?

**Đáp án:** Không. Cần đánh giá IOPS, throughput, disk latency và volume limits. Capacity và performance là hai chiều khác nhau.

### Bài 11. Systemd `ulimit`

Operator chạy `ulimit -n 100000` trên terminal SSH, nhưng service `mongod` vẫn báo `Too many open files`.

**Đáp án:** Service do systemd quản lý có resource limits riêng. Xem effective `LimitNOFILE` và áp dụng drop-in theo quy trình, không chỉ chỉnh shell đang mở.

### Bài 12. Kubernetes `emptyDir`

MongoDB dùng `emptyDir` làm `dbPath`, Pod bị xóa và tạo lại. Dữ liệu có bảo đảm còn không?

**Đáp án:** Không. `emptyDir` gắn với vòng đời Pod; dùng PVC/PV cho dữ liệu persistent.

### Bài 13. Một PVC cho ba MongoDB members

Ba replica-set members cùng mount một directory để “đỡ tốn disk”.

**Đáp án:** Không phù hợp. Mỗi member phải có data path riêng; MongoDB replication không dùng shared dbPath để đồng bộ.

### Bài 14. StorageClass và zone

PVC được cấp ở zone A, Pod được đặt ở zone B nên không attach được volume.

**Đáp án:** Kiểm tra storage topology, scheduling, binding mode và CSI/zone restrictions; không phải lỗi MongoDB query.

### Bài 15. `fsGroup`

Đã đặt `fsGroup` nhưng Pod vẫn không ghi được PVC.

**Đáp án:** Không phải mọi storage driver và ownership setup hỗ trợ cùng semantics. Kiểm tra effective UID/GID, volume ACL/SELinux, CSI driver và events; không tùy tiện chown toàn volume.

### Bài 16. Disk space và inodes

`df -h` còn nhiều GiB nhưng `mkdir`/ghi file báo hết chỗ.

**Đáp án:** Có thể hết inodes, quota hoặc filesystem read-only; dùng `df -i`, `findmnt` và storage metrics để phân biệt.

### Bài 17. Nâng cấp image

MongoDB image mới chạy bằng UID khác với owner của bind-mounted data directory.

**Đáp án:** Có thể gặp permission denied. Preflight phải kiểm tra UID/GID và chính sách chuyển quyền có kiểm soát; không chạy image mới một cách mù quáng trên volume production.

### Bài 18. Thay `dbPath`

Operator đổi đường dẫn sang volume mới rỗng, rồi thấy database trống dù volume cũ còn dữ liệu.

**Đáp án:** MongoDB đang đọc dbPath khác; cần kiểm tra mount/config và thực hiện data migration nhất quán. Không vội xóa volume cũ hoặc ghi đè.

### Bài 19. Backup thư mục khi đang chạy

Một shell script dùng `cp -r /var/lib/mongodb` khi MongoDB đang có writes. Đây là backup đáng tin cậy không?

**Đáp án:** Không thể giả định. Files có thể được copy ở các thời điểm khác nhau. Dùng logical backup/snapshot/backup service theo quy trình MongoDB hỗ trợ.

### Bài 20. Atlas

Ứng dụng dùng MongoDB Atlas và nhận cảnh báo disk/capacity. Có nên SSH vào node Atlas để chmod hoặc xóa journal?

**Đáp án:** Không. Atlas quản lý node/storage. Kiểm tra cluster sizing/metrics/autoscaling/backup và dùng managed operations phù hợp.

### Bài 21. Dọn volume khi deploy

Team thường chạy `docker compose down -v` trước mỗi deploy. Rủi ro?

**Đáp án:** Có thể xóa named/anonymous volumes theo semantics Compose, làm mất data của MongoDB. Không dùng `-v` cho database persistent khi không có chủ đích và backup.

### Bài 22. Replica set và storage failure domain

Replica set ba members nhưng cả ba data volumes nằm trên cùng một disk backend dễ lỗi.

**Đáp án:** Khi backend hỏng, cả ba members có thể mất dữ liệu/availability. Cần thiết kế failure domains, replication placement và backup độc lập.

### Bài 23. Monitoring

Chỉ monitor CPU và số connections có đủ để bảo đảm MongoDB ổn định không?

**Đáp án:** Không. Còn disk capacity/latency, WiredTiger cache, memory/OOM, file descriptors, replication lag, backups và PVC/mount health.

### Bài 24. FCV

Sau khi nâng cấp binary MongoDB, đội muốn bật mọi feature mới ngay, rồi nếu lỗi chỉ đổi lại binary cũ.

**Đáp án:** Không an toàn. Cần tuân theo đường upgrade/FCV và khả năng downgrade được hỗ trợ, có backup/restore plan. Storage format/feature flags có thể làm rollback phức tạp.

## 39. Checklist vận hành bền vững

### Lưu trữ

- [ ] `dbPath` thực tế đã được xác minh trên đúng filesystem/volume.
- [ ] Data volume sống qua container/Pod recreation theo thiết kế.
- [ ] Backup nằm ngoài cùng failure domain và có restore test.
- [ ] Đã tính disk capacity, index, journal, oplog và upgrade headroom.
- [ ] Storage IOPS/latency đạt SLA under representative load.
- [ ] Filesystem và mount options tương thích với MongoDB/OS version.
- [ ] Không có script xóa/chỉnh trực tiếp WiredTiger files.

### Permissions và security

- [ ] Xác định effective service user/UID/GID trước khi gán ownership.
- [ ] Data/log/keyfile paths chỉ có permissions cần thiết.
- [ ] Đã kiểm tra parent directories, ACL/SELinux/AppArmor/systemd sandbox.
- [ ] Docker bind mounts và Kubernetes PVC phù hợp security context.
- [ ] Không dùng root/chmod 777 như giải pháp mặc định.
- [ ] Secrets, TLS private keys và backups được bảo vệ riêng.

### Resources

- [ ] RAM/cgroup limit có headroom ngoài WiredTiger cache.
- [ ] CPU quotas và throttling được giám sát.
- [ ] Disk latency, IOPS, free capacity và inodes có alert.
- [ ] `NOFILE`/process limits được kiểm tra trên **process thật**, không chỉ shell.
- [ ] Có cảnh báo OOMKilled, CrashLoopBackOff, PVC Pending/attachment errors.
- [ ] Replication lag, oplog và các members được monitor.

### Nâng cấp và phục hồi

- [ ] MongoDB version, FCV và supported upgrade path được xác nhận.
- [ ] Image/package update không thay đổi data path/UID ngoài kế hoạch.
- [ ] Có đủ disk/resource headroom cho migration/index work.
- [ ] Backup đã được kiểm tra và thử restore.
- [ ] Rolling upgrade có thứ tự đúng, giữ quorum/availability.
- [ ] Có kế hoạch rollback thực tế; không chỉ đổi image tag.
- [ ] Đã kiểm tra application reads/writes và durability sau upgrade.

## 40. Tổng kết

**Lưu trữ bền vững** của MongoDB không chỉ là “có ổ đĩa”. Cần bảo đảm `storage.dbPath` nằm trên một volume có vòng đời độc lập với process/container/Pod, filesystem và storage backend đáp ứng nhu cầu ghi bền vững, có đủ capacity lẫn IOPS, và có backup/restore được kiểm chứng. **Write concern, journal, replication và backup** bảo vệ những loại lỗi khác nhau; không thành phần nào thay thế hoàn toàn cho các thành phần còn lại.

**Quyền thư mục** phải dựa trên user/UID/GID thực sự chạy `mongod`, cùng Unix permissions, ACL, SELinux/AppArmor, systemd sandboxing và quyền của container/PVC. `Permission denied` là tín hiệu cần xác định **đúng mount, đúng process, đúng policy**, không phải lời mời chạy root hoặc `chmod 777`.

**Giới hạn tài nguyên** phải được xem như một phần của thiết kế database: WiredTiger cache không phải tổng RAM, CPU quota có thể gây throttling, disk I/O có thể nghẽn khi capacity còn rộng, và file-descriptor limits có thể làm kết nối thất bại. Đối với Docker và Kubernetes, volume lifecycle, cgroups, PVC/StorageClass và topology tạo thêm các lớp cần giám sát.

Trước mọi nâng cấp, hãy ghi nhận version/FCV, data paths, permissions, volume mapping, resource limits và backup. Quy trình vận hành tốt là **quan sát trước, thay đổi đúng lớp, kiểm tra phục hồi và đo lại sau deploy** — thay vì sửa nóng trực tiếp trong thư mục dữ liệu khi sự cố xảy ra.

### Tài liệu tham khảo chính thức theo phiên bản

- [MongoDB Manual — Storage Engines](https://www.mongodb.com/docs/manual/core/storage-engines/)
- [MongoDB Manual — WiredTiger Storage Engine](https://www.mongodb.com/docs/manual/core/wiredtiger/)
- [MongoDB Manual — Journaling](https://www.mongodb.com/docs/manual/core/journaling/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Configuration Options](https://www.mongodb.com/docs/manual/reference/configuration-options/)
- [MongoDB Manual — Production Notes](https://www.mongodb.com/docs/manual/administration/production-notes/)
- [MongoDB Manual — UNIX ulimit Settings](https://www.mongodb.com/docs/manual/reference/ulimit/)
- [MongoDB Manual — Upgrade Procedures](https://www.mongodb.com/docs/manual/release-notes/)
- [Kubernetes Documentation — Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [Kubernetes Documentation — StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)
