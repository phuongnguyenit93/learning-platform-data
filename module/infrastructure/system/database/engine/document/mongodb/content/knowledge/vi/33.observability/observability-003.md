# Theo dõi replication lag, oplog window và trạng thái thành viên MongoDB

## 1. Bối cảnh: cụm vẫn chạy nhưng dữ liệu đã chậm bao lâu?

Giả sử ứng dụng thương mại điện tử ghi đơn hàng vào MongoDB replica set gồm một primary và hai secondary. Bình thường API ghi nhận đơn hàng trên primary, còn một số tác vụ báo cáo đọc từ secondary. Một ngày, hệ thống xuất hiện các dấu hiệu:

- API ghi thành công nhưng màn hình báo cáo trên secondary chưa nhìn thấy đơn hàng vừa tạo.
- Một secondary vẫn đang chạy nhưng liên tục tụt xa primary.
- Secondary khác vừa mất kết nối mạng 90 phút.
- Primary đang ghi nhiều dữ liệu nên lịch sử trong oplog chỉ còn khoảng 2 giờ.
- Khi secondary quay lại, nó không còn bắt kịp được vì những oplog entries cần thiết đã bị loại bỏ.

Vấn đề không thể giải quyết bằng một câu hỏi duy nhất như “MongoDB có hoạt động không?”. Cần **quan sát đồng thời ba nhóm tín hiệu**:

1. **Replication lag:** secondary đang chậm bao nhiêu so với nguồn đồng bộ hoặc primary?
2. **Oplog window:** một thành viên đang giữ được lịch sử thay đổi trong bao lâu?
3. **Trạng thái thành viên:** member đang `PRIMARY`, `SECONDARY`, `RECOVERING`, `DOWN`, `STARTUP2` hay một trạng thái khác, và có còn trao đổi heartbeat không?

### 1.1. Mục tiêu bài học

Sau bài, bạn có thể:

- Giải thích đường đi của write qua oplog và quá trình áp dụng trên secondary.
- Đọc `rs.status()` và `replSetGetStatus` mà không đánh đồng health, optime, heartbeat và member state.
- Sử dụng `rs.printSecondaryReplicationInfo()`, `rs.printReplicationInfo()` và `db.getReplicationInfo()` đúng mục đích.
- Đo và diễn giải **applied lag**, **oplog window** và **replication headroom**; phát hiện khi secondary có nguy cơ trở thành **too stale**.
- Phân biệt **primary**, **secondary**, **arbiter**, **delayed secondary**, **hidden/non-voting secondary** và thành viên đang **initial sync**.
- Phân tích nguyên nhân lag do network, disk, CPU, cache, write bursts, index/maintenance, sync source và election.
- Thiết kế dashboard, cảnh báo có ngưỡng, thu thập bằng chứng, runbook khắc phục và các bài thực hành an toàn.

### 1.2. Hai nguyên tắc đầu tiên

**Replication lag bằng 0 không tự chứng minh cluster khỏe.** Một thành viên có thể không nhận heartbeat, cụm có thể không có write mới hoặc một delayed secondary có cách hiển thị lag gây hiểu lầm.

**Oplog window lớn không tự bảo đảm một secondary bắt kịp được.** Cần so **vị trí cuối đã áp dụng** của member với **entry cũ nhất còn tồn tại tại sync source**, đồng thời xét tốc độ ghi/tốc độ apply và sự thay đổi của window trong thời gian phục hồi.

## 2. Nền tảng replica set và luồng đồng bộ

### 2.1. Một replica set đơn giản

```text
                     Client / Java Driver
                              |
                      Write to PRIMARY
                              |
                              v
                      +---------------+
                      | mongo-a       |
                      | PRIMARY       |
                      | oplog         |
                      +---------------+
                        /           \
                pull oplog          pull oplog
                      /               \
                     v                 v
             +---------------+ +---------------+
             | mongo-b       | | mongo-c       |
             | SECONDARY     | | SECONDARY     |
             | apply oplog   | | apply oplog   |
             +---------------+ +---------------+
```

Trong replica set, dữ liệu ghi trên primary được mô tả bằng các operation entries trong oplog. Secondary lấy các entries từ sync source và áp dụng chúng để duy trì bản sao dữ liệu.

**Replication về cơ bản là bất đồng bộ.** Việc primary đã nhận một write không có nghĩa mọi secondary đều đã áp dụng xong ngay thời điểm đó.

### 2.2. Secondary có thể đồng bộ từ một secondary khác

Một sơ đồ khác:

```text
PRIMARY mongo-a
      |
      v
SECONDARY mongo-b
      |
      v
SECONDARY mongo-c
```

`mongo-c` có thể chọn `mongo-b` làm **sync source** theo cơ chế lựa chọn nguồn đồng bộ. Vì vậy khi phân tích rủi ro quá hạn oplog, không chỉ nhìn window của primary mà còn phải biết **thành viên thực tế đang đồng bộ từ đâu**.

### 2.3. Ba chuyển động không nhất thiết cùng tốc độ

```text
PRIMARY ghi oplog
       |
       v
SECONDARY fetch/ghi oplog
       |
       v
SECONDARY apply operations
       |
       v
SECONDARY durable/journal và visibility theo read concern
```

Khi đọc metrics phải phân biệt **written**, **applied** và **durable**. Các trường hiển thị cụ thể phụ thuộc MongoDB version; ở MongoDB 8.0 có thêm thông tin `optimeWritten` và `optimeWrittenDate` trong `replSetGetStatus`.

## 3. Ba đại lượng cốt lõi và mối quan hệ

### 3.1. Replication lag

Với ví dụ đơn giản, lấy thời gian oplog mới nhất primary đã áp dụng trừ thời gian oplog mới nhất secondary đã áp dụng:

\[
\text{lag}_{s} \approx
\text{primaryLastAppliedTime} -
\text{secondaryLastAppliedTime}
\]

Nếu primary ở mốc `12:00:30`, secondary ở mốc `12:00:10`, chênh lệch hiển thị khoảng **20 giây**.

Đây là **xấp xỉ dựa trên thời điểm tiến độ oplog**, không phải phép đo thời gian mạng thuần túy; nó cũng không chứng minh chính xác thời gian một document đã sẵn sàng cho mọi kiểu read concern.

### 3.2. Oplog window

Oplog là một capped collection có kích thước/retention được cấu hình. Oplog window là khoảng thời gian giữa entry mới nhất và entry cũ nhất **còn trong oplog của một member**:

\[
\text{oplogWindow} =
\text{newestOplogTimestamp} -
\text{oldestOplogTimestamp}
\]

Ví dụ entry cũ nhất lúc 08:00, mới nhất lúc 12:00 thì **window = 4 giờ**, bất kể wall clock hiện tại có thể đã sang 12:10 nếu cụm ít hoạt động.

### 3.3. Replication headroom

Khi xem xét liệu secondary còn thời gian để theo kịp trước khi lịch sử cần thiết bị xoá, một ước lượng quan sát phổ biến là:

\[
\text{headroom} \approx
\text{syncSourceOplogWindow} -
\text{secondaryReplicationLag}
\]

Ví dụ:

```text
Sync source oplog window = 3 giờ
Secondary lag            = 1 giờ 30 phút
------------------------------------------------
Replication headroom     ≈ 1 giờ 30 phút
```

**Đây là phép tính chỉ báo, không phải cam kết chính xác 90 phút còn lại.** Write throughput có thể tăng, oplog window co lại và sync source có thể thay đổi.

### 3.4. Một bảng đọc nhanh

| Replication lag | Oplog window | Headroom | Diễn giải ban đầu |
|---:|---:|---:|---|
| 2 giây | 72 giờ | Rất rộng | Bình thường với nhiều workload |
| 20 phút | 24 giờ | Rộng | Có lag; tìm nguyên nhân và trend |
| 20 giờ | 24 giờ | 4 giờ | Rủi ro; cần ưu tiên xử lý |
| 8 giờ | 6 giờ | Âm | Có thể đã quá cửa sổ, kiểm tra too stale |
| Không xác định | 24 giờ | Không xác định | Đừng biến thiếu metric thành 0 |

Không dùng những con số trong bảng làm SLA mặc định. Ngưỡng phải xuất phát từ yêu cầu đọc, failover, downtime, backup và đặc tính workload.

## 4. Replication lag không đồng nghĩa network latency

Độ chậm replication có thể sinh ra bởi một hoặc nhiều khâu:

```text
PRIMARY writes
   |
   +-- CPU / storage / oplog generation
   |
   v
Network transport
   |
   +-- RTT / packet loss / bandwidth
   |
   v
SECONDARY receives oplog
   |
   +-- fetch / buffer
   |
   v
SECONDARY applies
   |
   +-- disk IOPS, cache, CPU, long operations, concurrency
   |
   v
Read visibility / durability
```

Một secondary có thể có network RTT chỉ 2 ms nhưng replication lag 60 giây vì ổ đĩa không đủ IOPS để áp dụng write. Ngược lại, RTT tăng do cross-region có thể làm lag tăng dù CPU/disk vẫn khỏe.

Vì vậy khi điều tra, **không nhìn `pingMs` rồi kết luận toàn bộ tình trạng replication**.

## 5. Lab: chuẩn bị kết nối đúng

### 5.1. Phạm vi thực hành

Các lệnh trong bài được thiết kế để **đọc/quan sát** một replica set do bạn quản lý hoặc môi trường lab được phép.

Ví dụ connection string:

```bash
mongosh "mongodb://mongo-a.example.internal:27017,mongo-b.example.internal:27017,mongo-c.example.internal:27017/?replicaSet=rsLab&tls=true" --tlsCAFile /secure/certs/ca.pem --username monitor_lab --authenticationDatabase admin --password
```

Host, TLS certificates và user đều là placeholder, không phải môi trường thực. Dùng account monitor có quyền tối thiểu như `clusterMonitor` nếu phù hợp với lệnh và chính sách RBAC.

### 5.2. Các lệnh có phạm vi khác nhau

| Lệnh | Mục đích | Chạy ở đâu? |
|---|---|---|
| `rs.status()` | Trạng thái replica set và members | Nên kiểm tra từ primary khi phân tích toàn cụm |
| `db.adminCommand({replSetGetStatus:1})` | Command mà `rs.status()` bao bọc | Member được kết nối |
| `rs.printSecondaryReplicationInfo()` | Báo cáo lag bằng văn bản | Khuyến nghị từ primary |
| `rs.printReplicationInfo()` | Báo cáo oplog member hiện tại | Kết nối trực tiếp member cần đo |
| `db.getReplicationInfo()` | Đọc thông tin oplog có cấu trúc | Kết nối member cần đo |
| `rs.conf()` | Cấu hình voting, priority, delay, hidden | Quyền phù hợp; đọc, không reconfig |
| `db.serverStatus()` | Metrics member hiện tại | Member hiện tại |
| `db.hello()` | Thông tin vai trò/hello của server | Kết nối member hiện tại |

