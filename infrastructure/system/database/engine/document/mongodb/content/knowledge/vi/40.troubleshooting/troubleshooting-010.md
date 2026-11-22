# Replication lag, mất quorum và oplog không đủ cho đồng bộ trong MongoDB

## 1. Mở đầu: ba sự cố dễ bị nhầm lẫn

Một hệ thống dùng MongoDB replica set gồm ba node:

```text
                        Java Application
                               |
                               v
                     Replica Set rsOrders
                               |
             +-----------------+----------------+
             |                 |                |
             v                 v                v
           mongo-a           mongo-b          mongo-c
           PRIMARY           SECONDARY        SECONDARY
           writes            replay oplog     replay oplog
```

Trong một ngày vận hành, đội kỹ thuật thấy ba cảnh báo:

1. `mongo-b` chậm hơn primary 45 giây.
2. Mất kết nối tới hai node, ứng dụng không tìm được primary.
3. `mongo-c` ngừng nhiều ngày, quay lại nhưng không thể bắt kịp oplog.

Cả ba đều liên quan replication, nhưng nguyên nhân và cách xử lý **không giống nhau**:

- **Replication lag:** secondary vẫn có khả năng đồng bộ, nhưng vị trí đã áp dụng dữ liệu thấp hơn nguồn.
- **Mất quorum:** replica set thiếu số phiếu bầu cần thiết để bầu hoặc duy trì primary; writes có thể không khả dụng, dù một vài process `mongod` vẫn chạy.
- **Oplog không đủ:** secondary cần các thay đổi quá cũ đã bị loại khỏi oplog của nguồn phù hợp; nó không thể chỉ `getMore` hoặc tăng tốc để phục hồi khoảng thiếu, thường phải thực hiện **initial sync/resync** theo thủ tục được hỗ trợ.

> **Ưu tiên xử lý:** bảo vệ dữ liệu và xác định nguồn sự thật trước; khôi phục majority và kết nối an toàn; mới tối ưu lag hoặc xây lại member. Không `force reconfig`, xóa `dbPath` hay khởi động nhiều primary độc lập chỉ vì thấy hệ thống không ghi được.

---

## 2. Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích replication dùng oplog và vai trò primary, secondary, sync source.
- Đọc `rs.status()`, các `optime`, `lastHeartbeat`, `syncSourceHost`.
- Phân biệt replication lag, replication delay được cấu hình và application read staleness.
- Tính **oplog window** dựa trên entry cũ nhất/mới nhất, hiểu tác động của write burst.
- Biết vì sao lag có thể dẫn tới secondary quá stale để bắt kịp.
- Tính majority voting và xác định vì sao không có primary.
- Phân biệt election quorum với `writeConcern: "majority"` trong replica set có arbiter.
- Xử lý mất mạng, host restart, disk full, election loop, slow apply.
- Chọn khi nào nên sửa đường replication, khi nào phải initial sync.
- Lập runbook an toàn với điều kiện dừng và kiểm tra sau khôi phục.
- Viết ứng dụng Java có timeout, retry và idempotency phù hợp failover.
- Thiết kế cảnh báo có ý nghĩa, thực hành lab và kiểm tra tính an toàn.

---

# PHẦN I — NỀN TẢNG CỦA REPLICATION

## 3. Primary ghi gì vào oplog?

Trong một replica set, các data-bearing members dùng **oplog** để đồng bộ các thay đổi.

```text
Client write
    |
    v
PRIMARY áp dụng thay đổi dữ liệu
    |
    v
Ghi lịch sử replication vào oplog
    |
    +---- SECONDARY B tải records ----> áp dụng thay đổi
    |
    +---- SECONDARY C tải records ----> áp dụng thay đổi
```

Oplog được lưu ở collection hệ thống:

```text
local.oplog.rs
```

Đây là **capped collection** hoặc cơ chế oplog có giới hạn lưu trữ theo các quy tắc server version. Khi lịch sử vượt ngưỡng giữ lại, các entry cũ được loại để nhường chỗ cho entry mới.

### 3.1. Oplog không phải audit log vĩnh viễn

Không dùng oplog như một kho lưu mọi thay đổi trong nhiều năm. Nó phục vụ replication và những hoạt động phụ thuộc change history như Change Streams.

### 3.2. Oplog chứa các thao tác replication

Có thể có insert, update, delete, transaction-related entries và các thao tác nội bộ theo định dạng release. Không suy luận rằng một business request luôn tạo đúng một oplog entry.

### 3.3. Secondary không đọc document gốc mỗi lần đồng bộ

Sau initial sync, secondary thường kéo các oplog entries cần thiết từ sync source rồi áp dụng. Nếu thiếu một đoạn lịch sử đã bị cắt, chỉ có document hiện tại ở primary **không đủ** để phục hồi bằng incremental replication bình thường.

---

## 4. Các thành viên trong replica set

| Member state | Ý nghĩa vận hành |
| --- | --- |
| `PRIMARY` | Có thể nhận writes được định tuyến tới primary |
| `SECONDARY` | Theo dõi và áp các thay đổi từ nguồn |
| `STARTUP2` | Trong các pha khởi động/initial sync theo release |
| `RECOVERING` | Chưa sẵn sàng phục vụ như secondary bình thường |
| `ROLLBACK` | Đang xử lý divergence của một nhánh dữ liệu |
| `ARBITER` | Có quyền vote nhưng không lưu bản sao dữ liệu |
| `DOWN`/unreachable | Thành viên không thể liên lạc theo quan sát |
| `UNKNOWN` | Node chưa xác định trạng thái member khác |

State là tín hiệu quan trọng nhưng **không đủ** để kết luận lag hay an toàn dữ liệu. Một node `SECONDARY` có thể chậm nhiều phút; một node `PRIMARY` có thể không thỏa majority write concern nếu topology chỉ còn một bản dữ liệu.

### 4.1. Hidden member

Một hidden secondary không được ưu tiên trong lựa chọn đọc thông thường, và phải có `priority: 0`. Nó vẫn có thể tham gia voting nếu được cấu hình có vote. Không coi hidden là “không ảnh hưởng quorum”.

### 4.2. Delayed member

Delayed secondary cố tình áp oplog muộn theo `secondaryDelaySecs` ở các phiên bản tương ứng. Lag lớn trên member này **có thể là thiết kế**, không phải lỗi. Nhưng nó vẫn cần đủ oplog để duy trì delay và khả năng catch-up.

### 4.3. Non-voting member

`votes: 0` không tính vào election voting majority. Tuy vậy node có thể đóng góp các bản sao dữ liệu và phục vụ mục đích dự phòng/đọc theo giới hạn. Phải kiểm tra cả `votes` và `priority`.

---

## 5. `optime`: secondary đang ở vị trí nào?

Một replica set theo dõi các mốc replication, thường gồm:

- **Last applied optime:** entry mới nhất node đã áp vào dữ liệu.
- **Last durable optime:** entry đã được ghi bền vững theo semantics của storage engine.
- **Last committed optime:** majority commit point của replica set.
- **Primary latest optime:** vị trí thay đổi mới nhất được quan sát trên primary.

Các trường chính xác và cấu trúc kết quả có thể khác giữa MongoDB versions.

### 5.1. Lag theo thời gian

Một ước lượng trực quan:

```text
Primary latest applied:   14:00:00
Secondary latest applied: 13:59:20

Replication lag ≈ 40 giây
```

Đây là **ước lượng khoảng cách thời gian giữa oplog operations**, không nhất thiết bằng chính xác latency để một write được nhìn thấy trong API.

### 5.2. Lag theo số thao tác

Nếu primary ghi 100.000 ops/s, lag 10 giây có thể tương ứng backlog rất lớn. Nếu workload im lặng, timestamps có thể làm phép so sánh đơn giản kém hữu ích.

### 5.3. NTP và clock skew

Các node cần đồng hồ ổn định. Nếu clock lệch, metrics dựa vào timestamp có thể gây hiểu lầm. Không dùng một phép trừ wall-clock thô làm kết luận duy nhất.

---

## 6. Majority commit point khác secondary latest applied

Một write có thể được primary nhận nhưng chưa được majority data-bearing members xác nhận. Trong tình huống failover, những writes chưa được majority acknowledged có thể có rủi ro rollback theo semantics replication.

Ví dụ:

```text
A PRIMARY:   applied up to op 110
B SECONDARY: applied up to op 108
C SECONDARY: applied up to op 105

Majority applied boundary có thể ở 108,
nhưng cần xem server's lastCommittedOpTime thực tế.
```

`lastCommittedOpTime` là thông tin do server duy trì; không tự tính thay bằng median của vài timestamps rồi tuyên bố kết quả chính xác.

### 6.1. `w: 1` và `w: "majority"`

- `w: 1`: primary có thể xác nhận write trước khi secondary apply.
- `w: "majority"`: đợi số data-bearing voting members theo quy tắc majority write concern của deployment.
- `wtimeout` có thể trả lỗi nếu chưa đủ acknowledgments đúng hạn.

### 6.2. Timeout không phải rollback

Một `writeConcern` timeout **không bảo đảm write đã bị hoàn tác**. Write có thể đã được primary áp dụng và sau đó replicate thành công. Ứng dụng phải xác minh outcome trước khi retry side effect không idempotent.

---

## 7. Replication pipeline nhìn từ secondary

Một secondary cần:

1. Kết nối tới sync source phù hợp.
2. Fetch những oplog records chưa nhận.
3. Duy trì buffer/queue và tải dữ liệu theo khả năng.
4. Áp dụng các thay đổi vào collections/indexes.
5. Ghi nhận applied/durable optime.
6. Theo dõi majority commit point và state.

Một nút có thể chậm ở bất kỳ pha nào.

```text
Sync source --> Network fetch --> Receive buffer --> Apply --> Disk durability
                   |                  |               |           |
                bandwidth           memory          CPU/index     IOPS
```

### 7.1. Slow fetch và slow apply khác nhau

Nếu network throughput thấp, secondary không nhận đủ events. Nếu nhận nhanh nhưng CPU/disk yếu, apply backlog tăng. Hai bottlenecks cần cách xử lý khác nhau.

### 7.2. Sync source không nhất thiết luôn là primary

MongoDB có thể dùng **chained replication** và secondary có thể đồng bộ từ một secondary khác. Vì vậy khi tìm sự cố cần xem `syncSourceHost`, không chỉ nhìn trực tiếp primary.

### 7.3. Flow control

MongoDB có cơ chế flow control trong một số phiên bản/topology để giảm tốc độ nhận writes của primary khi replication lag có nguy cơ ảnh hưởng majority commit. Flow control giúp giảm chênh lệch nhưng có thể làm **primary write latency tăng**, không thay thế việc tăng năng lực secondary.

---

# PHẦN II — CHẨN ĐOÁN REPLICATION LAG

## 8. Kiểm tra trạng thái đầu tiên

Kết nối bằng `mongosh` với quyền phù hợp, ưu tiên trực tiếp tới primary khi có thể:

```javascript
rs.status();
```

Hoặc:

```javascript
db.adminCommand({
  replSetGetStatus: 1
});
```

Tìm những thông tin:

- `set`, `date`, `myState`.
- `members[].name`, `health`, `stateStr`.
- `members[].optime`, `optimeDate`.
- `members[].lastHeartbeat`, `lastHeartbeatRecv`.
- `members[].lastHeartbeatMessage`.
- `members[].syncSourceHost`.
- `optimes.lastCommittedOpTime` và các mốc applied/durable nếu server trả.

### 8.1. Tập hợp nhanh vài trường quan trọng

```javascript
const status = rs.status();

printjson({
  replicaSet: status.set,
  observedAt: status.date,
  members: status.members.map(m => ({
    name: m.name,
    state: m.stateStr,
    health: m.health,
    optimeDate: m.optimeDate,
    syncSourceHost: m.syncSourceHost,
    lastHeartbeat: m.lastHeartbeat,
    lastHeartbeatMessage: m.lastHeartbeatMessage
  }))
});
```

**Lưu ý:** các field có thể `undefined` nếu member down hoặc server version không cung cấp. Không ép một node không phản hồi phải có `optimeDate` hiện tại.

### 8.2. Nếu không có primary

`rs.status()` có thể chạy trên một member có thể kết nối, nhưng một số admin actions hoặc helpers cần primary. Đừng coi việc một lệnh không chạy được là bằng chứng dữ liệu đã mất.

---

## 9. Các helper trong mongosh

Trên môi trường được hỗ trợ:

```javascript
rs.printReplicationInfo();
rs.printSecondaryReplicationInfo();
```

`rs.printReplicationInfo()` cung cấp các thông tin về oplog size và time range hiện có. `rs.printSecondaryReplicationInfo()` hiển thị các thông tin về độ trễ secondary dựa trên quan sát.

### 9.1. Đừng coi helper là nguồn dữ liệu tuyệt đối

Helper có thể:

- Trả dữ liệu tại một thời điểm khác nhau giữa members.
- Không có output như kỳ vọng khi primary không tồn tại.
- Báo lag trên delayed member dù đó là cấu hình có chủ đích.
- Không phân biệt rõ slow apply với slow fetch.
- Bị ảnh hưởng network và cách biểu diễn timestamp.

Kết hợp với `rs.status()`, metrics, logs và quan sát ứng dụng.

### 9.2. Đối chiếu với Atlas/monitoring

Nếu dùng MongoDB Atlas, có các metrics replication lag, oplog window và trạng thái node theo tier/version. Nên dùng chúng cùng sự kiện election và write latency để xác định mốc lag bắt đầu tăng.

---

## 10. Phân loại lag theo mẫu biến động

| Mẫu quan sát | Giả thuyết ưu tiên |
| --- | --- |
| Lag tăng dần đều | Secondary apply/fetch chậm hơn source write rate |
| Lag đột biến khi import | Write burst làm tăng lượng oplog |
| Lag tăng sau restart secondary | Cache lạnh, disk pressure, catch-up |
| Một member chậm, hai member khỏe | Node-specific CPU/IOPS/network/disk |
| Mọi secondary chậm | Primary quá tải writes, network chung, cấu hình/hardware |
| Lag cố định 1 giờ trên một member | Có thể delayed secondary được cấu hình |
| Lag tăng rồi giảm theo giờ | Workload peak hoặc backup/index build |
| Lag đi cùng `getMore` errors | Sync source/network/history issue |
| Lag lớn kèm `RECOVERING` | Node chưa sẵn sàng; có thể stale |
| Lag giảm nhưng `w:majority` vẫn timeout | Xem voting/data-bearing topology và majority commit |

### 10.1. Mẫu “lag 30 giây” tự nó chưa phải severity

Nếu RPO/chính sách reads yêu cầu dữ liệu cập nhật trong 1 giây, 30 giây nghiêm trọng. Nếu một reporting secondary được phép chậm vài phút, 30 giây có thể chấp nhận.

### 10.2. Đánh giá xu hướng

Lag 5 phút nhưng giảm nhanh có thể ít nguy hiểm hơn lag 30 giây nhưng **đang tăng liên tục** với tốc độ lớn. Phải theo dõi backlog và oplog window.

---

## 11. Nguyên nhân nhóm A: secondary thiếu CPU

Secondary phải áp operations, duy trì indexes và xử lý reads nếu được dùng đọc.

Nguyên nhân:

- CPU bị saturated.
- Quá nhiều concurrent analytical queries trên secondary.
- Index maintenance nặng.
- Compression/decompression.
- Container CPU limits quá thấp.
- Host bị noisy neighbor.

### 11.1. Tín hiệu

- CPU cao kéo dài.
- Replication lag tăng khi report queries chạy.
- Disk IOPS chưa chắc đã saturated.
- Application secondary reads chậm.
- Sau khi dừng reporting workload, lag bắt đầu giảm.

### 11.2. Xử lý

- Giảm/điều tiết báo cáo và aggregations nặng.
- Scale compute theo supported topology.
- Tối ưu indexes/queries.
- Tách workload analytical sang reporting cluster/dedicated read nodes theo nhu cầu.
- Tránh đặt index build hoặc batch export nặng vào thời điểm replication đang yếu.

**Không** thay secondary bằng arbiter để “giảm CPU” khi cần durability hoặc majority writes.

---

## 12. Nguyên nhân nhóm B: disk I/O và cache pressure

Replication apply tạo writes và index updates trên secondary. Disk latency cao có thể làm apply rate giảm.

Đo:

- Read/write IOPS.
- Disk await/service time.
- Queue depth.
- Disk utilization.
- WiredTiger cache pressure/eviction.
- Journal latency.
- Free disk và inode availability.
- Cloud volume throughput limits.

### 12.1. Secondary không có nghĩa ít tải

Secondary vẫn phải ghi dữ liệu và indexes gần tương đương về khối lượng thay đổi. Nếu vừa nhận reads nặng vừa apply oplog, có thể bị quá tải.

### 12.2. Disk đầy là sự cố nghiêm trọng

Nếu disk còn rất ít dung lượng, secondary có thể không ghi thêm được và tụt lại cho đến khi history bị mất. Không “cứ chờ replica tự xử lý”; cần giảm pressure, mở rộng volume hoặc giải phóng những dữ liệu **được phép** xóa theo runbook.

### 12.3. Không xóa file storage một cách thủ công

Không tự xóa files trong `dbPath`, WiredTiger data files hoặc `local.oplog.rs` để lấy dung lượng. Điều đó có thể làm member không khởi động hoặc mất consistency.

---

## 13. Nguyên nhân nhóm C: network fetch và sync source

Dấu hiệu:

- Một node có packet loss hoặc RTT cao.
- Firewall/security group chặn cổng MongoDB.
- DNS trỏ sai IP.
- TLS/certificate không hợp lệ.
- Authentication nội bộ sai keyfile/certificates.
- Sync source không reachable.
- Network bandwidth nhỏ hơn lượng oplog phát sinh.
- Cross-region link có latency lớn.

### 13.1. `syncSourceHost` là trường hữu ích

```javascript
rs.status().members.map(m => ({
  host: m.name,
  source: m.syncSourceHost,
  state: m.stateStr
}));
```

Nếu `mongo-c` đồng bộ từ `mongo-b`, sự cố `mongo-b` có thể ảnh hưởng cả `mongo-c` dù primary vẫn khỏe.

### 13.2. Chained replication không mặc định có lỗi

Chained replication là thiết kế được MongoDB hỗ trợ. Chỉ đánh giá là bất lợi khi đường sync source cụ thể gây lag, chậm hoặc không có history cần thiết.

### 13.3. Thay sync source

MongoDB có cơ chế chọn sync source tự động và admin helper trên những phiên bản hỗ trợ. Không thay đổi ép sync source hoặc configuration tùy tiện khi chưa hiểu topology, vì source được chọn phải có oplog cần thiết và chất lượng kết nối phù hợp.

---

## 14. Nguyên nhân nhóm D: write burst, bulk import và index churn

Tại primary:

```text
Normal:
  5,000 oplog events/min
  oplog window ~ 24 hours

Bulk migration:
  400,000 oplog events/min
  oplog window rapidly shrinks
```

Nếu secondary đang lag vì network và primary tiếp tục tạo nhiều oplog entries, khoảng lịch sử có sẵn có thể giảm nhanh.

### 14.1. Những công việc dễ kích hoạt

- Bulk writes/backfill.
- Sửa nhiều documents bằng `updateMany`.
- Xóa khối lượng lớn.
- TTL cleanup backlog.
- Schema migration.
- Tạo nhiều indexes trong khoảng tải lớn.
- Nhiều transactions lớn theo semantics của release.
- Service tạo nhiều write amplification events.

### 14.2. Không đổ lỗi cho TTL một cách tự động

TTL deletes có thể tạo lượng writes đáng kể khi backlog lớn, nhưng cần số liệu `metrics.ttl` và oplog/write rate trước khi kết luận.

### 14.3. Rate-limit bulk jobs

Một bulk migration có thể chạy chậm hơn một chút để giữ ổn định replication và tránh thu hẹp oplog window quá mức. Ngưỡng phụ thuộc headroom thực tế và SLO.

---

## 15. Nguyên nhân nhóm E: cấu hình member có chủ đích

Trước khi báo incident, kiểm tra:

```javascript
rs.conf();
```

Tìm:

- `priority`.
- `votes`.
- `hidden`.
- `secondaryDelaySecs`.
- `buildIndexes`.
- Tags/replica set settings liên quan.
- Sync source topology.

Một delayed secondary với `secondaryDelaySecs: 3600` có thể luôn chậm khoảng một giờ theo chủ đích. Nếu monitoring gộp tất cả members mà không phân loại, hệ thống báo lag giả suốt ngày.

### 15.1. Delayed secondary vẫn cần oplog đủ rộng

Nếu delay 1 giờ nhưng oplog window chỉ 40 phút, node khó duy trì trì hoãn như thiết kế. Cần đủ lịch sử để các operations delayed vẫn còn khả dụng.

### 15.2. Hidden có thể vote

Member `hidden:true` không đồng nghĩa `votes:0`. Khi tính quorum, phải đọc giá trị `votes` thực tế.

---

## 16. Flow control: lag liên quan trực tiếp độ trễ ghi