**Không có một lệnh duy nhất trả lời mọi câu hỏi.** `rs.status()` mô tả health/member progress; `db.getReplicationInfo()` trả cửa sổ oplog của node đang kết nối, không tự tổng hợp toàn replica set.

### 5.3. Lưu ý về MongoDB Atlas

Trên Atlas, các metrics **Replication Lag**, **Replication Oplog Window**, **Replication Headroom** và **Oplog GB/Hour** xuất hiện trong bộ biểu đồ/cảnh báo của cluster được hỗ trợ. Một số mongosh commands không có trên M0/Flex hoặc bị giới hạn; khi đó dùng Atlas metrics/APIs đúng khả năng deployment.

Không mở quyền admin vượt nhu cầu chỉ để chạy một lệnh monitor.

## 6. `rs.status()`: nơi bắt đầu điều tra

Trong `mongosh` nối vào replica set:

```javascript
const status = rs.status();
printjson(status);
```

`rs.status()` là wrapper của command:

```javascript
db.getSiblingDB("admin").runCommand({
  replSetGetStatus: 1
});
```

### 6.1. Những field quan trọng

Tùy phiên bản/config, output chứa:

```javascript
{
  set: "rsLab",
  date: ISODate("2026-11-14T12:00:40Z"),
  myState: 1,
  term: NumberLong("9"),
  members: [
    {
      _id: 0,
      name: "mongo-a.example.internal:27017",
      health: 1,
      state: 1,
      stateStr: "PRIMARY",
      optimeDate: ISODate("2026-11-14T12:00:30Z")
    },
    {
      _id: 1,
      name: "mongo-b.example.internal:27017",
      health: 1,
      state: 2,
      stateStr: "SECONDARY",
      optimeDate: ISODate("2026-11-14T12:00:28Z"),
      pingMs: NumberLong("2"),
      syncSourceHost: "mongo-a.example.internal:27017"
    },
    {
      _id: 2,
      name: "mongo-c.example.internal:27017",
      health: 1,
      state: 2,
      stateStr: "SECONDARY",
      optimeDate: ISODate("2026-11-14T11:58:10Z"),
      pingMs: NumberLong("3"),
      syncSourceHost: "mongo-b.example.internal:27017"
    }
  ],
  ok: 1
}
```

Đây là **output rút gọn minh họa**, không phải JSON đầy đủ mà mọi version đều trả.

### 6.2. Đừng nhầm `myState` và `members[n].state`

`myState` là trạng thái **member đang thực thi command**. `members[n].state` là trạng thái của **từng member từ góc nhìn của node đang hỏi**.

Nếu đang kết nối tới primary, thường:

```text
myState = 1 (PRIMARY)
members[0].state = 1
members[1].state = 2
members[2].state = 2
```

Nếu query một secondary, `myState` có thể là `2`. Khi node bị phân đoạn mạng, view của các member có thể khác nhau.

### 6.3. `health` không phải độ mới dữ liệu

`health: 1` có nghĩa member được xem là khỏe/có kết nối từ góc nhìn của node chạy status. Nó **không** có nghĩa secondary vừa áp dụng write mới nhất.

`health: 0` cho biết member không khỏe/không kết nối được theo view tương ứng; cần đối chiếu heartbeat, network và logs.

### 6.4. `optimeDate` không phải `status.date`

`status.date` là thời gian report được tạo.

`members[n].optimeDate` là thời điểm oplog entry cuối **đã áp dụng** theo metadata. Không lấy:

```text
status.date - secondary.optimeDate
```

rồi gọi đó là replication lag mà không so với primary. Khi cluster **không có write mới**, cả primary và secondary có thể có optimeDate cũ nhưng vẫn hoàn toàn bắt kịp nhau.

## 7. Trạng thái member: mã và ý nghĩa

Các state code chuẩn:

| Mã | `stateStr` | Ý nghĩa vận hành |
|---:|---|---|
| 0 | `STARTUP` | Node đang khởi động, chưa là member hoạt động đầy đủ |
| 1 | `PRIMARY` | Nhận writes bình thường cho replica set |
| 2 | `SECONDARY` | Đồng bộ dữ liệu, có thể nhận reads theo cấu hình |
| 3 | `RECOVERING` | Chưa sẵn sàng phục vụ reads; có thể trong phục hồi |
| 5 | `STARTUP2` | Có thể đang initial sync hoặc chuyển trạng thái lúc khởi động |
| 6 | `UNKNOWN` | Trạng thái chưa xác định từ view member khác |
| 7 | `ARBITER` | Chỉ bỏ phiếu, không lưu bản sao dữ liệu |
| 8 | `DOWN` | Member không liên lạc được từ view hiện tại |
| 9 | `ROLLBACK` | Đang rollback, không phục vụ read bình thường |
| 10 | `REMOVED` | Member đã bị loại khỏi replica set |

### 7.1. Không dùng một quy tắc “state khác SECONDARY là lỗi”

Các trạng thái `STARTUP2` và `RECOVERING` có thể **bình thường trong lúc initial sync/khởi động**, nhưng nếu kéo dài bất thường cần điều tra. `ROLLBACK` có thể là cơ chế phục hồi sau failover chứ không nhất thiết do lỗi disk.

### 7.2. Arbiter không có replication lag như data-bearing secondary

Arbiter không lưu data/oplog như secondary, chỉ tham gia bầu chọn. **Không đưa arbiter vào tính lag trung bình hoặc headroom**, không tính nó là một bản sao dữ liệu để đáp ứng read availability.

### 7.3. Một primary và quyền ghi

Replica set thường có **một primary tại một thời điểm**. Trong phân đoạn mạng, một node cũ có thể tạm thời nghĩ mình vẫn là primary, nhưng majority write concern và election term giúp xác định khả năng commit; đây là một tình huống cần xét khi đọc status từ những view khác nhau.

Không dựa vào trạng thái từ một node không liên lạc để tuyên bố toàn cluster chắc chắn có một primary khỏe.

## 8. Heartbeat, `pingMs` và nguồn đồng bộ

### 8.1. Heartbeat metadata

Các trường thường gặp trong `rs.status().members[]`:

- `lastHeartbeat`: thời điểm gửi heartbeat cuối theo view hiện tại.
- `lastHeartbeatRecv`: thời điểm nhận heartbeat gần nhất từ member khác.
- `lastHeartbeatMessage`: thông điệp lỗi/trạng thái liên quan.
- `pingMs`: thời gian phản hồi heartbeat, không phải replication lag.
- `syncSourceHost`: host đang dùng làm nguồn đồng bộ.
- `uptime`: thời gian liên lạc/hoạt động theo định nghĩa của field.

### 8.2. Ý nghĩa của `pingMs`

Ví dụ:

```text
pingMs = 5 ms
replicationLag = 40 seconds
```

Có thể network khá nhanh nhưng secondary apply chậm do disk/cache. Ngược lại `pingMs` tăng không đủ chứng minh lag, cần kiểm tra replication metrics thực.

### 8.3. `syncSourceHost` giúp xác định điểm nghẽn

Với chained replication:

```text
mongo-a PRIMARY
    |
    v
mongo-b SECONDARY lag 2s
    |
    v
mongo-c SECONDARY lag 90s
```

Nếu `mongo-c.syncSourceHost` là `mongo-b`, cần khảo sát cả oplog window, network và khả năng phục vụ sync của `mongo-b`.

Không mặc định `mongo-c` đang lấy dữ liệu trực tiếp từ primary.

## 9. `rs.printSecondaryReplicationInfo()`: kiểm tra lag bằng mắt

Được khuyến nghị chạy **trên primary** để có view cập nhật nhất:

```javascript
rs.printSecondaryReplicationInfo();
```

Output mẫu:

```text
source: mongo-b.example.internal:27017
    syncedTo: Sat Nov 14 2026 12:00:28 GMT+0000 (UTC)
    2 secs (0 hrs) behind the primary

source: mongo-c.example.internal:27017
    syncedTo: Sat Nov 14 2026 11:58:10 GMT+0000 (UTC)
    140 secs (0 hrs) behind the primary
```

### 9.1. Method này không trả JSON ổn định để parse

`rs.printSecondaryReplicationInfo()` **in báo cáo** để người vận hành đọc; nó không trả về một object JSON làm contract monitoring.

Đối với scripts/exporters, dùng `rs.status()` hoặc command `replSetGetStatus` để lấy dữ liệu có cấu trúc.

### 9.2. Kết quả âm hoặc bằng 0 khi không có write

Theo tài liệu MongoDB:

- Khi primary **idle**, `optimeDate` có thể cũ dù secondary đã bắt kịp.
- Một **delayed member** có thể hiển thị 0 giây behind trong những tình huống thời gian idle vượt `secondaryDelaySecs`.
- Báo cáo đôi khi có thể hiển thị **lag âm** do secondary nhận một write mới trước khi primary status qua heartbeat được cập nhật; điều đó **không chứng minh secondary đi trước primary**.

Vì vậy:

```text
Lag = -1s
```

không nên được đưa vào dashboard như “secondary nhanh hơn primary 1 giây” theo nghĩa nhân quả.

### 9.3. Hiểu lag theo xu hướng

Một sample 30 giây lag chưa đủ kết luận nghiêm trọng nếu vừa có burst write và sẽ nhanh chóng về 0. Nhưng lag tăng liên tục 5 → 10 → 30 → 90 → 180 giây là tín hiệu **secondary không theo kịp tốc độ phát sinh writes**.

Đo **slope**, **duration** và **workload context**, không chỉ max của một mẫu.

## 10. Tự lấy bảng member + applied lag có cấu trúc

Ví dụ `mongosh` chạy trên primary, đọc `rs.status()`:

```javascript
const s = rs.status();
const primary = s.members.find(m => m.stateStr === "PRIMARY");

if (!primary || !(primary.optimeDate instanceof Date)) {
  print("NO_PRIMARY_REFERENCE: cannot calculate lag safely");
} else {
  const referenceMs = primary.optimeDate.getTime();
  const summary = s.members.map(m => {
    const valid = m.optimeDate instanceof Date;
    const rawLagSeconds = valid
      ? (referenceMs - m.optimeDate.getTime()) / 1000
      : null;

    return {
      host: m.name,
      state: m.stateStr,
      health: m.health,
      appliedAt: valid ? m.optimeDate : null,
      lagSeconds: m.stateStr === "SECONDARY"
        ? rawLagSeconds
        : null,
      syncSourceHost: m.syncSourceHost || null,
      pingMs: m.pingMs ?? null
    };
  });

  printjson(summary);
}
```

### 10.1. Tại sao `lagSeconds` của arbiter là null?

Arbiter không lưu dữ liệu/oplog. Nếu nó không có `optimeDate`, phép trừ sẽ sinh kết quả giả.

### 10.2. Tại sao không `Math.max(0, lag)` ngay?

Lag âm có thể do **view không cập nhật đồng thời**, đặc biệt sau idle/heartbeat. Khi giám sát có thể chuẩn hóa giá trị hiển thị thành 0 nhưng nên giữ thêm raw value/quality flag để chẩn đoán, thay vì âm thầm che mọi bất thường.

### 10.3. Code này chỉ là snapshot từ primary