Trong một số deployment, khi lag ảnh hưởng khả năng majority commit, primary có thể giảm tốc độ cấp ticket writes thông qua replication flow control.

Sơ đồ:

```text
Secondary apply falling behind
             |
             v
Majority commit point advances slowly
             |
             v
Primary flow control may engage
             |
             v
Application write latency increases
```

Các metrics có thể xuất hiện trong `db.serverStatus().flowControl` theo MongoDB version.

```javascript
const server = db.serverStatus();
printjson(server.flowControl);
```

### 16.1. Không tắt flow control tùy tiện

Tắt flow control khi chưa hiểu nguyên nhân có thể làm primary chạy xa hơn secondaries, khiến lag và oplog pressure nặng hơn. Cần sửa resource bottleneck hoặc điều chỉnh workload dựa trên tài liệu/version và khuyến nghị vận hành.

---

# PHẦN III — MẤT QUORUM VÀ KHÔNG CÓ PRIMARY

## 17. Quorum nghĩa là gì?

**Election quorum** là số phiếu bầu cần thiết để bầu/duy trì primary.

Với tổng số voting members là `V`:

```text
election majority = floor(V / 2) + 1
```

Ví dụ:

| Voting members | Cần cho majority |
| ---: | ---: |
| 1 | 1 |
| 2 | 2 |
| 3 | 2 |
| 4 | 3 |
| 5 | 3 |
| 7 | 4 |

Không lấy tổng **mọi member** làm `V`; phải tính những members có `votes:1`.

### 17.1. Ba member, một node down

```text
A PRIMARY    UP
B SECONDARY  UP
C SECONDARY  DOWN

Votes reachable: 2/3
Election majority: 2
```

Có thể duy trì/bầu primary trong điều kiện các ràng buộc election khác đạt.

### 17.2. Ba member, hai nodes down

```text
A formerly PRIMARY  UP
B SECONDARY         DOWN
C SECONDARY         DOWN

Votes reachable: 1/3
Election majority: 2
```

Không đủ election quorum. Replica set không thể an toàn duy trì primary để nhận writes như bình thường.

### 17.3. Một process còn chạy không có nghĩa có primary

Client có thể kết nối trực tiếp tới `mongod`, nhưng lệnh write thông thường vẫn không được phép nếu node không ở trạng thái primary phù hợp.

---

## 18. Arbiter: có vote nhưng không giữ dữ liệu

Topology:

```text
A PRIMARY    data-bearing, votes=1
B SECONDARY  data-bearing, votes=1
C ARBITER    no data,      votes=1
```

Nếu B down, A+C vẫn có **election majority** 2/3. Nhưng chỉ còn **một data-bearing member**.

### 18.1. Majority write concern trong PSA

`w:"majority"` cần xác nhận theo majority data-bearing voting members; arbiter không lưu và xác nhận data writes như secondary. Khi B không khả dụng, `w:"majority"` có thể không thỏa và writes sẽ chờ/timeout theo write concern.

**Do đó: có thể có PRIMARY nhưng ứng dụng vẫn gặp writeConcern timeouts.**

### 18.2. Không dùng arbiter như bản sao dữ liệu

Arbiter không hỗ trợ restore dữ liệu, không thực hiện normal secondary reads và không thay backup.

### 18.3. Implicit default write concern có thể khác

Một số replica set topologies có arbiter ảnh hưởng cách MongoDB xác định implicit default write concern. Không giả định mọi deployment mặc định `w:"majority"`; kiểm tra `getDefaultRWConcern` và cấu hình ứng dụng theo release.

---

## 19. Quorum và availability của readers

Trong sự cố không còn primary:

- Writes qua replica set thông thường không khả dụng.
- Primary read preference không tìm được nguồn đọc.
- Một số reads từ secondary có thể còn hoạt động nếu cấu hình/read concern cho phép.
- Dữ liệu đọc từ secondary có thể **stale**.
- Những operation cần majority commit/snapshot có giới hạn khác nhau.

Không dùng khả năng đọc secondary làm bằng chứng replica set đang phục vụ giao dịch bình thường.

---

## 20. Vì sao election không xảy ra dù có đủ votes?

Quorum là điều kiện cần, không phải điều kiện duy nhất. Những nguyên nhân:

- Voting members không thực sự liên lạc hai chiều.
- Candidate không eligible do `priority:0`.
- Candidate chưa đủ cập nhật theo quy tắc election.
- Replica set config/term chưa thống nhất.
- Có initial sync hoặc RECOVERING member.
- Network partition/heartbeat failures.
- Authentication/TLS nội bộ lỗi.
- Một số member clock skew/stale state.
- Election đang chạy, chưa hoàn tất.

### 20.1. Priority 0 và delayed/hidden

Member `priority:0` không được bầu primary. Nếu mọi data-bearing node còn reachable đều priority 0, không thể kỳ vọng một member nào tự trở thành primary mặc dù tổng votes có vẻ đủ.

### 20.2. Last optime quan trọng

Một member quá lạc hậu không nên được chọn làm primary nếu điều đó vi phạm yêu cầu election freshness. Hệ thống ưu tiên an toàn replication hơn việc “cứ bầu đại một node”.

---

## 21. Split-brain và vì sao không nên ép primary

Một network partition có thể chia 5 voters thành:

```text
Partition A: 3 voting members
Partition B: 2 voting members
```

Chỉ phía có majority phù hợp mới có quyền bầu/duy trì primary theo thuật toán. Đây là cơ chế tránh hai primary nhận writes đồng thời.

### 21.1. Force reconfig có thể phá giới hạn an toàn

Một số admin command hỗ trợ `rs.reconfig(..., { force: true })` trong tình huống khẩn cấp, nhưng MongoDB cảnh báo nó có thể dẫn tới dữ liệu diverge/rollback của những writes đã acknowledged trước đó tùy cấu hình và sự kiện.

**Không sử dụng force reconfig như bước xử lý mặc định** khi mất quorum. Chỉ cân nhắc theo official disaster recovery procedure, sau khi bảo vệ dữ liệu, kiểm tra latest opTime/backups và có DBA/SRE phê duyệt.

### 21.2. Tuyệt đối không khởi tạo replica set mới trên từng node còn sống

Nếu hai partitions bị đưa thành hai replica sets độc lập rồi cùng nhận writes, kết quả có thể là divergent branches không thể “merge tự động”.

---

## 22. Tình huống mất một data center

Giả sử 5 voting members được đặt:

```text
DC1: A, B, C   (3 votes)
DC2: D, E      (2 votes)
```

Nếu DC1 down, DC2 còn 2/5 votes: **không đủ majority**.

Ngược lại mất DC2, DC1 còn 3/5: có thể tiếp tục election/primary.

### 22.1. Placement phải dựa vào failure domains

Đặt 5 members trong cùng một availability zone không giúp chịu lỗi cả zone dù quorum toán học đúng.

### 22.2. Arbiter ở third site

Thêm arbiter chỉ để có một vote thứ ba có thể giúp election availability cho một số PSA topologies, nhưng không tăng copies dữ liệu và không thay thế majority write durability. Cần đánh giá network latency, partition behavior và policy.

### 22.3. Data center outage không đồng nghĩa mất dữ liệu

Nếu còn quorum và dữ liệu được majority acknowledged, cluster có khả năng duy trì trạng thái an toàn. Nếu không đủ quorum, cần khôi phục kết nối/member thay vì mặc định bắt đầu từ backup.

---

## 23. Lỗi ứng dụng khi mất primary

Java MongoDB Driver có thể báo:

- Server selection timeout vì không tìm được primary.
- `NotWritablePrimary` hoặc những lỗi thay đổi trạng thái replica.
- Network exceptions khi connection bị đóng.
- Write concern timeout khi thiếu acknowledgments.
- Transient transaction errors khi election làm gián đoạn transaction.

### 23.1. Không coi mọi lỗi là “MongoDB đã mất dữ liệu”

Phân biệt:

- Lệnh không được gửi vì không tìm được primary.
- Lệnh gửi tới primary cũ rồi mất phản hồi.
- Write đã áp dụng ở primary nhưng chưa đạt write concern.
- Transaction commit kết quả không rõ.
- Read preference chọn secondary stale.

Chính sách retry và reconciliation phụ thuộc outcome category.

---

# PHẦN IV — OPLOG WINDOW VÀ SECONDARY QUÁ STALE

## 24. Oplog window là gì?

**Oplog window** là khoảng thời gian được bao phủ bởi entry cũ nhất và mới nhất còn nằm trong oplog hiện tại.

```text
Oldest entry                         Newest entry
    |                                     |
    v                                     v
  10:00 ------------------------------ 14:00
                 4 hours
```

Nó trả lời: lịch sử replication có thể phục vụ việc bắt kịp từ khoảng thời gian nào?

### 24.1. Oplog window không cố định theo giờ nếu không có chính sách retention thích hợp

Một oplog size cố định lưu trữ theo **dung lượng**, không phải một mốc thời gian cố định:

- Khi ít writes, window có thể dài.
- Khi nhiều writes, window có thể ngắn.
- Một batch migration lớn có thể làm window co rất nhanh.

### 24.2. Oplog window không phải RPO

RPO phụ thuộc write concern, backup và cutover behavior. Oplog window chỉ là một chỉ số về **lịch sử thay đổi còn sẵn để replication/resume**.

---

## 25. Cách xem oplog window

Trên data-bearing replica set member:

```javascript
rs.printReplicationInfo();
```

Helper có thể in:

- Configured oplog size.
- Actual oplog size.
- Thời điểm entry đầu và cuối.
- `oplog length start to end` tính theo thời gian.

### 25.1. Xem collection local.oplog.rs

```javascript
const oplog =
    db.getSiblingDB("local").getCollection("oplog.rs");

printjson(oplog.stats());
```

Nếu cần quan sát entries biên:

```javascript
const oldest = oplog.find()
    .sort({ $natural: 1 })
    .limit(1)
    .toArray();

const newest = oplog.find()
    .sort({ $natural: -1 })
    .limit(1)
    .toArray();

printjson({
  oldest: oldest[0],
  newest: newest[0]
});
```

**Cảnh báo:** oplog entries có thể chứa chi tiết dữ liệu/thao tác nhạy cảm và output rất lớn. Không log thô mọi oplog entry hoặc truy vấn toàn bộ oplog trong incident.

### 25.2. Lấy một mốc quan sát nhất quán

Đọc primary và secondary ở những thời điểm khác nhau có thể cho window khác. Ghi lại node, thời điểm, version và công cụ đo.

---

## 26. Tính window bằng tốc độ ghi và kích thước oplog

Một phép tính sơ bộ:

```text
Oplog allocated:       40 GiB
Avg oplog generation:   5 GiB/hour

Estimated window ≈ 8 hours
```