`rs.status()` là snapshot **tại một thời điểm và theo view của một node**. Nếu cần sự chắc chắn khi cluster đang election/network partition, lấy thêm dữ liệu từ từng member/Atlas events, nhưng phải giới hạn tần suất và quyền.

## 11. Primary, secondary và các loại optime

Một số trường quan trọng trong `replSetGetStatus`:

| Field | Diễn giải |
|---|---|
| `members[n].optime` | Timestamp/term của operation cuối đã apply |
| `members[n].optimeDate` | Thời điểm ứng với last applied oplog entry |
| `members[n].optimeDurable` | Operation đã durable vào journal |
| `members[n].optimeDurableDate` | Thời điểm của durable optime |
| `members[n].optimeWritten` | Entry mới nhất đã ghi vào oplog; xuất hiện ở MongoDB 8.0+ |
| `members[n].optimeWrittenDate` | Thời điểm của written optime; MongoDB 8.0+ |
| `optimes.lastCommittedOpTime` | Thông tin majority commit point theo view member |
| `optimes.readConcernMajorityOpTime` | Một mốc phục vụ majority read semantics (khi có) |

### 11.1. Applied khác durable

Một entry đã **apply** trên secondary không tự đồng nghĩa entry đó đã **journal durable**; các thao tác đọc và write concern có những điều kiện khác nhau.

### 11.2. Majority committed khác tất cả secondary đã apply

Write concern `{w: "majority"}` yêu cầu acknowledgement của **đa số voting data-bearing members thích hợp** theo semantics MongoDB, chứ không chờ tất cả secondary.

Ví dụ 3 data-bearing members:

```text
Primary A:    applied at t100
Secondary B:  applied at t100
Secondary C:  applied at t80

Majority point có thể tiến tới t100
trong khi C vẫn chậm.
```

Chi tiết durable/majority journal và failover phụ thuộc cấu hình/version. Không dùng “lag thấp” để thay cho kiểm tra write concern hoặc majority commit point.

### 11.3. Term quan trọng khi election

`optime.ts` gồm thời điểm/tăng dần, trong khi `optime.t` là **election term**. Khi có election hoặc rollback, không nên chỉ lấy `Date` rồi giả định mọi update có quan hệ thứ tự tuyến tính đơn giản.

### 11.4. Đừng dùng đồng hồ host làm primary optime

Nếu primary không có write trong một giờ:

```text
Wall clock = 13:00
Primary last applied = 12:00
Secondary last applied = 12:00
```

**Replication lag ≈ 0**, dù `Date.now()-optimeDate` ≈ 1 giờ. Nếu dashboard hiển thị secondary “behind 1 hour” từ công thức wall clock, đó là metric sai.

## 12. Oplog là gì và vì sao window không cố định?

Oplog nằm trong database `local`, collection `oplog.rs` của mỗi data-bearing member:

```text
local.oplog.rs

oldest                                            newest
  |                                                 |
  v                                                 v
[op1]-[op2]-[op3]-[op4] ... [opN-1]-[opN]
  ^                                                ^
  08:00                                            12:00

Window = 4 giờ
```

Oplog được giới hạn theo dung lượng và quy tắc retention. Khi ghi mới, entry cũ dần bị loại bỏ nếu đáp ứng điều kiện truncation.

### 12.1. Oplog size không tự chuyển trực tiếp thành số giờ

Giả sử oplog có tối đa khoảng 10 GiB:

| Tốc độ ghi vào oplog | Window xấp xỉ trong chế độ ổn định |
|---:|---:|
| 0,5 GiB/giờ | 20 giờ |
| 1 GiB/giờ | 10 giờ |
| 2 GiB/giờ | 5 giờ |
| 5 GiB/giờ | 2 giờ |

Đây là **mô hình số học gần đúng**, không bao hàm min retention, majority commit point, kích thước từng oplog entry và hình dạng workload.

Một cùng-size oplog có thể giữ 4 ngày khi hệ thống ít write nhưng chỉ vài giờ trong một đợt import/bulk update.

### 12.2. Oplog nằm trên mỗi member

Primary và các secondary có oplog riêng. Khi đo window:

```text
mongo-a  window 72h
mongo-b  window 55h
mongo-c  window 60h
```

Đó có thể là ba giá trị khác nhau. Không đo trên primary rồi gán nguyên cho tất cả secondary.

### 12.3. Tác động tới Change Streams

Change Stream resume token cũng phụ thuộc lịch sử oplog có thể truy cập. Oplog window quá ngắn có thể khiến consumer đã dừng lâu **không resume được** bằng token cũ.

Đây là lý do theo dõi window quan trọng cả khi secondary chưa lag: ứng dụng CDC/change-stream processors có thể cần retention dài hơn lịch bảo trì.

## 13. `rs.printReplicationInfo()`: xem nhanh oplog window

Kết nối **trực tiếp data-bearing member cần đo** và chạy:

```javascript
rs.printReplicationInfo();
```

Output minh họa:

```text
configured oplog size:   10240MB
log length start to end: 86400secs (24hrs)
oplog first event time:  Fri Nov 13 2026 12:00:00 GMT+0000
oplog last event time:   Sat Nov 14 2026 12:00:00 GMT+0000
now:                     Sat Nov 14 2026 12:00:20 GMT+0000
```

### 13.1. Cách đọc

- `configured oplog size`: dung lượng cấu hình của oplog.
- `log length start to end`: chênh lệch giữa entry sớm nhất và muộn nhất **còn tồn tại**.
- `oplog first event time` và `last event time`: hai mốc thời gian đó.
- `now`: thời gian hiện tại theo shell, không phải mốc newest oplog nếu cụm idle.

### 13.2. Method in ra text, không dùng để parse

`rs.printReplicationInfo()` in báo cáo dạng text. Trong scripts, dùng **`db.getReplicationInfo()`**.

### 13.3. Đúng member đang được đo

Nếu dùng replica set URI để kết nối nhưng driver/shell tự chọn primary, bạn có thể vô tình đo primary dù muốn đo secondary. Với kiểm tra riêng từng node, cần kết nối trực tiếp tới member phù hợp, bảo đảm quyền/TLS.

## 14. `db.getReplicationInfo()`: dữ liệu có cấu trúc cho scripts

```javascript
const info = db.getReplicationInfo();
printjson(info);
```

Ví dụ:

```javascript
{
  logSizeMB: 10240,
  usedMB: 8710,
  timeDiff: 86400,
  timeDiffHours: 24,
  tFirst: "Fri Nov 13 2026 12:00:00 GMT+0000",
  tLast: "Sat Nov 14 2026 12:00:00 GMT+0000",
  now: "Sat Nov 14 2026 12:00:20 GMT+0000"
}
```

Giá trị là minh họa; một số trường/dạng giá trị phụ thuộc mongosh version.

### 14.1. Các trường nên đưa lên monitoring

| Field | Ý nghĩa |
|---|---|
| `logSizeMB` | Kích thước oplog cấu hình |
| `usedMB` | Dung lượng hiện đang được dùng bởi entries |
| `timeDiff` | Chênh lệch oldest-newest tính giây |
| `timeDiffHours` | Cùng đại lượng tính giờ |
| `tFirst` | Mốc entry đầu còn tồn tại |
| `tLast` | Mốc entry mới nhất |
| `errmsg` | Có thể có khi oplog chưa có entry |

### 14.2. Phân biệt used và configured

`usedMB=8.7GiB` trên `logSizeMB=10GiB` không cho phép kết luận chắc chắn “còn khoảng 1.3GiB sẽ bị xoá” trong mọi cấu hình. Oplog có hành vi truncate/grow phụ thuộc retention/majority commit.

### 14.3. Không tự thay `timeDiff` bằng `now-tFirst`

Với cluster idle:

```text
tFirst = 10:00
tLast  = 11:00
now    = 13:00
```

`timeDiff` là **1 giờ**, không phải 3 giờ. Đây là **thời gian giữa hai operation entries thực tế**.

## 15. Kết nối trực tiếp member để xem oplog

Trong một số công cụ, connection string có thể chọn primary/secondary tự động. Để xác định chính xác member đang quan sát:

```bash
mongosh "mongodb://mongo-b.example.internal:27017/admin?directConnection=true&tls=true" --tlsCAFile /secure/certs/ca.pem --username monitor_lab --password
```

Sau khi kết nối:

```javascript
printjson(db.hello());
printjson(db.getReplicationInfo());
```

`directConnection=true` giúp nhắm tới host được chỉ định trong ví dụ; vẫn cần network/cert hợp lệ, quyền thực thi và không dùng cấu hình directConnection tùy tiện làm URI chính của application cần replica-set failover.

### 15.1. Không phải member nào cũng có oplog

- Primary/secondary data-bearing members có oplog.
- Arbiter không lưu bản sao dữ liệu/oplog.
- Một node không thuộc replica set có thể không có `local.oplog.rs` theo mong đợi.

Nếu `db.getReplicationInfo()` báo thiếu oplog hoặc `errmsg`, không biến giá trị này thành window bằng 0 rồi vội phát cảnh báo “oplog chỉ có 0 giờ”; cần phân loại member.

### 15.2. Raw oplog inspection chỉ khi cần

Một ví dụ **đọc hạn chế** để xem timestamp entry đầu/cuối:

```javascript
const oplog = db.getSiblingDB("local").getCollection("oplog.rs");

const first = oplog.find({}, { ts: 1, _id: 0 })
  .sort({ $natural: 1 }).limit(1).toArray()[0];

const last = oplog.find({}, { ts: 1, _id: 0 })
  .sort({ $natural: -1 }).limit(1).toArray()[0];

printjson({ first, last });
```

Đừng dùng `find().toArray()` trên toàn oplog lớn chỉ để tính window. Với exporter giám sát định kỳ, `db.getReplicationInfo()` thường có giao diện thuận tiện hơn.

## 16. Oplog window, lag và khoảng thời gian phục hồi

### 16.1. Secondary chậm nhưng vẫn trong cửa sổ

```text
Sync source oplog:
  oldest=08:00 newest=12:00

Secondary last applied:
  10:30

Window = 4h
Lag    = 1h30
Headroom ≈ 2h30
```

Secondary vẫn còn cơ hội tải và apply những entries tiếp theo, **nếu những entries cần thiết chưa bị truncate**.

### 16.2. Secondary chậm quá cửa sổ

```text
Sync source oplog:
  oldest=11:00 newest=12:00

Secondary last applied:
  10:30

Entry sau 10:30 đã có thể bị xoá.
```

Nếu member không tìm được lịch sử để tiếp tục, nó có thể thành **too stale** và cần **initial sync/resynchronization** theo procedure được hỗ trợ.

### 16.3. “Headroom = window - lag” là chỉ báo chứ không phải chứng minh

Hãy nghĩ đến ba yếu tố:

1. **Lag** của secondary theo tiến độ apply.
2. **Window** của sync source thực tế.
3. **Tốc độ tiến triển** của cả source và secondary.

Một secondary có headroom 1 giờ nhưng apply chậm hơn tốc độ ghi sẽ tiếp tục xấu đi. Nếu write throughput tăng gấp ba, window có thể thu hẹp nhanh hơn dự kiến.

### 16.4. Cần xem trend

```text
T0: lag 10 min, window 6h, headroom 5h50
T1: lag 20 min, window 4h, headroom 3h40
T2: lag 40 min, window 2h, headroom 1h20
T3: lag 70 min, window 1h30, headroom 20 min
```

Ngay cả khi lag mới tăng từ 40 lên 70 phút, headroom đã giảm mạnh vì **cả hai phía đều xấu đi**. Đây là lý do cần dashboard trên cùng timeline.

## 17. Oplog retention và kích thước

### 17.1. Mặc định theo dung lượng

Oplog là capped collection với dung lượng giới hạn; khi vượt giới hạn và đáp ứng quy tắc, MongoDB loại entries cũ để giữ cửa sổ gần với khả năng lưu trữ đã cấu hình.

Đừng coi “10 GiB oplog” là “đủ 24 giờ” cho mọi workload.

### 17.2. Minimum oplog retention

MongoDB có thể cấu hình thời gian giữ tối thiểu:

```yaml
storage:
  oplogMinRetentionHours: 72
```

MongoDB chỉ loại entry khi **cả hai điều kiện** được đáp ứng:

1. Oplog đã đạt kích thước tối đa cấu hình.
2. Entry cũ hơn thời gian retention tối thiểu dựa trên system clock.

Do vậy oplog **có thể tăng vượt dung lượng cấu hình** để thỏa điều kiện lưu giữ.

### 17.3. Một trường hợp tăng dung lượng ngoài dự kiến

```text
Configured oplog size: 20 GiB
Min retention:          72 giờ
Write rate:             2 GiB/giờ

Khối lượng dữ liệu 72h ≈ 144 GiB
```

Đây là số học minh họa, không phải dự báo byte chính xác. **Không bật retention cao mà không dự trù disk capacity**: có thể làm ổ đĩa đầy và ảnh hưởng availability.

### 17.4. Majority commit point

MongoDB có thể cho oplog tăng quá size cấu hình để tránh loại bỏ entries cần giữ cho **majority commit point**. Vì vậy `logSizeMB` là ngưỡng cấu hình, không phải luôn là trần tuyệt đối của physical usage.

### 17.5. Đừng thay đổi retention chỉ vì một alert

Tăng oplog size/min retention có thể là biện pháp đúng khi **write workload bình thường** nhưng window quá hẹp so với downtime mục tiêu.

Nhưng nếu secondary chậm do disk failure, tăng oplog chỉ **mua thêm thời gian**, không tự chữa vấn đề apply throughput.

## 18. Kiểm tra và điều chỉnh oplog trên self-managed

### 18.1. Đọc cấu hình

Ở member thích hợp:

```javascript
const local = db.getSiblingDB("local");
printjson(local.getCollection("oplog.rs").stats());
```

Để xem cấu hình minimum retention khi được hỗ trợ:

```javascript
const ss = db.getSiblingDB("admin").serverStatus();
printjson(ss.oplogTruncation?.oplogMinRetentionHours ?? null);
```

### 18.2. `replSetResizeOplog`

Trên MongoDB **self-managed** và sau change approval, command hỗ trợ chỉnh size/min retention mà không cần restart:

```javascript
// CHỈ MINH HỌA, KHÔNG TỰ CHẠY TRÊN PRODUCTION.
db.adminCommand({
  replSetResizeOplog: 1,
  size: Double(16384),
  minRetentionHours: 72
});
```

`size` ở đây là **MB** và command chỉ áp dụng cho **member đang kết nối**. Không tự động thay đổi oplog của tất cả replica set members.

### 18.3. Hai cảnh báo quan trọng

- **Không có support trên Atlas clusters cho `replSetResizeOplog`**; Atlas có cơ chế đặt minimum oplog window trong UI/API theo khả năng deployment.
- **Giảm size/retention có thể truncate entries ngay**, làm secondary hoặc change-stream consumers không còn tiếp tục được. Đây là thay đổi rủi ro cao, cần kế hoạch và kiểm tra.

### 18.4. Đặc tính resource của resize

`replSetResizeOplog` có thể lấy exclusive lock trên oplog trong lúc thực hiện. Giảm size không nhất thiết trả disk space ngay cho OS.

Không lập lịch thay đổi oplog trong giờ cao điểm mà chưa xem tài liệu thao tác tương ứng, tài nguyên và khả năng khôi phục.

## 19. Nhận diện member quá cũ: `tooStale`

Trong một số trạng thái `replSetGetStatus` có thể xuất hiện:

```javascript
{
  tooStale: true,
  // ...
}
```

Điều này cho biết member đã tụt quá xa và bị kẹt trong trạng thái `RECOVERING` vì thiếu lịch sử oplog cần thiết theo cơ chế đồng bộ.

### 19.1. Không chữa bằng cách ép member thành primary

Một secondary đã too stale không thể được “chữa” bằng cách buộc election/stepUp. Đưa một bản dữ liệu cũ làm nguồn ghi có thể tạo rủi ro toàn vẹn nghiêm trọng.

### 19.2. Hướng xử lý

1. Xác minh vấn đề trên đúng member và sync source.
2. Kiểm tra log `RECOVERING`/`too stale` và oplog windows.
3. Xác nhận replica set còn primary và healthy members đủ khả năng.
4. Lập kế hoạch **initial sync/resync** theo tài liệu MongoDB cho môi trường cụ thể.
5. Ước lượng dung lượng, disk/network và thời gian đồng bộ.
6. Theo dõi `STARTUP2` → `RECOVERING` → `SECONDARY`.
7. Không drop data directory hoặc `rs.reconfig()` tự ý.

### 19.3. Too stale không phải mọi lỗi RECOVERING

`RECOVERING` còn có thể xuất hiện khi khởi động, rollback hoặc giai đoạn chuyển tiếp. Chỉ kết luận too stale khi có **bằng chứng trạng thái/log/metr​ics** hỗ trợ, không chỉ từ `stateStr`.

## 20. Delayed secondary: lag có chủ đích

Replica set có thể cấu hình **delayed secondary**, thường phục vụ nhu cầu giữ bản sao dữ liệu chậm một khoảng đã đặt để hỗ trợ khôi phục một số thao tác sai.

Ví dụ member cấu hình:

```javascript
{
  _id: 2,
  host: "mongo-c.example.internal:27017",
  priority: 0,
  hidden: true,
  secondaryDelaySecs: 3600
}
```

Đây là fragment minh họa của `rs.conf().members[]`, **không phải lời khuyên thay đổi config trên production**.

### 20.1. Có chủ đích không có nghĩa bỏ giám sát

Với delay 1 giờ, lag quan sát khoảng 1 giờ có thể đúng thiết kế. Nhưng:

- Member vẫn cần network, disk, replication khỏe.
- Oplog window phải đủ cho delay cộng downtime/catch-up.
- Có thể chậm **nhiều hơn** delay cấu hình do lỗi.
- Một thời điểm primary idle có thể làm `rs.printSecondaryReplicationInfo()` hiển thị 0 giây dù delay vẫn được cấu hình.

### 20.2. Ngưỡng phải theo member role

Không áp chung alert `lag > 30s` cho cả delayed secondary 3600s. Nên đặt:

```text
effectiveExcessLag ≈ measuredLag - configuredDelay
```

chỉ như tín hiệu bổ sung, cùng heartbeat/state/headroom và điều kiện đo. Trên primary ít write, raw lag không phản ánh delay ổn định; cần đánh giá thực tế.

### 20.3. Delayed secondary không thay backup

Với sai sót được phát hiện sau lâu hơn delay, hoặc attacker có quyền xóa cả replica set, bản delayed không bảo đảm khả năng phục hồi. Backup, PITR và access controls vẫn cần thiết.

## 21. Hidden/non-voting members và khả năng bầu chọn

### 21.1. Hidden secondary

Hidden member có thể đồng bộ dữ liệu nhưng không được đưa vào danh sách member mà driver thông thường chọn để phục vụ reads. Nó vẫn có thể hữu ích cho backup/reporting hoặc yêu cầu riêng.

Nếu hidden member đang lag và chưa nằm trong đường phục vụ API, mức ảnh hưởng user có thể khác với secondary đang nhận traffic đọc, nhưng **không có nghĩa bỏ qua lag**.

### 21.2. Priority và votes

Trong `rs.conf()`:

- `priority` ảnh hưởng khả năng ưu tiên làm primary.
- `votes` ảnh hưởng quyền bầu chọn.
- `hidden` ảnh hưởng tính hiển thị của member đối với client.
- `secondaryDelaySecs` cấu hình delay.
- `arbiterOnly` cho biết arbiter.

Các field này cho biết **vai trò dự kiến**. `rs.status().stateStr` cho biết **trạng thái vận hành hiện tại**.

### 21.3. Không tính tất cả secondary là failover candidates

Một member `priority: 0` không trở thành primary qua election thông thường. Delayed/hidden members thường được cấu hình không bầu làm primary.

Vì thế một secondary “healthy” không tự nghĩa replica set có thêm một ứng cử viên primary phù hợp.

## 22. Election: đọc trạng thái trong thời điểm thay primary

### 22.1. Các tín hiệu

Khi primary down hoặc step down, có thể thấy:

- Primary cũ từ `PRIMARY` chuyển sang `SECONDARY`, `RECOVERING` hoặc không thể liên lạc.
- Một secondary phù hợp được bầu làm `PRIMARY`.
- Giá trị `term` thay đổi.
- Driver phát hiện topology thay đổi.
- Một số thao tác write bị retry hoặc trả lỗi tạm thời.

### 22.2. Đừng dùng một status sample để kết luận dài hạn

Trong 1–2 nhịp heartbeat, report có thể hiển thị một view chưa cập nhật. Nên:

1. Thu status từ primary mới khi có.
2. Xem election/log events.
3. Kiểm tra majority availability.
4. Quan sát `term` và `optimes`.
5. Xem driver retries/application error rate.

### 22.3. Việc nào không nên tự động làm?

Không xây monitoring script cứ thấy primary vắng 5 giây là gọi:

```javascript
rs.stepDown();
rs.reconfig();
rs.remove();
```

Đây là các **lệnh thay đổi topology**, không phải lệnh quan sát. Việc gọi sai có thể kéo dài outage hoặc gây mất quorum.

## 23. Initial sync: giai đoạn đặc biệt của member

Một member mới hoặc cần tái đồng bộ có thể trải qua:

```text
STARTUP
   |
   v
STARTUP2 (initial sync)
   |
   v
RECOVERING
   |
   v
SECONDARY
```

### 23.1. Theo dõi gì?

- Trạng thái thành viên và thời gian tồn tại trong `STARTUP2`.
- Dung lượng dữ liệu/index đang được copy/build.
- Oplog entries phải apply trong khi clone.
- Disk capacity, write rate, network bandwidth.
- Các trường `initialSyncStatus` khi có.
- Log lỗi/tiến độ và khả năng chọn sync source.