Nếu workload peak tăng lên 20 GiB/hour:

```text
Estimated window ≈ 2 hours
```

### 26.1. Vì sao chỉ là ước lượng?

- Oplog capped/retention behavior tùy version.
- Compression và representation khác nhau.
- Oplog entry sizes không đều.
- Burst writes.
- Transactions và internal operations.
- Minimum retention policy nếu được cấu hình.
- Disk capacity và storage engine behavior.

### 26.2. Công thức sizing thực hành

```text
Required history >= maximum tolerated replication outage
                 + worst-case catch-up duration
                 + maintenance/failover headroom
```

Nếu tổ chức cần node có thể offline 12 giờ và catch-up thêm 4 giờ, một oplog window chỉ 6 giờ trong peak là không đủ.

---

## 27. Khi nào secondary thành “too stale to catch up”?

Giả sử secondary dừng ở oplog timestamp:

```text
Secondary latest applied: 10:00

Primary oplog still contains:
  oldest  = 11:30
  newest  = 16:00
```

Secondary cần các operations từ ngay sau 10:00, nhưng sync source không còn dữ liệu trước 11:30. Có một **khoảng hở lịch sử**.

```text
Secondary needs:
    10:00 -> 16:00

Source has:
             11:30 -> 16:00

Missing:
    10:00 -> 11:30
```

Không thể chỉ tăng `batchSize`, tăng CPU hay retry `getMore` để khôi phục các oplog entries đã bị loại.

### 27.1. Hệ quả

MongoDB có thể báo secondary quá stale trong logs và không thể tiếp tục incremental replication. Node có thể ở trạng thái `RECOVERING` hoặc state khác theo release.

### 27.2. Xác định đúng nguyên nhân

Không phải mọi secondary `RECOVERING` đều quá stale. Nó cũng có thể đang:

- Recovering sau restart.
- Đang xử lý rollback.
- Initial sync.
- Chờ ổn định sync source.
- Gặp lỗi disk/network/auth.
- Gặp sự cố storage.

Phải xem logs, oplog boundaries và `rs.status()`.

---

## 28. Tăng oplog sau khi đã mất history có giúp không?

**Không khôi phục các entry đã bị cắt.**

Tăng oplog size hoặc minimum retention **trước khi** outage dài có thể giúp tránh thành stale; nhưng sau khi gap đã xuất hiện, mở rộng oplog không làm lịch sử đã xóa quay lại.

### 28.1. Cơ hội với sync source khác

Nếu replica set còn một data-bearing member khác **vẫn giữ đủ history**, secondary có thể có đường sync phù hợp. Điều này cần kiểm tra khả năng tương thích, sync source selection và release procedures.

Không chọn sync source khác chỉ vì nó đang online: phải xác nhận nó giữ **liên tục** phần lịch sử cần thiết và dữ liệu không diverge.

### 28.2. Nếu không member nào còn history

Thường phải thực hiện **initial sync** để dựng lại dữ liệu từ một nguồn hợp lệ, hoặc sử dụng quy trình resync/backup-based initial sync được hỗ trợ.

---

## 29. Initial sync khác incremental catch-up

| Hoạt động | Mục tiêu | Điều kiện điển hình |
| --- | --- | --- |
| Incremental replication | Áp oplog chưa xử lý | Nguồn còn đầy đủ history |
| Initial sync | Xây lại dữ liệu member từ nguồn phù hợp | Member mới hoặc cần resync |
| Rollback | Loại bỏ writes của nhánh không còn được chọn | Theo replication history/rollback semantics |
| Restore backup | Khôi phục dữ liệu từ backup | Có backup hợp lệ |
| Clone/new member | Tạo node mới lấy bản sao từ nguồn | Có capacity, security/config hợp lệ |

### 29.1. Initial sync không có nghĩa copy một snapshot rồi xong

Nó thường gồm:

1. Chọn sync source.
2. Clone dữ liệu và metadata cần thiết.
3. Tải oplog changes trong thời gian clone.
4. Áp changes để bắt kịp.
5. Chuyển trạng thái khi đủ điều kiện.

Nếu initial sync kéo dài hơn khả năng duy trì history và server không có cơ chế phù hợp, job có thể fail/restart.

### 29.2. Resource requirements

Initial sync có thể dùng nhiều network, disk I/O và CPU trên cả source và destination. Nếu source đang phục vụ production với ít headroom, đồng bộ lại ngay giờ cao điểm có thể làm lag các members còn lại.

---

## 30. Điều kiện trước khi xây lại secondary

Trước bất kỳ thao tác destructive nào, xác minh:

- Đúng **node** cần rebuild; không nhầm primary.
- Replica set còn đủ majority/voting members.
- Có ít nhất một data-bearing source khỏe và có dữ liệu đúng.
- Dữ liệu chưa majority acknowledged cần xử lý theo incident policy.
- Có backup hoặc restore point đã kiểm chứng.
- Không có local-only data cần giữ trên node mục tiêu.
- Storage/disk/net đủ năng lực.
- Version/FCV/tls/auth phù hợp.
- Initial sync procedure được support cho version/topology.
- Có change approval/on-call phối hợp.
- Có kế hoạch chờ catch-up trước khi rebuild member kế tiếp.

### 30.1. Không tự xóa dbPath khi chưa xác định node

Một chỉ dẫn “xóa thư mục `/var/lib/mongodb` rồi restart” có thể phá hủy duy nhất bản sao còn sống nếu người vận hành chọn nhầm host.

### 30.2. Không resync mọi secondaries cùng lúc

Nếu cả B và C cần initial sync, hãy đánh giá thứ tự và capacity. Rebuild đồng loạt có thể để lại chỉ một data-bearing member, ảnh hưởng majority, durability và write availability.

### 30.3. Backup là bắt buộc trước thao tác rủi ro

Một node stale vẫn có thể chứa dữ liệu cần forensic trong trường hợp chưa xác định được lịch sử acknowledged writes. Không xóa dấu vết trước khi có quyết định recovery.

---

## 31. Runbook khái niệm để xử lý một stale secondary

Ví dụ:

```text
A PRIMARY    healthy/current
B SECONDARY  healthy/current
C RECOVERING too-stale
```

Với A/B còn ổn và đủ majorities thích hợp:

1. Xác nhận C đúng là stale bằng logs + oplog boundary.
2. Bảo đảm A/B đang đồng bộ tốt và backup hợp lệ.
3. Chọn quy trình xây lại C theo MongoDB Manual/edition/version.
4. Dừng C theo service manager.
5. Chuẩn bị data directory mới **chỉ cho C**, sau xác minh path/permissions và approval.
6. Khởi động C vào topology hợp lệ để initial sync.
7. Theo dõi initial sync progress, CPU, disk, network, oplog source.
8. Chờ C thành `SECONDARY` và lag về ngưỡng chấp nhận.
9. Kiểm tra majority writes, ứng dụng và monitoring.
10. Chỉ xử lý member khác nếu C đã ổn.

### 31.1. Không cung cấp một dòng lệnh xóa data directory dùng chung

Đường dẫn `dbPath` khác nhau theo service, Docker, Atlas, Windows và deployment automation. Bài học không khuyến khích copy-paste `rm -rf` trên production.

### 31.2. Initial sync có thể được quản lý tự động

Với Atlas, Ops Manager hoặc nền tảng có automation, dùng **quy trình replace/resync member của nền tảng**, không sửa data files thủ công như self-managed.

---

# PHẦN V — RUNBOOK XỬ LÝ SỰ CỐ THEO THỨ TỰ

## 32. Bước 0: xác định mức độ khẩn cấp

Cần phân biệt:

- **SEV-1:** mất primary/quorum, writes ngừng hoàn toàn.
- **SEV-1/2:** nguy cơ mất durability hoặc secondary gần stale.
- **SEV-2:** majority writes timeout/latency cao.
- **SEV-3:** một reporting secondary lag nhưng service vẫn khỏe và trong SLO.

Mức độ cụ thể tùy chính sách tổ chức; đây chỉ là ví dụ.

### 32.1. Thông tin đầu tiên phải ghi nhận

- Từ khi nào bắt đầu?
- Mọi tenants hay một subset?
- Writes có đang thất bại không?
- Read latency/errors?
- Có vừa nâng version/index, backup, maintenance, bulk job không?
- Có node/network/storage alerts?
- Có bản sao nào dữ liệu mới nhất?
- Oplog window hiện tại và lag đang tăng hay giảm?

---

## 33. Bước 1: giữ nguyên bằng chứng và tránh thay đổi phá hoại

Trước khi thực hiện:

- Lưu trạng thái rs.status từ node reachable.
- Lưu logs ở khoảng bắt đầu incident.
- Ghi lại các member `host`, `votes`, `priority`, `health`, `optime`.
- Ghi lại monitoring graph và deployment events.
- Xác nhận backup gần nhất.
- Dừng các bulk jobs không thiết yếu nếu đang gây pressure.
- Không force reconfig/stepdown/restart toàn bộ cluster.

### 33.1. Tại sao không restart mọi thứ?

Restart hàng loạt có thể:

- Làm mất quorum đang còn.
- Đưa secondary đang catch-up trở về trạng thái recover.
- Kéo dài outage.
- Làm dấu vết lỗi khó phân tích.
- Tăng cache cold-start và disk I/O.

### 33.2. Một thay đổi tại một thời điểm

Nếu phải xử lý nhiều điều kiện (network, disk, config), chọn thay đổi có xác suất khôi phục cao và có thể rollback, sau đó quan sát hiệu quả.

---

## 34. Bước 2: xác định topology thực tế

```javascript
const c = rs.conf();

printjson(c.members.map(m => ({
  host: m.host,
  votes: m.votes,
  priority: m.priority,
  hidden: m.hidden,
  secondaryDelaySecs: m.secondaryDelaySecs,
  arbiterOnly: m.arbiterOnly
})));
```

**Lưu ý:** `rs.conf()` cần truy cập một member hợp lệ; nếu không thể, dùng bản cấu hình được lưu từ automation/runbook và đối chiếu khi node hồi phục.

### 34.1. Đừng chỉ nhìn số node online

Phải phân biệt:

- Data-bearing vs arbiter.
- Voting vs non-voting.
- Priority > 0 hay 0.
- Hidden/delayed.
- Thành viên thực sự được kết nối hai chiều.

### 34.2. Ví dụ tính quorum

Replica set có A/B/C/D/E với votes `[1,1,1,0,0]`. Có 5 processes nhưng chỉ **3 voting members**, election majority là **2**, không phải 3.

---

## 35. Bước 3: kiểm tra network và DNS

Nếu thấy `health:0` hoặc heartbeat errors:

- Ping/route chỉ để kiểm tra reachability ở mức phù hợp.
- Kiểm tra TCP port, security group, firewall và load balancer.
- Kiểm tra hostname resolve đồng nhất từ các members.
- Kiểm tra TLS cert SAN, expiry và internal auth.
- Kiểm tra clocks/NTP.
- Kiểm tra packet drops/latency giữa AZ/region.
- Xem có deployment event thay đổi IP/DNS/ports không.

### 35.1. Kết nối một chiều không đủ

Node A có thể gọi B nhưng B không gọi lại được A. Election/replication cần khả năng giao tiếp phù hợp theo các hướng, không chỉ một lần kết nối từ laptop quản trị.

### 35.2. Đừng thay hostnames trong config vội

Thay đổi replica set member hostnames có điều kiện và rủi ro; ưu tiên phục hồi DNS/network theo thiết kế trước.

---

## 36. Bước 4: kiểm tra compute/disk

Đo theo từng member:

- CPU throttling.
- Free RAM/swap pressure.
- Disk free.
- Disk IOPS/latency.
- Journal/storage errors.
- WiredTiger cache eviction.
- Network throughput.
- Container restarts/OOM kills.
- Cloud volume credits và caps.

### 36.1. Nếu một secondary có disk full

Ưu tiên giải phóng dung lượng bằng cách được MongoDB và platform hỗ trợ hoặc mở rộng storage. Không trực tiếp xóa WiredTiger files/oplog entries.

### 36.2. Nếu primary disk full

Đó là rủi ro nghiêm trọng cho write availability và durability. Cần phối hợp incident team, backup và storage recovery; không ép primary nhận writes trên volume đã hết chỗ.

---

## 37. Bước 5: xác định có mất oplog history hay chỉ lag lớn

Quan sát đồng thời:

```javascript
rs.status();
rs.printReplicationInfo();
rs.printSecondaryReplicationInfo();
```

Sau đó đối chiếu:

```text
Latest primary oplog timestamp
Oldest retained source oplog timestamp
Latest applied optime of slow secondary
```

### 37.1. Nếu latest secondary vẫn nằm trong source window

Đường incremental catch-up có thể còn khả dụng; tập trung xử lý throughput/network/apply bottleneck.

### 37.2. Nếu secondary cần lịch sử trước oldest retained entry

Nguy cơ stale; xác minh logs và source khác trước khi chọn initial sync.

### 37.3. Không chỉ so timestamps

Cần đảm bảo history chain/oplog entries phù hợp, tránh dữ liệu diverge hoặc sync source thiếu sự kiện cần thiết. MongoDB tự kiểm tra các điều kiện replication; người vận hành không nên “ghép oplog” thủ công.

---

## 38. Bước 6: bảo vệ quorum trước mọi maintenance

Ví dụ 3 data-bearing members:

```text
A PRIMARY UP
B SECONDARY UP
C SECONDARY LAGGING
```

Nếu quyết định restart B khi C không khỏe, có thể mất data-bearing majority dù C vẫn là member trên config.

### 38.1. Một thay đổi mỗi lần

- Chỉ restart/replace một member.
- Chờ node ổn định và catch-up.
- Đánh giá majority sau mỗi bước.
- Kiểm tra `w:majority` và app writes.
- Không dừng source khỏe phục vụ initial sync nếu có thể tránh.

### 38.2. Ưu tiên khôi phục node cũ trước force reconfig

Nếu một member down do service/network, việc khôi phục đúng node có thể an toàn hơn reconfig vì bảo tồn identity, data và voting membership.

---

## 39. Bước 7: xác minh ứng dụng sau khôi phục

Không dừng ở việc `rs.status()` hiển thị một primary.

Kiểm tra:

- Một write nhỏ có acknowledgment theo chính sách.
- Read-after-write requirement.
- Primary discovery từ Java Driver.
- Transactions/commit behavior.
- Retryable writes phù hợp.
- Replication lag có giảm và ổn định không.
- `lastCommittedOpTime` có tiến lên không.
- Oplog window đủ headroom không.
- Backup/PITR và Change Streams consumers có chạy không.
- Metrics p95/p99/errors trở về SLO.

### 39.1. Không dùng một lệnh ghi test phá business data

Nếu phải kiểm tra writes, dùng collection test/namespace được phép và dọn sau; không insert data giả vào collection nghiệp vụ production.

---

# PHẦN VI — OPLOG SIZING VÀ PHÒNG NGỪA STALE SECONDARY

## 40. Khi nào cần tăng oplog?

Có thể cần tăng capacity hoặc minimum retention nếu:

- Oplog window ngắn hơn maintenance/outage budget.
- Node cross-region thường lag vì network.
- Thường xuyên chạy bulk imports.
- Initial sync cần history dài hơn.
- Change Streams consumers có downtime dài.
- Delayed secondary cần được trì hoãn nhiều giờ.
- Hệ thống có retention headroom thấp vào peak.

### 40.1. Lựa chọn tăng

- Tăng cấu hình oplog size theo command được server hỗ trợ.
- Cấu hình minimum oplog retention hours nếu release hỗ trợ.
- Giảm write bursts/replication lag.
- Cải thiện secondary throughput.
- Điều chỉnh architecture capacity.

### 40.2. Tăng retention không phải miễn phí

Minimum retention có thể khiến oplog **dùng nhiều disk hơn configured size** để giữ các entries đủ lâu theo policy. Cần tính disk headroom và monitoring, nếu không có thể biến lag issue thành disk full issue.

---

## 41. `replSetResizeOplog` ở self-managed MongoDB

Ở các MongoDB versions hỗ trợ dynamic oplog sizing, có lệnh:

```javascript
db.adminCommand({
  replSetResizeOplog: 1,
  size: 16384
});
```

Trong lệnh này `size` thường tính bằng **MiB**: `16384` tương đương khoảng 16 GiB. Command có version/topology/permissions restrictions; thực hiện **trên đúng data-bearing replica set member**, không qua mongos hoặc production không có approval.

Ví dụ thiết lập minimum retention trên release hỗ trợ:

```javascript
db.adminCommand({
  replSetResizeOplog: 1,
  minRetentionHours: 48
});
```

### 41.1. Cần kiểm tra đầy đủ version và cú pháp

Không phải mọi MongoDB version đều hỗ trợ cùng options. Dùng tài liệu `replSetResizeOplog` tương ứng version/edition và cấu hình deployment trước khi áp dụng.

### 41.2. Resize không làm hồi sinh oplog history đã bị cắt

Nếu một secondary đã too stale, tăng size giúp ngăn tình trạng tái diễn, nhưng vẫn cần recovery cho gap hiện tại.

### 41.3. Chọn kích thước theo thực tế

Ví dụ nếu peak generation là 6 GiB/giờ và cần 36 giờ headroom:

```text
6 GiB/h × 36 h = 216 GiB (rough sizing)
```

Cần thêm margin, disk capacity, storage overhead và profile workload để ra cấu hình thực tế.

---

## 42. Oplog minimum retention vs configured size

Hai chính sách khác nhau:

- **Oplog size:** dung lượng mục tiêu/lưu trữ, bị ảnh hưởng tốc độ phát sinh entries.
- **Minimum retention hours:** ngăn cắt những entries còn trẻ hơn một khoảng thời gian định nghĩa, trên release hỗ trợ.

### 42.1. Ví dụ

```text
Configured oplog size:       20 GiB
Minimum retention:          24 hours
Peak generation:            3 GiB/hour

24h history requires:        ~72 GiB
```

Server có thể giữ lượng oplog vượt configured size để đáp ứng minimum retention, phụ thuộc disk và server behavior.

### 42.2. Không dùng minimum retention để vượt giới hạn disk vật lý

Nếu chỉ còn 30 GiB free mà retention cần thêm 70 GiB, chính sách đó có thể làm disk pressure nghiêm trọng.

### 42.3. Alert theo **window thực**, không chỉ cấu hình

Một oplog có size 100 GiB vẫn có thể chỉ giữ vài giờ trong write burst. Đo actual oldest/newest và expected outage.

---

## 43. Tối ưu sync source và placement

Với multi-region topology:

```text
Region A:
  A PRIMARY
  B SECONDARY

Region B:
  C SECONDARY
  D SECONDARY
```

C/D có thể chịu network RTT cao nếu luôn phải fetch xuyên vùng. Chained replication có thể ảnh hưởng nhu cầu bandwidth và khả năng bắt kịp.

### 43.1. Những điều cần cân bằng

- Latency và bandwidth giữa regions.
- Failure domains.
- Khả năng C/D tham gia election.
- Write concern tags hoặc majority.
- Oplog retention.
- Chi phí cross-region traffic.
- Recovery khi một region bị mất.
- Source selection và replication history availability.

### 43.2. Không chọn sync source chỉ dựa vào vị trí gần

Một node gần nhưng đã lag/stale hoặc có disk bottleneck có thể là nguồn tệ. Phải xem thời điểm dữ liệu, oplog window và health.

---

## 44. Backup không thay oplog nhưng hỗ trợ khôi phục

Oplog giúp replication và CDC resume. Backup giúp phục hồi dữ liệu khi oplog/history hoặc primary data không còn hợp lệ.

Một kế hoạch DR cần:

- Scheduled backups.
- PITR phù hợp topology.
- Restore rehearsal.
- Encryption/KMS key retention.
- Backup consistency.
- Phân loại snapshots theo version/FCV.
- Quy trình đưa restored member vào replica set an toàn.
- Đối soát dữ liệu sau restore.

### 44.1. Đừng restore bản cũ rồi lập tức cho bầu primary

Nếu restore member từ snapshot cũ, nó có thể không có recent writes. Phải theo procedure initial sync/recovery và bảo đảm không tạo divergent history.

### 44.2. Backup-only recovery có thể cần RPO tradeoff

Nếu chỉ còn backup trước sự cố, có thể mất recent unbacked-up writes. Đây là quyết định dữ liệu nghiệp vụ cần approval.

---

# PHẦN VII — JAVA DRIVER TRONG SỰ CỐ REPLICATION

## 45. Replica set URI để driver tự khám phá primary

Ví dụ:

```text
mongodb://mongo-a:27017,mongo-b:27017,mongo-c:27017/
  ?replicaSet=rsOrders&retryWrites=true
```

Trong cấu hình thực tế URI phải là một dòng, có TLS/auth và secrets an toàn.

### 45.1. Tránh `directConnection=true` cho ứng dụng cần failover

Nếu app chỉ kết nối một host và ép direct connection, nó có thể không khám phá primary mới đúng như mô hình replica set thông thường.

### 45.2. URI chứa nhiều seeds không có nghĩa chắc chắn có primary

Seeds giúp driver tìm topology. Khi quorum mất, driver không thể tự tạo primary hoặc vượt qua giới hạn consensus.