### 23.2. `initialSyncStatus` không phải field thường xuyên

Trong `replSetGetStatus`, `initialSyncStatus` chỉ xuất hiện khi phù hợp với trạng thái/method initial sync. Một member đã hoạt động bình thường có thể không có field này.

Monitoring phải biểu diễn `field missing` là “không áp dụng/không có dữ liệu”, không coi mọi thiếu field là lỗi.

### 23.3. Cẩn thận sức ép do initial sync

Initial sync có thể tải nhiều dữ liệu từ sync source và tạo I/O đáng kể. Khi thêm nhiều members cùng lúc vào một cluster đang nặng, risk tăng:

- Network saturation.
- Disk/cache pressure ở source.
- Oplog window không đủ để giữ thay đổi trong thời gian clone.

Nên lập kế hoạch capacity và lịch thực hiện, không đồng loạt resync nhiều secondary thiếu cơ sở.

## 24. Rollback và replication lag sau failover

### 24.1. Rollback là gì?

Khi primary cũ đã chấp nhận một số write nhưng chúng không trở thành lịch sử chung của primary mới, member cũ có thể cần rollback những write lệch khi nhập lại replica set.

### 24.2. Trạng thái `ROLLBACK`

`ROLLBACK` là trạng thái có ý nghĩa điều tra. Nó khác với “secondary chỉ chậm 10 giây”.

Kiểm tra:

- Election timeline.
- Write concern mà application dùng.
- Rollback logs/metadata.
- Majority commit point.
- Ảnh hưởng lên nghiệp vụ nếu write đã được acknowledged mà chưa đạt majority.

### 24.3. Không kết luận dữ liệu đã mất chỉ từ lag metric

High lag không tự chứng minh mất write. Ngược lại lag thấp cũng không thay cho **durability/write concern guarantees**.

Đọc cùng:

```text
writeConcern + majorityCommit + memberState + optime + election logs
```

để đánh giá rủi ro đúng.

## 25. Chẩn đoán lag: phân nhóm nguyên nhân

| Nhóm | Biểu hiện | Metric/cách điều tra |
|---|---|---|
| Network | RTT/packet loss tăng, heartbeat lỗi | `pingMs`, network monitoring, logs |
| Disk/I/O | Secondary apply chậm, latency ghi cao | Disk latency/IOPS/queue, storage metrics |
| CPU/cache | Cache eviction hoặc CPU gần bão hòa | `serverStatus()`, WiredTiger cache, CPU |
| Write burst | Primary oplog generation tăng mạnh | Oplog GB/hour, opcounters, load timeline |
| Long-running ops | Operations cạnh tranh tài nguyên | Current ops, profiler, slow logs |
| Sync source | Down/slow source hoặc chaining không tối ưu | `syncSourceHost` và health của source |
| Oplog window | Window co nhanh, headroom giảm | `getReplicationInfo()`, Atlas metrics |
| Initial sync | Copy/build indexes/apply ongoing | `STARTUP2`, `initialSyncStatus`, logs |
| Election/rollback | Term/state đổi, writes bị retry | `rs.status()`, log events |
| Capacity/config | Disk đầy, underprovisioning | Atlas/OS storage, CPU, cache, network |

### 25.1. Tìm “điểm bắt đầu” trên timeline

Giả sử:

```text
09:00  deploy batch import
09:03  oplog GB/hour tăng
09:05  secondary disk IOPS chạm trần
09:07  lag bắt đầu tăng
09:15  headroom giảm còn 20 phút
```

Nếu chỉ nhìn lag tại 09:15, bạn thấy triệu chứng. Timeline cho thấy **write burst + secondary disk bottleneck** có thể là nguyên nhân.

### 25.2. Không nhầm tương quan và nguyên nhân

Nếu CPU primary tăng cùng lag secondary, chưa đủ kết luận “primary CPU cao làm secondary lag”. Cần kiểm tra source throughput, network, apply metrics và thay đổi workload.

## 26. Chẩn đoán network lag và heartbeat

### 26.1. Thu thập bằng chứng

Trên các host được phép:

- RTT, packet loss và throughput giữa members.
- DNS resolution, firewall/security group changes.
- TLS certificate expiry và authentication failures.
- `lastHeartbeat`, `lastHeartbeatMessage`, `pingMs`.
- Connection resets/retries trong logs.

### 26.2. Địa lý và multi-region

Một replica set trải rộng nhiều region có RTT khác nhau. Nếu secondary ở xa primary, lag có thể tăng trong đợt write burst nhưng không nhất thiết vì lỗi hạ tầng.

Tuy vậy, đường truyền thường xuyên mất gói hoặc bandwidth thấp có thể khiến oplog fetch không theo kịp.

### 26.3. Không dùng `ping` làm phép đo duy nhất

`ping` ICMP và MongoDB heartbeat đi theo đường/hành vi khác nhau. Một kiểm tra network phải bao gồm endpoint thực tế, TLS và app-level metrics khi có.

## 27. Chẩn đoán disk, WiredTiger cache và áp dụng oplog

### 27.1. Tài nguyên secondary

Nếu secondary bị bão hòa disk I/O:

```text
Primary: 500 writes/s
Secondary disk: chỉ xử lý hiệu quả 350 ops/s

Backlog tăng -> lag tăng
```

Giải pháp có thể là nâng IOPS/storage tier, giảm cạnh tranh từ report/backup hoặc tối ưu workload.

### 27.2. WiredTiger cache

Trên member, có thể xem:

```javascript
const ss = db.serverStatus();
printjson(ss.wiredTiger?.cache?.[
  "pages evicted by application threads"
] ?? null);
```

Trong JavaScript `mongosh`, truy cập property có tên chứa khoảng trắng bằng cú pháp:

```javascript
const pagesEvictedByApp = db.serverStatus()
  .wiredTiger?.cache?.["pages evicted by application threads"];

printjson(pagesEvictedByApp);
```

Nếu metric này **tăng** đều, có thể có cache pressure khiến thread ứng dụng phải giúp eviction. Một giá trị khác 0 đơn lẻ có thể chỉ là tổng tích lũy; cần đo **tốc độ tăng theo thời gian**.

### 27.3. Disk metrics

Nên theo dõi:

- Disk latency (read/write).
- Disk IOPS so với quota.
- Disk queue depth.
- Disk used/free và tốc độ tăng.
- WiredTiger cache usage/eviction.
- Secondary read workload cạnh tranh tài nguyên.

### 27.4. Không tùy tiện chỉnh internals

Các server parameters về concurrency, flow control hay oplog size có trade-off phức tạp. Không giảm/thay giá trị trên production chỉ từ một blog/forum mà chưa benchmark và xem version.

## 28. Flow control và majority lag

MongoDB có cơ chế **flow control** để điều chỉnh nhịp ghi nhằm hạn chế việc majority-committed lag quá xa.

Trên primary:

```javascript
const flow = db.serverStatus().flowControl;
printjson(flow);
```

Một số version có trường:

```javascript
db.serverStatus().flowControl?.isLagged
```

### 28.1. Khi nào xem flow control?

Nếu thấy:

```text
replication lag tăng
write latency tăng
flowControl engaged
```

thì flow control có thể là **dấu hiệu hệ thống đang hạn chế write rate để bảo vệ replication**, không phải nhất thiết nguyên nhân gốc của lag.

### 28.2. Không tự tắt flow control

Tắt hoặc giảm flow control có thể làm primary ghi nhanh hơn trong ngắn hạn nhưng khiến secondaries tụt xa thêm và mất headroom.

Quy trình ưu tiên:

1. Xác định member đang lag.
2. Đo apply throughput, disk và cache.
3. Giảm write burst hoặc tăng capacity nếu phù hợp.
4. Kiểm tra lại majority lag và write latency.
5. Chỉ đánh giá thay đổi flow control trong quy trình chuyên môn.

## 29. Theo dõi oplog GB/hour và áp lực ghi

### 29.1. Tại sao oplog GB/hour quan trọng?

Window bị ảnh hưởng trực tiếp bởi lượng thay đổi được ghi theo thời gian. Tốc độ oplog tăng:

```text
oplogSize ≈ 20 GiB
oplogRate ≈ 1 GiB/hour -> estimated 20h
oplogRate ≈ 5 GiB/hour -> estimated 4h
```

Đó chỉ là ước lượng ổn định; retention/majority commit/transaction overhead có thể làm khác.

### 29.2. Bulk write và delete

Một tác vụ cleanup:

```javascript
db.events.deleteMany({ createdAt: { $lt: cutoffDate } });
```

có thể tạo một lượng lớn operations và làm tăng tốc độ phát sinh oplog. Không chạy đoạn này trên production để test lag.

### 29.3. Kiểm soát batch

Đối với tác vụ hợp lệ, có thể:

- Chia batch theo thời gian/ID.
- Dùng index phù hợp cho filter.
- Đo oplog rate/lag/headroom trong khi chạy.
- Tạm dừng hoặc giảm concurrency khi vượt guardrail.
- Chọn thời điểm workload thấp hơn.

Đừng tự tăng bulk concurrency cho tới khi saturate I/O rồi mới nhìn alert too stale.

## 30. Quan sát trên MongoDB Atlas

Theo tài liệu Atlas hiện hành, các metric/cảnh báo quan trọng:

| Metric | Ý nghĩa |
|---|---|
| **Replication Lag** | Thời gian xấp xỉ secondary chậm primary |
| **Replication Oplog Window** | Khoảng thời gian lịch sử oplog đang giữ |
| **Replication Headroom** | Chênh lệch window của sync source và replication lag |
| **Oplog GB/Hour** | Tốc độ tạo dữ liệu oplog |
| **Disk IOPS/Latency** | Khả năng phục vụ apply |
| **CPU/WiredTiger Cache** | Áp lực compute/cache |
| **Network** | Bandwidth/throughput kết nối |
| **Election/Availability** | Sự kiện thay primary hoặc member bất thường |

### 30.1. Xem từng node

Không chỉ xem một đồ thị tổng hợp của cả cluster. Một secondary lag 10 phút có thể bị che bởi hai members lag 0 giây nếu dashboard lấy trung bình.

Nên phân nhóm theo:

```text
project / cluster / replicaSet / host / state / region / role
```

### 30.2. Độ phân giải metrics

Atlas thu thập nhiều metrics theo granularity riêng; theo tài liệu monitoring, một số Replication Lag và Headroom metrics được thu ở khoảng **85 giây** trong cấu hình thông thường.

Điều đó có nghĩa:

- Một spike ngắn vài giây có thể không hiện rõ.
- Alert từ Atlas có thể có độ trễ so với realtime console sample.
- Cần dùng thời gian thu thập và window aggregation rõ ràng.

### 30.3. M0/Flex và giới hạn lệnh

Các tier không hỗ trợ đầy đủ command/metrics giống dedicated cluster. Không dùng khả năng đọc `local.oplog.rs` trên self-managed làm giả định cho một shared/free deployment.

## 31. Thiết kế dashboard

### 31.1. Tổng quan replica set

```text
┌───────────────────────────────────────────────┐
│ Replica Set: rsLab                            │
├─────────────┬───────────┬──────────┬──────────┤
│ Member      │ State     │ Lag      │ SyncSrc  │
├─────────────┼───────────┼──────────┼──────────┤
│ mongo-a     │ PRIMARY   │ —        │ —        │
│ mongo-b     │ SECONDARY │ 2 s      │ mongo-a  │
│ mongo-c     │ SECONDARY │ 140 s    │ mongo-b  │
└─────────────┴───────────┴──────────┴──────────┘

PRIMARY oplog window: 12 h
Worst lag:             140 s
Min headroom:          11 h 57 m 40 s (ước lượng)
Write oplog rate:      0.8 GiB/h
Elections (24h):       0
```

Các số trong bảng là giả lập. **Headroom thực tế cần tính theo sync source của từng secondary**, không chỉ primary, đặc biệt với chained replication.

### 31.2. Dashboard chi tiết cho từng member

- Role, `health`, state duration.
- `optimeDate`/`optimeDurableDate` và phiên bản hỗ trợ `optimeWrittenDate`.
- Lag seconds theo time series.
- Oplog window của member và sync source.
- Headroom seconds.
- Heartbeat/ping/network errors.
- Disk latency/IOPS/queue, cache eviction, CPU.
- Sync source host và thay đổi source.
- Initial sync progress khi đang STARTUP2.

### 31.3. Quy tắc tránh biểu đồ đánh lừa

Không:

```text
Lag = null -> 0
Oplog window = null -> 0
Member DOWN -> 0 second lag
```

Nên:

```text
Lag = unknown / data missing
Member DOWN = availability alert
Oplog window = not applicable or unavailable
```

**Thiếu dữ liệu quan sát là một trạng thái cần theo dõi**, không phải bằng chứng mọi thứ tốt.

## 32. Thiết kế cảnh báo

### 32.1. Các nhóm alert

| Alert | Trigger gợi ý | Ý nghĩa |
|---|---|---|
| **No Primary** | Không có primary vượt khoảng grace | Khả năng ghi bị ảnh hưởng |
| **Member Unreachable** | `DOWN`/heartbeat lỗi kéo dài | Availability/topology |
| **Member in RECOVERING** | Kéo dài ngoài maintenance/initial sync | Cần kiểm tra nguyên nhân |
| **Lag High** | Lag > SLO trong nhiều samples | Secondary không theo kịp |
| **Lag Growing** | Slope lag dương liên tục | Nguy cơ lan rộng |
| **Oplog Window Low** | Window < downtime mục tiêu + margin | Không đủ lịch sử |
| **Headroom Low** | Headroom < time-to-recover + margin | Nguy cơ quá hạn oplog |
| **Oplog Rate Spike** | GB/hour tăng so với baseline | Window có thể co nhanh |
| **Disk Saturated** | Latency/IOPS bất thường | Có thể làm apply chậm |
| **Election Storm** | Số elections tăng | Topology/network instability |
| **Metrics Missing** | Không có status/oplog samples | Giám sát bị gián đoạn |

### 32.2. Không áp dụng một ngưỡng lag chung

Ví dụ tùy use case:

- Secondary phục vụ đọc thời gian gần thực: lag SLO có thể vài giây.
- Secondary phục vụ báo cáo cuối ngày: lag chấp nhận được có thể lâu hơn.
- Delayed secondary 1 giờ: lag gần 1 giờ là có chủ đích.
- DR secondary cross-region: ngưỡng còn phụ thuộc RPO, mạng và write throughput.

Ngưỡng phải được **định nghĩa cùng product/SRE**, không lấy một giá trị từ blog làm tiêu chuẩn bắt buộc.

### 32.3. Chống alert flapping

Với spike ngắn:

```text
lag=1s -> 6s -> 1s
```

nếu báo động mỗi lần vượt 5 giây có thể gây nhiễu. Sử dụng sustained duration, p95 hoặc burn-rate phù hợp, nhưng **không trì hoãn cảnh báo headroom sắp bằng 0** chỉ để tránh nhiễu.

### 32.4. Phân tầng mức độ

Một quy tắc ví dụ:

```text
WARNING:
  lag growing for 5 minutes
  hoặc oplog window dưới downtime target

HIGH:
  headroom < estimated recovery time + buffer
  hoặc important read-secondary lag vượt SLO

CRITICAL:
  tooStale
  no primary
  loss of required quorum
  headroom gần 0 với lag còn tăng
```

Không áp ngưỡng này nguyên xi vào mọi cluster; điều kiện dùng thực tế phải được đo và chấp thuận.

## 33. Runbook 1 — Secondary lag tăng nhưng vẫn SECONDARY

### Bước 1: xác minh tình hình

Trên primary:

```javascript
rs.status();
rs.printSecondaryReplicationInfo();
```

Ghi lại:

- Tên member bị lag.
- State và health.
- Lag ở nhiều thời điểm.
- Sync source.
- Oplog window và headroom.

### Bước 2: đánh giá mức khẩn

Nếu headroom vẫn rất rộng, có thể điều tra thận trọng. Nếu headroom sắp bằng 0, cần ưu tiên để tránh member trở thành too stale.

### Bước 3: xem tài nguyên

- Disk latency/IOPS trên secondary.
- CPU và WiredTiger cache.
- Network/ping/packet loss.
- Backup/analytics đang đọc secondary không.
- Recent deploy, bulk write, index build, migration.

### Bước 4: giảm nguyên nhân

Tùy bằng chứng:

- Giảm tốc/điều chỉnh batch import.
- Chuyển bớt reporting load khỏi secondary bị quá tải.
- Nâng storage IOPS/tier.
- Sửa network route hoặc sự cố packet loss.
- Tối ưu index/filter làm các tác vụ cạnh tranh tài nguyên.

### Bước 5: xác nhận phục hồi

Lag phải **giảm bền vững**, headroom tăng, member healthy, không có lỗi mới và primary/write latency trong giới hạn.

Không kết luận “đã xử lý” chỉ vì lag tạm về 0 trong một khoảng cluster ít write.

## 34. Runbook 2 — Oplog window thu hẹp đột ngột

### Dấu hiệu

```text
12:00 window 48h
12:10 window 24h
12:20 window 12h
12:30 window 6h
```

### Điều tra

1. Kiểm tra `db.getReplicationInfo()` trên member ảnh hưởng.
2. Đo **Oplog GB/Hour** và write rate.
3. Tìm batch import/update/delete gần đây.
4. Kiểm tra changed workload và index/transaction behavior.
5. Xác minh configured size/min retention.
6. Đối chiếu disk free và majority commit point.
7. Đo lag/headroom của secondaries.

### Hành động có thể cân nhắc

- Giảm write burst tạm thời theo business constraints.
- Tối ưu batch sizes.
- Tăng capacity của oplog hoặc minimum window theo kế hoạch (self-managed/Atlas mechanism khác nhau).
- Bảo vệ secondary đang lag trước khi thiếu history.
- Điều chỉnh backup/maintenance windows.

### Không nên làm

Không giảm oplog size để “giải phóng disk” khi secondary đang gần vượt cửa sổ. Việc truncate thêm có thể đẩy nó thành too stale.

## 35. Runbook 3 — Member DOWN hoặc UNKNOWN

### Bước 1: phân biệt view lỗi và member thật sự down

`rs.status()` từ một node có thể đánh dấu member là `DOWN` do network partition. Hãy đối chiếu:

- Monitoring host/process.
- Network connectivity theo đường thực tế.
- Node logs và TLS/auth.
- View của các members khác.
- Election/majority status.

### Bước 2: bảo vệ quorum

Tránh restart/reconfigure thêm nodes khi replica set đang thiếu majority. Một hành động sai có thể làm mất khả năng bầu primary và ngắt writes.

### Bước 3: ước lượng downtime an toàn

```text
current window ở sync source
  - thời gian member offline
  - độ trễ đã có trước khi offline
  ≈ khoảng lịch sử còn lại (xấp xỉ)
```

Cần nhớ thời gian downtime thực không đủ chính xác nếu window thay đổi theo write workload.

### Bước 4: quay lại

Sau khi member kết nối, xem nó trở lại `SECONDARY` và lag giảm hay chuyển `RECOVERING`/`tooStale`. Không auto xóa data directory rồi cho initial sync mới khi chưa xác minh.

## 36. Runbook 4 — Member too stale

Khi xác nhận `tooStale`:

1. Xác định data-bearing members còn khỏe và phần lớn replica set có hoạt động không.
2. Kiểm tra oplog window tại sync sources khả dụng.
3. Thu logs, thời điểm last applied/last fetched.
4. Lập kế hoạch resync theo hướng dẫn phiên bản.
5. Kiểm tra dung lượng source/target, disk và mạng.
6. Không thực hiện nhiều resync đồng thời nếu nguồn không chịu được.
7. Theo dõi initial sync progress và `STARTUP2`.
8. Xác nhận `SECONDARY`, applied lag/headroom sau resync.
9. Tìm nguyên nhân root cause: network outage, write burst, window quá ngắn.

**Không coi resync là khắc phục tận gốc** nếu workload vẫn tạo oplog nhanh hơn khả năng apply của secondary.

## 37. Runbook 5 — Election liên tục

Nếu primary thay đổi liên tục:

- Ghi danh sách election timestamps, `term` và candidate.
- Xem network partition, heartbeat errors, CPU/disk stalls.
- Xác nhận quorum/voting configuration.
- Kiểm tra members có priority/delay/hidden khác dự kiến không.
- Đối chiếu driver connection errors và application write retries.
- Theo dõi rollback risk, write concern và majority commit.
- Không dùng `rs.stepDown()` hoặc `rs.reconfig()` như probe chẩn đoán.

Mục tiêu là ổn định nguyên nhân **network/resource/topology**, không ép một primary cố định bằng những thao tác tùy tiện.

## 38. Tích hợp monitoring bằng Java Sync Driver

Một application Java có thể đọc `replSetGetStatus` nếu identity đủ quyền. **Đây là tác vụ monitoring nội bộ**, không phải endpoint công khai trả chi tiết hostnames/cluster topology.

### 38.1. Ví dụ Java

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import java.util.Date;
import java.util.List;