---

## 46. Java Sync Driver với write concern rõ ràng

Ví dụ:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadPreference;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

import java.util.concurrent.TimeUnit;

public final class MongoClientFactory {

    public static MongoClient create(String uri) {
        MongoClientSettings settings =
            MongoClientSettings.builder()
                .applyConnectionString(
                    new ConnectionString(uri)
                )
                .retryWrites(true)
                .readPreference(
                    ReadPreference.primary()
                )
                .writeConcern(
                    WriteConcern.MAJORITY
                        .withWTimeout(10, TimeUnit.SECONDS)
                )
                .applyToClusterSettings(
                    builder -> builder.serverSelectionTimeout(
                        10, TimeUnit.SECONDS
                    )
                )
                .build();

        return MongoClients.create(settings);
    }
}
```

### 46.1. Driver version

Builder methods/timeout semantics phụ thuộc Java Driver version. Đối chiếu Javadocs hiện hành của dependency đang dùng.

### 46.2. `serverSelectionTimeout`

Giới hạn thời gian chờ driver tìm server thỏa yêu cầu. Nó không làm replica set có primary khi mất quorum.

### 46.3. `wtimeout`

Một write concern timeout không chắc nghĩa là write chưa áp vào primary. Không tự retry toàn bộ external business transaction như payment/email.

### 46.4. `retryWrites`

Hỗ trợ các retryable writes khi server/driver/operation đủ điều kiện; không bao trùm mọi bulk write, transaction, external API hay lỗi logic.

---

## 47. Xử lý lỗi an toàn khi không rõ kết quả ghi

Ví dụ:

```java
try {
    orders.insertOne(order);
    return "ACKNOWLEDGED";
} catch (com.mongodb.MongoException error) {
    logger.warn(
        "MongoDB write not confirmed for orderId={}",
        order.get("_id"),
        error
    );
    throw error;
}
```

Đây là **phác thảo**, không đủ cho ứng dụng critical. Cần protocol:

1. Sinh `orderId`/idempotency key ổn định **trước** write.
2. Có unique key trên business operation.
3. Khi nhận timeout chưa rõ, query lại theo ID từ một read path phù hợp sau khi cluster khỏe.
4. Chỉ retry thao tác có semantics idempotent.
5. Không gọi lại payment/email bên ngoài vì một MongoDB write timeout.
6. Với transaction commit uncertain, xử lý error label và retry commit theo driver documentation.

### 47.1. Đừng lấy count ngay trên stale secondary để kết luận thiếu record

Nếu ứng dụng `insertOne` trên primary rồi query secondary chậm, có thể chưa thấy dữ liệu. Kiểm tra read preference/concern và trạng thái replication.

---

## 48. Read preference và stale reads

Nếu ứng dụng dùng:

```java
ReadPreference.secondaryPreferred()
```

trong lúc replication lag tăng, các reads có thể nhận dữ liệu cũ.

### 48.1. `maxStalenessSeconds`

Java Driver hỗ trợ read preference với **maximum staleness** theo những giới hạn server/driver:

```java
import com.mongodb.ReadPreference;

ReadPreference preference =
    ReadPreference.secondary(
        120,
        java.util.concurrent.TimeUnit.SECONDS
    );
```

Ý nghĩa: driver tránh lựa chọn những secondary được ước lượng stale quá ngưỡng theo rules phù hợp. Đây không phải SLA tuyệt đối cho mọi read và có minimum value constraints.

### 48.2. Nếu không còn secondary phù hợp

Một read preference chỉ chọn secondary có thể thất bại thay vì tự đọc primary. `secondaryPreferred` có thể fallback sang primary khi không có secondary phù hợp, tùy topology.

### 48.3. Critical reads

Các luồng tài chính, xác thực token hoặc inventory phải xác định read consistency riêng. Không mặc định secondary reads có read-your-writes.

---

## 49. Transaction và primary election

Trong lúc primary stepdown hoặc mất quorum, application transaction có thể bị abort hoặc trả lỗi tạm thời.

Driver cung cấp error labels như:

- `TransientTransactionError`.
- `UnknownTransactionCommitResult`.

### 49.1. Retry theo ngữ nghĩa

- Với lỗi giao dịch tạm thời, có thể cần retry toàn transaction body.
- Với kết quả commit chưa rõ, có thể retry commit phù hợp mà **không** replay toàn bộ external side effects.
- Dùng `withTransaction` hoặc helper phù hợp driver version và ứng dụng.

### 49.2. Callback không gọi side effect không idempotent

Nếu `withTransaction` callback có thể chạy lại, không trực tiếp gọi payment gateway/email trong callback mà không có outbox/idempotency.

---

# PHẦN VIII — SỰ CỐ CỤ THỂ VÀ CÁCH XỬ LÝ

## 50. Tình huống A: secondary lag tăng từ 5 lên 300 giây

Quan sát:

```text
A PRIMARY    healthy
B SECONDARY  lag 5s -> 30s -> 300s
C SECONDARY  lag < 1s
```

Giả thuyết ban đầu: node-specific resource/network issue ở B.

### 50.1. Chẩn đoán

- B có CPU/disk saturation không?
- B có đang chạy reporting query/index build không?
- `syncSourceHost` của B là ai?
- B có restart gần đây không?
- Oplog window trên sync source còn bao nhiêu?
- Lag có đang giảm khi giảm workload không?

### 50.2. Hành động

1. Không can thiệp C nếu đang healthy.
2. Hạ workload reads trên B nếu cần.
3. Sửa disk/network bottleneck.
4. Quan sát B catch-up.
5. Điều chỉnh oplog size/retention nếu risk quá stale.
6. Nếu B quá stale và không có history, lập kế hoạch initial sync.

### 50.3. Sai lầm

Restart cả A/B/C hoặc force reconfig chỉ vì B chậm trong khi quorum đang khỏe.

---

## 51. Tình huống B: mất hai voters của replica set ba node

```text
A: reachable
B: unreachable
C: unreachable

Votes: 1/3
Election majority: 2
No PRIMARY
```

### 51.1. Ưu tiên

1. Khôi phục network/service của B hoặc C, ưu tiên node có dữ liệu mới và an toàn.
2. Xem logs để xác nhận không có split-brain.
3. Tránh force reconfig trước khi xác định dữ liệu của các members.
4. Khi đủ votes, đợi election hoàn tất.
5. Xác minh application writes và `w:majority`.
6. Phục hồi member còn lại theo thứ tự an toàn.

### 51.2. Không tự “hạ majority”

Có các quy trình DR đặc biệt cho tình trạng không thể khôi phục voting members, nhưng thay cấu hình ép có nguy cơ data loss và phải tuân theo MongoDB documentation, backup/restore assessment và escalation.

---

## 52. Tình huống C: PSA còn primary và arbiter, thiếu secondary

```text
A PRIMARY    data
B SECONDARY  DOWN
C ARBITER    vote only
```

A+C có thể có election majority nhưng thiếu data-bearing acknowledgment cho `w:"majority"`.

### 52.1. Biểu hiện

- Primary vẫn được driver tìm thấy.
- Writes `w:1` có thể trả thành công.
- Writes `w:"majority"` chờ/timeout.
- Write durability suy giảm.
- Monitoring có thể không báo “no primary”.

### 52.2. Xử lý

Khôi phục B càng sớm càng tốt. Không hạ write concern xuống `w:1` chỉ để “xanh dashboard” nếu business cần majority durability; đó là thay đổi rủi ro dữ liệu cần approval.

---

## 53. Tình huống D: secondary offline 12 giờ, window còn 2 giờ

```text
C last applied:  00:00
A oplog oldest:  10:00
A oplog latest:  12:00
```

C cần history 00:00–10:00 mà source không giữ.

### 53.1. Hành động

1. Xác định C thật sự too stale.
2. Kiểm tra source khác còn đủ oplog history không.
3. Không retry incremental replication mãi.
4. Nếu không có history, lập kế hoạch rebuild/initial sync.
5. Bảo vệ majority A/B.
6. Trước khi xóa bất kỳ local data nào của C, có backup và approval.
7. Resize oplog/tối ưu capacity để giảm nguy cơ lặp lại.

### 53.2. Không có phép màu

Tăng oplog từ 2 GiB lên 200 GiB lúc 12:00 không tái tạo các entries đã biến mất trước 10:00.

---

## 54. Tình huống E: lag sau bulk update nhiều triệu documents

```text
Normal oplog window: 20 hours
During migration:    3 hours
B replication lag:   2 hours and growing
```

### 54.1. Rủi ro

Nếu bulk update tiếp tục phát sinh oplog với tốc độ cao, B có thể mất phần history cần để catch up.

### 54.2. Hành động

- Giảm/tạm dừng bulk operations có thể điều khiển.
- Kiểm tra B I/O/CPU/network.
- Theo dõi actual window theo thời gian.
- Tăng oplog capacity nếu khả thi và phù hợp.
- Phân hoạch job migration thành nhỏ hơn và có rate limit.
- Không mở thêm nhiều worker để “bù tốc độ” khi source đang quá tải.

---

## 55. Tình huống F: delayed secondary báo lag đúng một giờ

```text
D SECONDARY
secondaryDelaySecs: 3600
Observed lag:        ~3600 seconds
```

Đây có thể là **behavior mong muốn**.

### 55.1. Monitoring đúng

- Tách deliberate delay khỏi unexpected extra lag.
- Alert nếu lag thực vượt configured delay cộng headroom.
- Đo oplog window > configured delay + outage/catch-up budget.
- Đảm bảo member đủ disk và server có history cần thiết.

### 55.2. Không “sửa” bằng cách bỏ delay không có phê duyệt

Delayed member có thể phục vụ recovery use case. Thay cấu hình này làm mất một lớp bảo vệ logic trong hệ thống.

---

## 56. Tình huống G: writeConcern timeout sau election

Một write đang chờ majority acknowledgment khi primary đổi.

### 56.1. Những kết quả có thể xảy ra

- Write không được áp dụng.
- Write đã áp dụng nhưng response bị mất.
- Write được áp và sau đó replicate.
- Write chưa đạt mức durability mong muốn tại thời điểm timeout.

### 56.2. Ứng dụng cần làm

- Dùng stable operation ID.
- Đọc lại outcome khi topology ổn định.
- Retry theo driver error labels/semantics.
- Không lặp side effects không idempotent.
- Ghi monitoring write concern errors/timeout rate.

### 56.3. Không khẳng định timeout nghĩa chắc chắn dữ liệu bị mất

Chẩn đoán dựa vào outcome và trạng thái committed, không chỉ exception string.

---

## 57. Tình huống H: initial sync làm nguồn quá tải

Node C được xây lại, bắt đầu tải dữ liệu từ A. B vẫn healthy nhưng A có disk/CPU gần giới hạn.

### 57.1. Dấu hiệu

- A read IOPS tăng.
- A write latency/p99 tăng.
- B lag bắt đầu tăng.
- C initial sync kéo dài.
- Oplog window co.
- Application errors tăng.

### 57.2. Xử lý

- Điều tiết workloads không thiết yếu.
- Chọn thời điểm ít tải hơn nếu có thể.
- Kiểm tra nguồn sync khác khỏe theo procedure.
- Tăng resource capacity.
- Đánh giá khả năng clone/resync bằng cơ chế supported.
- Không restart B trong lúc B là majority data copy quan trọng.

---

# PHẦN IX — ALERTING, PREVENTION VÀ BÀI TẬP

## 58. Chỉ số nên theo dõi liên tục

| Chỉ số | Ý nghĩa |
| --- | --- |
| Replica set PRIMARY availability | Có leader hợp lệ hay không |
| Voting members reachable | Có election majority hay không |
| Data-bearing members healthy | Khả năng durability/replication |
| Replication lag per member | Chậm đồng bộ từng secondary |
| Lag growth rate | Nguy cơ bắt kịp không nổi |
| Oplog window per sync source | History headroom |
| Oplog generation rate | Rủi ro window co do write burst |
| Majority commit point lag | Write durability/flow control |
| Write concern timeouts | Majority acknowledgments không đúng hạn |
| Election/stepdown frequency | Topology instability |
| Network RTT/errors | Sync fetch reliability |
| Disk free/IOPS/latency | Apply và storage |
| CPU/cache pressure | Secondary apply bottleneck |
| Flow control engaged | Primary bị throttled theo replication |
| Initial sync progress/retries | Recovery health |
| Change Stream consumer lag | Oplog-dependent consumers |
| Client server selection errors | Tác động application |

### 58.1. Đặt cảnh báo theo headroom

Ví dụ policy:

```text
warning:
  replication lag > 2 min sustained
  or oplog window < 12 hours