public final class ReplicaHealthSample {
    public static void main(String[] args) {
        // URI demo: triển khai thật cần credentials/TLS/secret management.
        String uri = System.getenv("MONGODB_MONITOR_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                "MONGODB_MONITOR_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase admin = client.getDatabase("admin");
            Document status = admin.runCommand(
                new Document("replSetGetStatus", 1));

            @SuppressWarnings("unchecked")
            List<Document> members =
                (List<Document>) status.get("members");

            Document primary = null;
            for (Document member : members) {
                if ("PRIMARY".equals(member.getString("stateStr"))) {
                    primary = member;
                    break;
                }
            }

            Date primaryApplied = primary == null
                ? null : primary.getDate("optimeDate");

            for (Document member : members) {
                String name = member.getString("name");
                String state = member.getString("stateStr");
                Date applied = member.getDate("optimeDate");

                Double lagSeconds = null;
                if ("SECONDARY".equals(state)
                        && primaryApplied != null
                        && applied != null) {
                    lagSeconds =
                        (primaryApplied.getTime() - applied.getTime())
                        / 1000.0;
                }

                System.out.printf(
                    "member=%s state=%s lagSeconds=%s%n",
                    name, state,
                    lagSeconds == null ? "unknown" : lagSeconds);
            }
        }
    }
}
```

### 38.2. Cảnh báo về Java version và permissions

Ví dụ dùng `String.isBlank()` (Java 11+). Cần MongoDB Java Sync Driver dependency đúng version và một identity được phép gọi `replSetGetStatus`.

Trên một số triển khai/driver configuration, cách route lệnh vào node cụ thể cần chủ đích; không dùng output một member làm nguồn tuyệt đối khi cluster đang failover.

### 38.3. Không nối trực tiếp monitoring vào HTTP public

Không tạo:

```text
GET /admin/replica-status
-> trả raw rs.status() cho mọi user
```

Raw output có hostnames, network addresses và thông tin topology. Cần AuthN/AuthZ, loại bỏ dữ liệu không cần thiết, rate limit và security policy.

### 38.4. Polling có kiểm soát

Không query `rs.status()` hàng chục lần mỗi giây từ hàng trăm application instances. Dùng central exporter/monitoring agent và scrape interval hợp lý.

## 39. Một script mongosh tổng hợp cho lab

Script sau **chỉ đọc**, tổng hợp state, applied lag và oplog window **của member đang kết nối**. Để tính headroom của từng secondary, cần thêm window từ sync source riêng.

```javascript
function collectReplicaMetrics353() {
  const s = rs.status();
  const primary = s.members.find(
    m => m.stateStr === "PRIMARY");

  const primaryTime = primary?.optimeDate instanceof Date
    ? primary.optimeDate.getTime()
    : null;

  const members = s.members.map(m => {
    const secondary = m.stateStr === "SECONDARY";
    const time = m.optimeDate instanceof Date
      ? m.optimeDate.getTime() : null;

    return {
      name: m.name,
      state: m.stateStr,
      health: m.health,
      lagSeconds: secondary &&
        primaryTime !== null && time !== null
          ? (primaryTime - time) / 1000
          : null,
      source: m.syncSourceHost || null
    };
  });

  const info = db.getReplicationInfo();

  return {
    sampledAt: new Date(),
    replicaSet: s.set,
    observerState: s.myState,
    oplogWindowHoursOnObserver:
      typeof info.timeDiffHours === "number"
        ? info.timeDiffHours : null,
    oplogUsedMBOnObserver: info.usedMB ?? null,
    members
  };
}

printjson(collectReplicaMetrics353());
```

**Giới hạn cố ý:**

- `oplogWindowHoursOnObserver` chỉ đại diện **node đang kết nối**.
- Không có primary thì lag là null.
- Arbiter không có lag.
- Không tự phát cảnh báo từ một sample.
- Nếu `rs.status()` không có quyền hoặc đang election, script có thể lỗi; exporter phải ghi rõ trạng thái thu thập thất bại.

## 40. Sử dụng `serverStatus()` và quyền monitoring

MongoDB cung cấp nhiều thông tin qua:

```javascript
db.getSiblingDB("admin").serverStatus();
```

Có thể xem:

- `opcounters`, `opcountersRepl`.
- `flowControl`.
- `wiredTiger.cache`.
- `connections`.
- `network`.
- `metrics.repl` hoặc những nhánh liên quan theo version.
- `oplogTruncation` khi hỗ trợ.

### 40.1. Không khóa code vào tên metric bất biến

Cấu trúc `serverStatus()` thay đổi giữa MongoDB versions. Một exporter nên:

1. Xác định version.
2. Detect field availability.
3. Đặt missing values là unknown.
4. Giữ compatibility tests.
5. Không tự map tên metric chưa có thành 0.

### 40.2. RBAC

Role `clusterMonitor` thường phù hợp cho phần lớn mục đích giám sát cluster. Nhưng một số truy vấn `local.oplog.rs` hoặc thông tin cấu hình cần quyền bổ sung tùy deployment. Thay vì cấp `root` cho exporter, kiểm tra tối thiểu những actions required và cấp custom role khi cần.

## 41. Sharded cluster: theo dõi replica set riêng từng shard

Trong MongoDB sharded cluster có:

```text
Application -> mongos
                |
                +-- Shard A replica set
                |     A-P, A-S1, A-S2
                |
                +-- Shard B replica set
                |     B-P, B-S1, B-S2
                |
                +-- Config server replica set
                      C-P, C-S1, C-S2