critical:
  no primary
  or majority unavailable
  or lag approaches remaining oplog window
```

Các ngưỡng **chỉ là ví dụ**. Hệ có 24/7 payments và DR chính sách chặt cần thresholds khác hệ chỉ dùng reporting.

### 58.2. Lag/window ratio

Một chỉ số cảnh báo sớm:

```text
replication lag / oplog window
```

Ví dụ:

```text
lag = 90 min
window = 120 min
ratio = 75%
```

Secondary đang gần ranh giới rủi ro nếu lag còn tăng. Phải xét tốc độ thay đổi window, outage budget và source chain, không chỉ lấy ratio tĩnh.

---

## 59. Runbook theo ba câu hỏi

Khi nhận alert, tự hỏi:

**Câu 1: Có PRIMARY và election majority không?**

- Không → khôi phục network/service/voting members an toàn trước.
- Có → tiếp câu 2.

**Câu 2: Majority writes và data-bearing members ổn không?**

- Không → xử lý write concern/data copy availability, đặc biệt PSA.
- Có → tiếp câu 3.

**Câu 3: Secondary chậm còn history cần thiết không?**

- Có → xử lý slow fetch/apply và workload.
- Không → xác minh stale, tìm source còn history hoặc initial sync theo procedure.

Sơ đồ:

```text
Replication incident
        |
        v
Primary + election quorum?
        |
       / \
     No   Yes
     |     |
Restore    v
healthy   Majority write concern healthy?
voters     |
          / \
        No   Yes
        |     |
   Repair data-bearing
   availability
              |
              v
       Lagging member needs history?
              |
             / \
          Yes   No
           |     |
      Fix fetch/apply
      bottleneck      Evaluate alternate
                      source / initial sync
```

---

## 60. Checklist xử lý sự cố thực tế

- [ ] Ghi nhận thời điểm, blast radius và business impact.
- [ ] Biết topology, votes/priority và failure domains.
- [ ] Có `rs.status()` từ member reachable.
- [ ] Xác định primary/election quorum hiện tại.
- [ ] Phân biệt data-bearing với arbiter.
- [ ] Kiểm tra `w:"majority"` và write concern timeouts.
- [ ] Phân loại hidden/delayed secondaries.
- [ ] Ghi replication lag **theo từng member**.
- [ ] Xem `syncSourceHost` và network/DNS/TLS.
- [ ] Kiểm tra CPU, disk free, IOPS, RAM/cache.
- [ ] Kiểm tra các bulk jobs/DDL/backup đang chạy.
- [ ] Đo actual oplog window.
- [ ] So secondary latest applied với oldest retained oplog.
- [ ] Không giả định mọi RECOVERING đều too stale.
- [ ] Không force reconfig như bước đầu.
- [ ] Không xóa dbPath khi chưa xác minh node/backup/approval.
- [ ] Giữ majority trước mỗi restart/resync.
- [ ] Chỉ rebuild một secondary theo capacity cho phép.
- [ ] Xác minh source dữ liệu và oplog history phù hợp.
- [ ] Không nghĩ resize oplog hồi sinh history đã cắt.
- [ ] Sau recovery kiểm tra write concern, app reads/writes.
- [ ] Theo dõi majority commit point và oplog headroom.
- [ ] Cập nhật backup/recovery plan và alert thresholds.

---

## 61. Thực hành lab: quan sát lag trên replica set riêng

**Chỉ thực hiện trong môi trường test cô lập**, không trên production.

Giả sử đã có ba `mongod` nodes chạy cùng replica set `rs0` với hostname mà các nodes truy cập được:

```javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "mongo-a:27017", priority: 2 },
    { _id: 1, host: "mongo-b:27017" },
    { _id: 2, host: "mongo-c:27017" }
  ]
});
```

Đây là ví dụ cấu hình topology, không bao gồm TLS/keyfile/auth và network isolation cần cho deployment thực. Không để MongoDB không xác thực lộ ra Internet.

### 61.1. Sinh một lượng writes vừa phải

Trên primary của lab:

```javascript
const lab = db.getSiblingDB("replication_lab");
lab.events.createIndex({ createdAt: 1 });

for (let i = 0; i < 1000; i++) {
  lab.events.insertOne({
    sequence: i,
    createdAt: new Date(),
    payload: "example"
  });
}
```

### 61.2. Xem trạng thái

```javascript
rs.status();
rs.printReplicationInfo();
rs.printSecondaryReplicationInfo();
```

### 61.3. Thử một secondary ngừng trong lab

Trong môi trường test, có thể tắt **một** secondary rồi tiếp tục một số writes ở primary, sau đó bật lại và quan sát catch-up. Không tắt nhiều members cùng lúc khi không chủ đích test quorum.

### 61.4. Bài học

- Lag tăng trong lúc secondary offline.
- Khi khởi động lại, nó có thể catch up nếu history còn.
- Nếu quá lâu và oplog history bị mất, incremental catch-up có thể không thành công.
- Rebuild cần procedure an toàn, không phải chỉ tăng network timeout.

---

## 62. Lab mất quorum: minh họa có kiểm soát

Trong replica set lab ba voting members:

1. Đảm bảo A primary, B/C secondaries.
2. Chụp `rs.status()` baseline.
3. Dừng B, quan sát A/C vẫn có majority.
4. Dừng C **chỉ trong lab**, quan sát primary/writes không khả dụng theo election rules.
5. Khởi động lại một member khỏe.
6. Chờ election và xác nhận `PRIMARY` trở lại.
7. Khởi động member còn lại.
8. So sánh logs/election events.

### 62.1. An toàn thử nghiệm

- Không có dữ liệu sản xuất.
- Có snapshot/fixture để reset.
- Network/service operations do môi trường test điều khiển.
- Không dùng `force:true` để ép primary.
- Không xóa data directory.

---

## 63. Bài tập 1 — Lag hay stale?

```text
Primary oldest oplog:   10:00
Primary latest oplog:   14:00
Secondary latest:       13:45
```

**Hỏi:** Secondary có thể catch up từ lịch sử đang giữ không?

**Đáp án:** Theo timeline đơn giản, vị trí 13:45 vẫn trong window 10:00–14:00; có thể còn khả năng incremental catch-up. Cần kiểm tra history chain, sync source, health và logs, không chỉ timestamps.

---

## 64. Bài tập 2 — Đã quá stale

```text
Primary oldest oplog:   12:00
Secondary latest:       08:00
```

**Đáp án:** Có khoảng thiếu 08:00–12:00 nếu không source khác còn history. Tăng oplog size lúc này không khôi phục các entries cũ; phải đánh giá initial sync/restore được hỗ trợ.

---

## 65. Bài tập 3 — Majority của 5 voters

Một replica set có 5 voters; 2 members down.

**Đáp án:** Còn 3/5, đáp ứng election majority về số phiếu nếu connectivity và candidate eligibility cũng đạt.

---

## 66. Bài tập 4 — Chỉ còn 2/5

5 voters, 3 members down.

**Đáp án:** Còn 2/5, không đủ majority để duy trì/bầu primary theo cách bình thường.

---

## 67. Bài tập 5 — PSA

Primary + arbiter còn hoạt động, secondary data-bearing down.

**Hỏi:** Có thể thấy primary không? Có chắc `w:"majority"` thành công không?

**Đáp án:** Có thể vẫn có election majority và primary. Nhưng arbiter không chứa dữ liệu để xác nhận write; majority write concern có thể block/timeout khi chỉ một data-bearing member.

---

## 68. Bài tập 6 — Hidden member

Một secondary `hidden:true, votes:1, priority:0`.

**Đáp án:** Nó không eligible làm primary và không được client chọn cho reads thông thường, nhưng vẫn có thể đóng góp vote vào election. Không bỏ nó khỏi phép tính quorum.

---

## 69. Bài tập 7 — Delayed member

Lag 3600 giây, cấu hình `secondaryDelaySecs:3600`.

**Đáp án:** Đây có thể là lag có chủ đích. Alert theo excess lag/health và oplog window, không bắt member phải bắt kịp primary ngay.

---

## 70. Bài tập 8 — Oplog size

Oplog 30 GiB, rate trung bình 5 GiB/giờ. Peak 15 GiB/giờ.

**Đáp án:** Window ước tính khoảng 6 giờ bình thường và khoảng 2 giờ lúc peak, chưa xét compression/retention/overhead. Cần sizing theo worst-case/headroom.

---

## 71. Bài tập 9 — Flow control

Primary latency tăng cùng lúc secondary lag.

**Đáp án:** Có thể liên quan flow control/majority commit pressure. Kiểm tra `serverStatus().flowControl`, replication lag, disk/network và workload; không tắt flow control tùy tiện.

---

## 72. Bài tập 10 — Write concern timeout

Ứng dụng nhận timeout sau `insertOne` với w:majority.

**Đáp án:** Không có bằng chứng chắc chắn insert chưa được áp. Dùng stable `_id`/idempotency key, xác minh outcome và retry đúng semantics, không lặp payment/email.

---

## 73. Bài tập 11 — Secondary `RECOVERING`

Một node `RECOVERING`, team muốn xóa dbPath.

**Đáp án:** Sai nếu chưa xác định nguyên nhân. Có thể đang recover/rollback/initial sync hoặc có lỗi disk; đọc logs và oplog boundaries, bảo vệ data/backup trước destructive recovery.

---

## 74. Bài tập 12 — Nhiều secondary lag

Cả B/C lag sau một bulk migration lớn.

**Đáp án:** Xem primary write burst, oplog window, throughput của từng secondary, network chung và resource pressure. Có thể cần rate-limit migration và tăng headroom.

---

## 75. Bài tập 13 — Chỉ một secondary lag

B lag cao, C không lag.

**Đáp án:** Ưu tiên node-specific CPU/disk/network/source issues ở B trước khi thay primary configuration.

---

## 76. Bài tập 14 — Quorum và lỗi mạng

A reach B, nhưng B không reach A; C down.

**Đáp án:** Không chỉ dựa vào ping một chiều; kiểm tra hai chiều TCP/DNS/TLS/heartbeat. Election và replication có thể thất bại vì connectivity không đầy đủ.

---

## 77. Bài tập 15 — Resize oplog

Secondary đã mất 8 giờ history. Operator tăng oplog từ 10 lên 100 GiB.

**Đáp án:** Không làm history cũ quay lại. Cần initial sync hoặc source khác đủ history; tăng oplog chỉ giúp tương lai.

---

## 78. Bài tập 16 — Initial sync trong peak

Primary CPU/disk 95%, một secondary cần initial sync.

**Đáp án:** Cần cân nhắc thời điểm/capacity và nguồn đồng bộ, vì initial sync có thể làm primary/secondary khác chịu tải cao. Không bắt đầu tùy tiện khi còn nhiều vấn đề nghiêm trọng.

---

## 79. Bài tập 17 — Đọc từ secondary

App vừa ghi primary rồi đọc từ secondaryPreferred, không thấy record.

**Đáp án:** Có thể do lag/read preference. Xác định read-your-writes requirement và dùng read concern/read preference/session phù hợp.

---

## 80. Bài tập 18 — Loss of primary

Java Driver không tìm được primary và serverSelectionTimeout xảy ra.

**Đáp án:** Driver không thể tự tạo quorum. Phải khôi phục members/election và xử lý error/retry ở app.

---

## 81. Bài tập 19 — Force reconfig

Vì outage, một người đề xuất `rs.reconfig(config, {force:true})` ngay.

**Đáp án:** Không phải default fix. Có nguy cơ divergence/data loss; chỉ theo DR runbook được hỗ trợ sau khi đánh giá latest data, backups, split-brain và approvals.

---

## 82. Bài tập 20 — Rủi ro thay đổi cùng lúc

Trong maintenance, team dự định nâng tất cả mongod, chạy index build, bulk import và rebuild secondary lag.

**Đáp án:** Rủi ro tăng do thay đổi đồng thời, giảm khả năng quy nguyên nhân. Tách giai đoạn, bảo đảm quorum/oplog headroom và có rollback plan.

---

## 83. Những ngộ nhận phổ biến

| Ngộ nhận | Thực tế |
| --- | --- |
| “Lag 0 là không có vấn đề.” | Còn phải kiểm tra majority commit, write concern và health. |
| “SECONDARY nghĩa đã bắt kịp.” | Secondary có thể lag. |
| “RECOVERING nghĩa dữ liệu đã hỏng.” | Có nhiều nguyên nhân hợp lệ. |
| “Replica set có 3 processes thì majority luôn 2.” | Phải xem voting membership thực tế. |
| “Hidden không vote.” | Hidden có thể vote nếu cấu hình. |
| “Delayed lag là lỗi.” | Có thể là cấu hình chủ đích. |
| “Arbiter là bản sao dữ liệu thứ ba.” | Arbiter không lưu dữ liệu. |
| “Có primary thì w:majority luôn được.” | PSA mất secondary có thể timeout majority writes. |
| “Không có primary nghĩa đã mất dữ liệu.” | Có thể chỉ mất election quorum/network. |
| “Restart toàn cluster sẽ sửa lag.” | Có thể làm mất quorum và kéo dài recovery. |
| “Oplog window là hằng số.” | Thay đổi theo tốc độ writes/retention. |
| “Oplog size gấp đôi thì history gấp đôi ngay.” | Phụ thuộc workload và hiện trạng entries. |
| “Resize oplog khôi phục history cũ.” | Entry đã cắt không được tự tạo lại. |
| “Too stale chỉ cần tăng timeout.” | Thiếu oplog history không giải quyết bằng timeout. |
| “Có sync source online nghĩa đủ history.” | Phải có các entries liên tục cần thiết. |
| “Initial sync không ảnh hưởng production.” | Có thể tiêu thụ lượng lớn I/O/CPU/network. |
| “Xóa dbPath của secondary luôn an toàn.” | Cần xác nhận node, backups, source và quorum. |
| “Force reconfig không có rủi ro.” | Có thể gây data divergence/rollback. |
| “Write concern timeout luôn nghĩa insert thất bại.” | Outcome có thể chưa rõ. |
| “Ứng dụng retry mọi request là an toàn.” | External side effects có thể duplicate. |
| “Flow control là bug nên tắt.” | Có vai trò hạn chế lag, cần chẩn đoán. |
| “Thêm arbiter giải quyết durability.” | Chỉ thêm vote, không thêm bản sao dữ liệu. |
| “Tăng số workers luôn giảm lag.” | Có thể làm primary/oplog pressure tăng. |
| “Lag timestamp luôn chính xác tuyệt đối.” | Clock/workload/metrics semantics có giới hạn. |
| “Oplog thay backup.” | Oplog có retention giới hạn; cần backup/PITR. |
| “Quorum đủ thì có thể bỏ qua disk full.” | Một member disk full vẫn đe dọa consistency/availability. |
| “Read secondary luôn là đọc mới nhất.” | Secondary reads có thể stale. |
| “Recovery xong khi thấy PRIMARY.” | Còn phải kiểm tra writes, lag, app SLO, backups. |

---

## 84. Tài liệu tham khảo chính thức

Các nguồn nên dùng để đối chiếu version-specific behavior:

1. [Replication — MongoDB Manual](https://www.mongodb.com/docs/manual/replication/) — kiến trúc replica set và replication.
2. [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — oplog, retention và giới hạn history.
3. [Replica Set Secondary Members](https://www.mongodb.com/docs/manual/core/replica-set-secondary/) — vai trò secondary và đồng bộ.
4. [Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/) — quorum, votes, priority và election.
5. [Replica Set Arbiter](https://www.mongodb.com/docs/manual/core/replica-set-arbiter/) — voting member không chứa dữ liệu.
6. [Replica Set Member States](https://www.mongodb.com/docs/manual/reference/replica-states/) — PRIMARY, SECONDARY, RECOVERING...
7. [rs.status()](https://www.mongodb.com/docs/manual/reference/method/rs.status/) — trạng thái members, optime và heartbeat.
8. [replSetGetStatus](https://www.mongodb.com/docs/manual/reference/command/replSetGetStatus/) — response fields.
9. [rs.printReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/rs.printReplicationInfo/) — oplog window và size.
10. [rs.printSecondaryReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/rs.printSecondaryReplicationInfo/) — độ trễ secondary.
11. [Replication Lag](https://www.mongodb.com/docs/manual/tutorial/troubleshoot-replica-sets/#replication-lag) — troubleshooting replication.
12. [replSetResizeOplog](https://www.mongodb.com/docs/manual/reference/command/replSetResizeOplog/) — oplog size và minimum retention.
13. [Replica Set Initial Sync](https://www.mongodb.com/docs/manual/core/replica-set-sync/) — initial sync process.
14. [Resync a Member of a Replica Set](https://www.mongodb.com/docs/manual/tutorial/resync-replica-set-member/) — rebuild member theo procedure.
15. [Replica Set Maintenance](https://www.mongodb.com/docs/manual/administration/replica-set-maintenance/) — vận hành/quản trị.
16. [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — majority, wtimeout và durability.
17. [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — secondary reads và staleness.
18. [Replication Flow Control](https://www.mongodb.com/docs/manual/tutorial/troubleshoot-replica-sets/#flow-control) — điều tiết primary khi lag.
19. [serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — replication/flow control/storage metrics.
20. [Java Sync Driver — Connection Options](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/) — topology và timeout.
21. [Java Sync Driver — CRUD Write Concern](https://www.mongodb.com/docs/drivers/java/sync/current/crud/configure/) — write/read concerns theo driver.
22. [Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — retry/error labels.

**Lưu ý:** các fields của `rs.status`, helper output, dynamic oplog sizing, initial sync, flow control, read/write concern và driver APIs có thể khác nhau theo MongoDB Server version, FCV, edition, topology và Atlas/self-managed deployment. Khi xử lý sự cố production, dùng đúng tài liệu và runbook được phê duyệt cho version thực tế.

---

## 85. Kết luận

Ba vấn đề phải được chẩn đoán tách biệt:

1. **Replication lag:** secondary còn đồng bộ được nhưng không bắt kịp write stream. Xác định bottleneck ở fetch, network, CPU, disk hoặc workload; đánh giá xu hướng lag so với oplog window.
2. **Mất quorum:** replica set không có đủ voting members/candidate phù hợp để bầu hoặc duy trì primary; ưu tiên phục hồi network và members an toàn. Arbiter có vote nhưng không thay bản sao dữ liệu hay majority write acknowledgement.
3. **Oplog không đủ:** nguồn không còn lịch sử cần để secondary bắt kịp; tăng oplog lúc đó không phục hồi entries cũ. Phải kiểm tra source khác hoặc thực hiện initial sync/resync theo procedure và giữ quorum.

**Thứ tự xử lý hiệu quả là: giữ bằng chứng và bản sao dữ liệu → xác nhận quorum/primary → kiểm tra majority write concern → đo lag, oplog window và bottleneck → khôi phục từng member → kiểm tra ứng dụng, durability và backup.**

**Một replica set khỏe không chỉ cần đủ process `mongod` đang chạy. Nó cần majority được bầu an toàn, dữ liệu theo kịp trong phạm vi oplog lưu giữ, và khả năng xác nhận writes đúng mức durability mà ứng dụng yêu cầu.**