```

### 41.1. Không có một lag metric duy nhất cho mọi shard

Một shard có lag 2 giây, shard khác 20 phút. Tổng hợp trung bình có thể che rủi ro.

Nên hiển thị theo:

```text
cluster -> replicaSet -> member
```

và định nghĩa “worst lag/headroom” trên từng nhóm phù hợp.

### 41.2. Config servers cũng cần quan sát

Config server replica set lưu metadata quan trọng cho sharding. Nếu thành viên trong đó bất ổn, cluster có thể bị ảnh hưởng dù shard data nodes vẫn hoạt động.

Không đọc metadata config servers bằng những thao tác thay đổi `config.*` để “test replication”. Chỉ dùng công cụ monitoring được hỗ trợ.

### 41.3. Không xem `mongos` là data-bearing replica member

`mongos` là router, không giữ `local.oplog.rs` như primary/secondary của shard. Để xem lag/window, cần truy vấn đúng replica sets hoặc Atlas metrics theo từng shard.

## 42. Tác động tới reads, write concern và failover

### 42.1. Secondary reads có thể cũ

Nếu ứng dụng dùng:

```text
readPreference = secondary
```

thì có thể đọc một bản dữ liệu chưa áp dụng write mới nhất. Nếu nghiệp vụ đòi read-your-writes hoặc consistency mạnh, cần xem lại read preference/read concern/session guarantees.

### 42.2. Lag và max staleness

Driver có tùy chọn **maxStalenessSeconds** với read preference phù hợp để tránh chọn secondary quá cũ theo tiêu chí driver.

Đây không phải thay thế hoàn toàn cho monitoring:

- Driver nhìn topology qua cơ chế SDAM/heartbeats.
- Staleness estimate không phải độ mới tuyệt đối của từng document.
- Cần tuân thủ giới hạn giá trị/phiên bản, bao gồm ngưỡng tối thiểu theo tài liệu driver.
- Nếu tất cả secondary không phù hợp, hành vi chọn server phụ thuộc read preference và topology.

### 42.3. Write concern majority

Write concern `majority` giúp gắn acknowledgement với majority replication guarantees, nhưng không yêu cầu mọi secondary chậm đều bắt kịp.

Nếu lag cao ở secondary phục vụ báo cáo, application dùng majority writes vẫn có thể có báo cáo cũ trên member đó.

### 42.4. Failover readiness

Trong tình huống primary mất:

- Secondary đủ điều kiện election mới có thể thay thế.
- Lag làm tăng rủi ro failover/độ mới.
- Thành viên quá chậm không phải ứng cử viên phù hợp.
- Arbiter không lưu data và không thể thành primary.

Dashboard cần phân biệt **có N nodes healthy** và **có bao nhiêu data-bearing voting/electable members thật sự đủ điều kiện**.

## 43. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách hiểu đúng |
|---|---|---|
| Lấy `Date.now()-secondary.optimeDate` làm lag | Báo giả khi cluster idle | So secondary với primary optime |
| Chỉ nhìn health=1 | Bỏ qua secondary lag | Xem state + optime + headroom |
| Coi `pingMs` là replication lag | Chẩn đoán sai network vs apply | Đo riêng network và oplog progress |
| Parse `rs.printSecondaryReplicationInfo()` như JSON | Script dễ lỗi | Dùng `rs.status()` |
| Dùng `rs.printReplicationInfo()` của primary cho mọi members | Không thấy window khác nhau | Đo đúng member/sync source |
| Coi oplog size 10GB = retention 10h | Sai khi write rate thay đổi | Theo dõi actual window và GB/hour |
| Không theo dõi headroom | Phản ứng muộn với too stale | So window và lag |
| Đánh giá headroom chỉ theo primary | Sai khi chained replication | Xem sync source thực |
| Ép missing lag về 0 | Che DOWN/UNKNOWN | Giữ unknown và health alert |
| Coi lag âm là secondary đi trước primary | Sai do heartbeat/view không đồng bộ | Giữ context và đo lại |
| Alert lag > 30s cho delayed secondary 1h | Báo giả liên tục | Có member-specific thresholds |
| Xem arbiter là secondary có data | Đánh giá sai resiliency | Không tính arbiter trong lag/data replicas |
| Coi `STARTUP2` luôn là lỗi | Báo giả khi initial sync | Theo dõi progress/duration |
| Coi `RECOVERING` luôn too stale | Chẩn đoán sai | Xem `tooStale` và logs |
| Nhầm `applied` với `durable` | Suy sai durability | Xem đúng optime và write concern |
| Thấy flow control rồi tắt ngay | Lag có thể tăng mạnh | Điều tra secondary bottleneck |
| Tăng oplog size để chữa disk failure | Chỉ trì hoãn sự cố | Sửa nguyên nhân apply chậm |
| Đặt min retention quá cao không tính disk | Có thể làm đầy đĩa | Capacity planning |
| Giảm oplog size lúc secondary lag | Có thể mất history | Change review |
| Gọi `replSetResizeOplog` trên Atlas | Command không hỗ trợ | Dùng Atlas settings |
| Gọi `rs.reconfig()` từ monitoring | Thay topology nguy hiểm | Monitoring chỉ đọc |
| Chỉ xem average lag nhiều shards | Che shard bị lag lớn | Per-member/per-shard dashboard |
| Coi replication là backup | Xóa hợp lệ được sao chép | Dùng backup/PITR riêng |
| Không xem metric sampling interval | Bỏ qua spike/đọc sai thời điểm | Hiểu granularity |
| Chỉ lấy một sample rồi báo resolved | Có thể do idle hoặc spike | Theo dõi xu hướng |

## 44. Bài tập thực hành

### Bài 1 — Đọc sơ đồ replication

Vẽ replica set ba member với một primary, hai secondary. Một secondary đồng bộ qua secondary khác. Hãy ghi sync source, luồng oplog fetch và các điểm có thể tạo lag.

### Bài 2 — Tính lag

Primary `optimeDate=12:00:40`; secondary B `12:00:36`; secondary C `11:59:10`. Tính lag xấp xỉ và giải thích vì sao công thức không dùng wall clock hiện tại.

### Bài 3 — Cluster idle

Wall clock `15:00`; primary và secondary đều có last oplog entry `14:00`. Dashboard báo lag 3600 giây. Xác định sai lầm và công thức đúng.

### Bài 4 — Đọc `rs.status()`

Cho:

```javascript
{
  members: [
    { name:"A", stateStr:"PRIMARY", health:1,
      optimeDate:ISODate("2026-11-14T12:00:00Z") },
    { name:"B", stateStr:"SECONDARY", health:1,
      optimeDate:ISODate("2026-11-14T11:59:58Z") },
    { name:"C", stateStr:"SECONDARY", health:1,
      optimeDate:ISODate("2026-11-14T11:58:00Z") }
  ]
}
```

Member nào cần điều tra trước? Vì sao health=1 không có nghĩa data mới?

### Bài 5 — Các trạng thái

Phân loại `PRIMARY`, `SECONDARY`, `STARTUP2`, `RECOVERING`, `UNKNOWN`, `ARBITER`, `DOWN`, `ROLLBACK`. Trạng thái nào không có bản sao dữ liệu? Trạng thái nào có thể bình thường khi initial sync?

### Bài 6 — Heartbeats

Member B có `pingMs=3` nhưng lag 120 giây. Liệt kê ít nhất năm nguyên nhân khác network RTT cần kiểm tra.

### Bài 7 — Oplog window

Trong oplog oldest=08:00, newest=12:30. Tính window. Nếu wall clock hiện tại=13:45, có được thay newest bằng 13:45 không?

### Bài 8 — Window theo tốc độ

Oplog có thể chứa khoảng 12 GiB. Với workload 1 GiB/h và 4 GiB/h, tính retention xấp xỉ trong điều kiện ổn định. Vì sao kết quả thực có thể khác?

### Bài 9 — Headroom

Secondary lag 2 giờ, sync source window 3 giờ. Tính headroom xấp xỉ. Nếu trong 20 phút tiếp theo window co còn 2 giờ 10 phút và lag tăng 2 giờ 5 phút, diễn giải mức rủi ro.

### Bài 10 — Too stale

Sync source oldest oplog entry=11:00; secondary last applied=10:20. Thành viên `RECOVERING` và `tooStale=true`. Xây runbook an toàn, nêu vì sao không ép stepUp hoặc xóa data directory tùy ý.

### Bài 11 — Delayed secondary

Một delayed member cấu hình `secondaryDelaySecs=1800` nhưng report đôi khi hiển thị lag 0. Nêu ít nhất hai nguyên nhân hợp lệ và cách thiết kế alert theo role.

### Bài 12 — Viết script

Dùng `rs.status()` để trả bảng `host`, `stateStr`, `health`, `optimeDate`, `syncSourceHost` và lag so với primary. Không tính arbiter và không tự đưa null về zero.

### Bài 13 — Xem window có cấu trúc

Dùng `db.getReplicationInfo()` để thu `timeDiff`, `timeDiffHours`, `tFirst`, `tLast`, `usedMB`, `logSizeMB`. Vì sao `rs.printReplicationInfo()` không phải nguồn JSON tốt cho scripts?

### Bài 14 — Ghi chậm trên secondary

Disk IOPS secondary đạt giới hạn trong khi write rate primary tăng. Hãy thiết kế điều tra theo timeline và đề xuất biện pháp giảm tải/an toàn.

### Bài 15 — Flow control

Replication lag tăng cùng write latency; `flowControl.isLagged` xuất hiện. Vì sao không nên tắt flow control ngay? Cần đo thêm gì?

### Bài 16 — Oplog retention

Bạn đặt minimum retention 72 giờ, write rate 3 GiB/h, configured oplog size 20 GiB. Tính khối lượng tích lũy xấp xỉ và nêu nguy cơ disk. Hai điều kiện nào cho phép MongoDB truncate entry?

### Bài 17 — Resize oplog

Phân biệt self-managed `replSetResizeOplog` với tùy chọn Atlas. Vì sao giảm size/min retention có thể ảnh hưởng Change Streams và secondary?

### Bài 18 — Election

Cluster có A(primary), B(secondary priority 1), C(hidden priority 0), D(arbiter). Nếu A mất, ai có thể trở thành primary? Phải xem thêm votes/quorum và điều kiện nào?

### Bài 19 — Initial sync

Member mới ở `STARTUP2` trong 4 giờ, disk đang copy dữ liệu và oplog window đang giảm. Những metrics nào giúp phân biệt progress bình thường với nguy cơ initial sync thất bại?

### Bài 20 — Sharded monitoring

Một sharded cluster có hai shard replica sets và một config server replica set. Thiết kế dashboard hiển thị lag/window theo member để không che shard A bị lag lớn bằng trung bình toàn cluster.

### Bài 21 — Atlas alert

Đề xuất ba cảnh báo: Replication Lag, Replication Oplog Window và Replication Headroom. Giải thích tại sao chỉ bật Lag High chưa đủ.

### Bài 22 — Java monitoring

Viết đoạn Java Sync Driver gọi `replSetGetStatus`, lấy primary optime và tính lag của secondary. Nêu cách xử lý `optimeDate` thiếu và bảo vệ URI monitoring.

### Bài 23 — Read staleness

Ứng dụng đọc từ secondary nhưng vừa ghi vào primary. Thảo luận các lựa chọn read preference/read concern/session và vì sao monitoring lag không tự bảo đảm read-your-writes.

### Bài 24 — Sự cố 90 phút mất mạng

Secondary offline 90 phút, oplog window ban đầu 4 giờ nhưng trong outage co xuống 1 giờ. Khi nó trở lại, khả năng too stale ra sao? Cần thu bằng chứng nào?

### Bài 25 — Runbook hoàn chỉnh

Thiết kế incident response với:

```text
Lag grows: 5m -> 20m -> 40m
Oplog window: 3h -> 2h -> 1h
Member state: SECONDARY
Write throughput: tăng 4x
Disk latency: tăng
```

Hãy nêu triage order, chỉ số ưu tiên, biện pháp ngắn hạn, biện pháp dài hạn, tiêu chí kết thúc sự cố và các hành động **không nên tự động thực hiện**.

## 45. Checklist vận hành

### 45.1. Trước khi đưa replica set vào production

1. Có dashboard mỗi member về state/health/lag.
2. Có metric oplog window trên từng member hoặc ít nhất mỗi sync source liên quan.
3. Có headroom metric và cảnh báo theo thời gian phục hồi mục tiêu.
4. Có giám sát Oplog GB/Hour để dự báo window co.
5. Có CPU/disk/cache/network metrics để tìm nguyên nhân lag.
6. Có cảnh báo election, no primary, DOWN, RECOVERING kéo dài.
7. Có cách phân biệt delayed/hidden/arbiter members.
8. Có account monitor với RBAC tối thiểu và TLS.
9. Có alert cho metric collection thất bại.
10. Có runbook resync/initial sync và capacity plan.

### 45.2. Trong quá trình vận hành

1. Theo dõi baseline và xu hướng theo ngày/giờ cao điểm.
2. Kiểm tra oplog window sau major workload changes.
3. Xem các đợt bulk import/cleanup có gây headroom giảm không.
4. Theo dõi secondary read/report workload.
5. Xác minh backup/change-stream consumers vẫn ở trong window.
6. Review topology sau thêm/bớt members hoặc election.
7. Kiểm tra sync source khi lag tăng.
8. Thử alert theo trường hợp missing metrics và DOWN.
9. Có log sự kiện, owner, SLA và tiêu chí xử lý.
10. Không thay config nguy hiểm khi chưa có change approval.

## 46. Tổng kết

**Replication lag, oplog window và member state là ba góc nhìn phải ghép với nhau.** Lag phản ánh tiến độ áp dụng dữ liệu so với primary; oplog window phản ánh lịch sử thay đổi còn tồn tại tại một member; member state và heartbeat nói member có đang đồng bộ, có kết nối và có đủ điều kiện vận hành hay không.

**Dùng đúng công cụ:** `rs.status()` và `replSetGetStatus` cho snapshot có cấu trúc của members; `rs.printSecondaryReplicationInfo()` để đọc nhanh replication lag từ primary; `rs.printReplicationInfo()` để đọc nhanh oplog window của member; `db.getReplicationInfo()` để thu window có cấu trúc vào scripts. Với Atlas, Replication Lag, Replication Oplog Window, Replication Headroom và Oplog GB/Hour cung cấp góc nhìn lịch sử/cảnh báo phù hợp.

**Đừng coi một con số là sự thật tuyệt đối.** Lag bằng 0 có thể đi kèm cluster idle; lag âm có thể do heartbeat không cập nhật đồng thời; arbiter không có dữ liệu; delayed members có lag có chủ đích; window thay đổi theo tốc độ write. Phép tính headroom = window − lag là chỉ báo quan trọng nhưng không phải cam kết còn đúng từng giây khi workload biến động.

**Phản ứng hiệu quả phải dựa vào nguyên nhân và khả năng phục hồi.** Khi secondary chậm, hãy xem network, disk, CPU/cache, workload, sync source và flow control. Khi window co và headroom sắp hết, cần bảo vệ lịch sử oplog và giảm nguyên nhân lag; khi member đã too stale, resync phải theo runbook chính thức. Đừng dùng `rs.reconfig()`, `rs.stepDown()`, resize giảm oplog hay xóa data files như “lệnh thử” để chữa lag.

Một hệ thống quan sát tốt không chỉ báo “secondary chậm”, mà còn cho biết **chậm bao nhiêu, theo nguồn nào, còn bao nhiêu headroom, rủi ro failover là gì và hành động an toàn nào có thể giúp phục hồi**.

## 47. Tài liệu tham khảo

- [MongoDB Manual — Troubleshoot Replication Lag](https://www.mongodb.com/docs/manual/troubleshooting/replication-lag/): đo lag và tìm nguyên nhân network/disk/resource.
- [MongoDB Manual — Troubleshoot Replica Sets](https://www.mongodb.com/docs/manual/tutorial/troubleshoot-replica-sets/): `rs.status()`, lag và flow control.
- [MongoDB Manual — replSetGetStatus](https://www.mongodb.com/docs/manual/reference/command/replsetgetstatus/): member state, heartbeat, optime và tooStale.
- [MongoDB Manual — Replica Set Member States](https://www.mongodb.com/docs/manual/reference/replica-states/): state codes và các trạng thái bình thường/lỗi.
- [MongoDB Manual — Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/): oplog window và retention.
- [MongoDB Manual — rs.printSecondaryReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/rs.printsecondaryreplicationinfo/): báo cáo lag dạng text.
- [MongoDB Manual — rs.printReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/rs.printreplicationinfo/): báo cáo oplog window dạng text.
- [MongoDB Manual — db.getReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/db.getreplicationinfo/): structured oplog metrics cho scripts.
- [MongoDB Manual — replSetResizeOplog](https://www.mongodb.com/docs/manual/reference/command/replsetresizeoplog/): điều chỉnh oplog trên self-managed và các cảnh báo.
- [MongoDB Atlas — Review Alert Conditions](https://www.mongodb.com/docs/atlas/reference/alert-conditions/): Replication Lag, Oplog Window, Headroom, GB/hour.
- [MongoDB Atlas — Review Cluster Metrics](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/): metric granularity và retention.
- [MongoDB Atlas — Fix Oplog Issues](https://www.mongodb.com/docs/atlas/reference/alert-resolutions/replication-oplog/): chẩn đoán oplog window và write rate.
