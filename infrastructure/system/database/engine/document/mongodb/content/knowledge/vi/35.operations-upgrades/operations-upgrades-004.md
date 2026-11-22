# Chuyển primary, thay thành viên và giảm gián đoạn kết nối trong MongoDB

## 1. Một lần bảo trì replica set có thể ảnh hưởng người dùng thế nào?

Giả sử ứng dụng đặt hàng dùng MongoDB replica set ba thành viên:

```text
                  Java Order Service
                          |
                     MongoDB driver
                          |
             +------------+-------------+
             |            |             |
             v            v             v
         mongo-a        mongo-b       mongo-c
         PRIMARY        SECONDARY     SECONDARY
         votes=1        votes=1       votes=1
         priority=1     priority=1    priority=1
```

Đội vận hành cần thay máy chủ `mongo-a`. Nếu tắt primary ngay mà không kiểm tra cụm, ứng dụng có thể gặp:

- Không có primary trong khoảng thời gian election; một số lệnh ghi thất bại hoặc phải chờ.
- Driver đang mở connection đến primary cũ và phải phát hiện topology mới.
- Write vừa được gửi nhưng kết quả chưa về, khiến ứng dụng **không biết thao tác đã thành công hay chưa**.
- Secondary đang chậm quá xa và không đủ điều kiện bầu chọn an toàn.
- Việc tháo một voting member làm mất majority nếu đồng thời một node khác gặp lỗi.
- Certificate, DNS hoặc replica set configuration chưa sẵn sàng trên máy thay thế.

Một quy trình tốt không hứa “chuyển primary hoàn toàn không có gián đoạn”. Nó **giảm thời gian không có primary, giới hạn lỗi quan sát từ ứng dụng và tránh mất dữ liệu do thao tác vận hành sai**.

### 1.1. Mục tiêu bài học

Sau bài, bạn có thể:

1. Phân biệt **planned switchover**, **automatic failover**, **stepdown**, **election** và **rollback**.
2. Xác định điều kiện về majority/quorum, optime, replication lag, voting, priority và khả năng ứng cử primary.
3. Lập runbook chuyển primary bằng `rs.stepDown()` hoặc cơ chế vận hành được hỗ trợ.
4. Thêm, thay và loại thành viên replica set an toàn với `rs.add()`, `rs.remove()`, `rs.conf()` và `rs.reconfig()`.
5. Quản lý initial sync, oplog window, member health, TLS, DNS, hostnames và các giới hạn của sharded cluster.
6. Cấu hình Java MongoDB driver để phát hiện topology mới, dùng retryable operations phù hợp và không nhân đôi side effect nghiệp vụ.
7. Tổ chức rolling maintenance/rolling upgrade, giám sát failover và kiểm thử khả năng phục hồi có kiểm soát.
8. Phân biệt biện pháp giảm gián đoạn kết nối với những bảo đảm **durability/consistency** của write concern và transaction.

**Phạm vi an toàn:** ví dụ mongosh chủ yếu phục vụ lab replica set do bạn quản trị. Các lệnh `rs.stepDown()`, `rs.add()`, `rs.remove()`, `rs.reconfig()` và restart member **làm thay đổi trạng thái hệ thống**; không chạy trên production nếu chưa có phê duyệt, backup và phương án rollback.

## 2. Những khái niệm phải phân biệt

| Khái niệm | Ý nghĩa | Có chủ đích? |
|---|---|---|
| **Primary** | Thành viên nhận các writes thông thường của replica set | Vai trò do election quyết định |
| **Secondary** | Thành viên đồng bộ bằng oplog và có thể phục vụ reads theo cấu hình | Vai trò vận hành |
| **Election** | Quá trình các voting members chọn primary theo quy tắc replica set | Có thể tự động hoặc sau thao tác |
| **Automatic failover** | Primary bị mất hoặc không còn đáp ứng điều kiện; cụm bầu primary mới | Thường do sự cố |
| **Planned switchover** | Chủ động chuyển primary để bảo trì, cân bằng vận hành | Có |
| **Stepdown** | Primary tự rời vai trò primary và tạm không đủ điều kiện quay lại | Có hoặc do server |
| **StepUp** | Yêu cầu secondary phù hợp cố gắng trở thành primary | Chủ động, phụ thuộc điều kiện |
| **Initial sync** | Member mới nhận toàn bộ dữ liệu ban đầu và bắt kịp oplog | Có thể tốn thời gian |
| **Rollback** | Loại bỏ thay đổi không thuộc lịch sử được chọn sau failover | Không phải cơ chế backup |

### 2.1. Switchover khác failover

**Switchover:** đội vận hành chọn thời điểm, kiểm tra secondary ứng viên, phối hợp ứng dụng, sau đó chuyển primary.

**Failover:** primary bất ngờ mất, các member còn lại tự bầu primary nếu đủ quorum và có ứng viên hợp lệ.

Hai quá trình dùng election machinery tương tự, nhưng **switchover có lợi thế chuẩn bị trước**. Khi failover xảy ra vì network partition, việc mất primary có thể kéo dài hơn dự kiến.

### 2.2. Primary mới không nhất thiết là member được mong muốn

Priority, freshness, voting, khả năng kết nối và điều kiện election ảnh hưởng kết quả. Không được giả định `rs.stepDown()` tự chỉ định chính xác `mongo-b` làm primary. Cần **xác minh kết quả** sau election.

### 2.3. Một hệ thống có primary không đồng nghĩa tất cả dữ liệu đều mới

Secondary có thể đang replication lag; primary mới được bầu dựa trên những điều kiện nhất định. Với các write không đạt majority acknowledgement, một số dữ liệu có thể bị rollback sau failover. Chỉ nhìn `stateStr: "PRIMARY"` không đủ đánh giá toàn vẹn nghiệp vụ.

## 3. Majority và quorum: ranh giới không thể bỏ qua

Replica set bầu primary bằng phiếu của **voting members**. Với N voting members, cần đa số:

\[
\text{majority} = \left\lfloor\frac{N}{2}\right\rfloor + 1
\]

Ví dụ:

| Voting members | Majority cần | Tối đa voting members mất mà còn majority |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 0 |
| 3 | 2 | 1 |
| 4 | 3 | 1 |
| 5 | 3 | 2 |
| 7 | 4 | 3 |

MongoDB replica set có thể chứa tối đa 50 members nhưng chỉ tối đa **7 voting members**. Không nhầm “thêm 10 secondary” với “có 10 phiếu”.

### 3.1. Ví dụ ba voters

```text
mongo-a PRIMARY   votes=1
mongo-b SECONDARY votes=1
mongo-c SECONDARY votes=1

Majority = 2
```

Nếu `mongo-a` ngừng, `mongo-b` và `mongo-c` còn 2/3 phiếu nên có thể bầu primary mới **nếu** chúng khỏe, liên lạc được và có thành viên đủ điều kiện.

Nếu đang bảo trì `mongo-b` rồi `mongo-a` bất ngờ ngừng:

```text
mongo-a DOWN
mongo-b DOWN
mongo-c SECONDARY

Chỉ còn 1/3 votes => không đủ majority.
```

Hệ quả: không có primary được bầu hợp lệ, khả năng ghi bị gián đoạn.

### 3.2. Quorum không phải số lượng data-bearing copies

**Arbiter** có phiếu bầu nhưng không lưu dữ liệu. Nó có thể giúp election, nhưng:

- Không phục vụ reads.
- Không đồng bộ oplog như secondary.
- Không trở thành primary.
- Không thay thế một data-bearing member cho mục tiêu redundancy.

Trong topology hai data-bearing nodes + một arbiter, khi một data-bearing node mất, ý nghĩa của write concern `majority` và durability cần được hiểu theo chính sách MongoDB của version/topology. Không dùng arbiter như “secondary dữ liệu thứ ba”.

### 3.3. Đừng thay đổi quorum tùy tiện khi đang lỗi

Vội thay votes hoặc gọi `rs.reconfig(..., {force: true})` khi network partition có thể gây khó khăn phục hồi và rủi ro rollback. Phải xác định view của từng member, majority và lịch sử đã được commit trước khi thay cấu hình.

## 4. Election eligibility: ai có thể thành primary?

Một member không tự đủ điều kiện chỉ vì đang ở trạng thái `SECONDARY`.

### 4.1. Các điều kiện cần xem

- `votes`: member có quyền bầu không?
- `priority`: member có được ứng cử và mức ưu tiên là bao nhiêu?
- `hidden`: thường đi kèm `priority: 0`.
- `secondaryDelaySecs`: delayed secondary có cấu hình hạn chế ứng cử.
- Trạng thái `SECONDARY` và tiến độ replication.
- Độ mới của dữ liệu/optime so với members khác.
- Mạng và khả năng liên lạc với đa số voting members.
- Member có đang `frozen` hoặc trong giai đoạn initial sync không?

### 4.2. Ví dụ một member không ứng cử

```javascript
{
  _id: 2,
  host: "mongo-c.example.internal:27017",
  votes: 1,
  priority: 0,
  hidden: true
}
```

Member này có thể tham gia biểu quyết nhưng không trở thành primary khi `priority: 0`.

### 4.3. Không đồng nhất `votes` và `priority`

`votes` góp vào quorum/election; `priority` ảnh hưởng việc member có thể thành primary và thứ tự ưu tiên. Một voting member `priority: 0` có thể bỏ phiếu nhưng không ứng cử.

### 4.4. Priority cao không đảm bảo chuyển ngay

Ngay cả khi `mongo-b.priority=2` và `mongo-c.priority=1`, nếu `mongo-b` chậm, unreachable hoặc chưa đủ điều kiện, kết quả election có thể khác kỳ vọng.

**Không điều khiển switchover chỉ bằng một con số priority rồi bỏ bước xác minh freshness.**

## 5. Replication lag và oplog window trước khi chuyển primary

### 5.1. Replication lag

Replication lag xấp xỉ độ chênh thời gian giữa oplog entry cuối đã apply trên primary và secondary:

\[
\text{lag}_{secondary} \approx
\text{primaryLastApplied} - \text{secondaryLastApplied}
\]

Giả sử:

```text
Primary last applied:    12:00:30
Secondary B applied:     12:00:29
Secondary C applied:     11:57:00

B lag ≈ 1 giây
C lag ≈ 3 phút 30 giây
```

`mongo-b` trông có vẻ là ứng viên tốt hơn, nhưng vẫn phải xem health, votes, priority, durable optime, network và resources.

### 5.2. Oplog window

Oplog window là khoảng thời gian giữa entry cũ nhất và mới nhất còn trong `local.oplog.rs`. Nếu secondary bị dừng quá lâu, sync source có thể xóa những entries nó cần trước khi secondary quay lại.

### 5.3. Headroom

Một ước lượng:

\[
\text{headroom} \approx
\text{syncSourceOplogWindow} - \text{replicationLag}
\]

Đây là **chỉ báo**, không phải deadline chính xác vì tốc độ writes có thể thay đổi.

### 5.4. Vì sao quan trọng khi thay member?

Initial sync node mới có thể kéo dài hàng giờ. Trong thời gian đó, những thay đổi trên primary phải được giữ đủ lâu để member mới bắt kịp.

Nếu write rate quá cao khiến oplog window co nhanh, initial sync có thể thất bại và phải thực hiện lại.

### 5.5. Cụm ít ghi có thể có lag hiển thị gây hiểu lầm

Đừng lấy wall clock hiện tại trừ `secondary.optimeDate` rồi gọi đó là lag. Khi primary đã không ghi trong một giờ và secondary cũng áp dụng tới cùng optime, nó có thể **đã bắt kịp hoàn toàn**.

## 6. Công cụ quan sát trước mọi thao tác

Các lệnh sau chỉ đọc:

```javascript
rs.status();
rs.conf();
rs.printSecondaryReplicationInfo();
rs.printReplicationInfo();
db.getReplicationInfo();
```

### 6.1. `rs.status()`

```javascript
const status = rs.status();
printjson(status);
```

Một output minh họa:

```javascript
{
  set: "rsShop",
  date: ISODate("2026-11-14T12:00:40Z"),
  term: NumberLong("12"),
  members: [
    {
      _id: 0,
      name: "mongo-a.example.internal:27017",
      stateStr: "PRIMARY",
      state: 1,
      health: 1,
      optimeDate: ISODate("2026-11-14T12:00:30Z")
    },
    {
      _id: 1,
      name: "mongo-b.example.internal:27017",
      stateStr: "SECONDARY",
      state: 2,
      health: 1,
      optimeDate: ISODate("2026-11-14T12:00:29Z")
    },
    {
      _id: 2,
      name: "mongo-c.example.internal:27017",
      stateStr: "SECONDARY",
      state: 2,
      health: 1,
      optimeDate: ISODate("2026-11-14T12:00:25Z")
    }
  ],
  ok: 1
}
```

Các field nêu trên là output **rút gọn để giải thích**, không phải mẫu bất biến cho mọi MongoDB version.

### 6.2. `rs.conf()`

```javascript
const cfg = rs.conf();
printjson(cfg.members.map(m => ({
  _id: m._id,
  host: m.host,
  votes: m.votes,
  priority: m.priority,
  hidden: m.hidden,
  secondaryDelaySecs: m.secondaryDelaySecs
})));
```

`rs.status()` nói **member đang làm gì**; `rs.conf()` nói **member được cấu hình ra sao**.

### 6.3. `rs.printSecondaryReplicationInfo()`

```javascript
rs.printSecondaryReplicationInfo();
```

Phù hợp để người vận hành đọc nhanh lag từ primary, nhưng đây là báo cáo text. Với scripts/exporters, sử dụng `rs.status()` hoặc command `replSetGetStatus`.

### 6.4. `rs.printReplicationInfo()`

```javascript
rs.printReplicationInfo();
```

Xem nhanh oplog window **của member đang kết nối**, không tự có window của mọi member.

### 6.5. `db.getReplicationInfo()`

```javascript
printjson(db.getReplicationInfo());
```

Một số field thường có: `logSizeMB`, `usedMB`, `timeDiff`, `timeDiffHours`, `tFirst`, `tLast`.

### 6.6. Kiểm tra từ đúng thành viên

Nếu MongoDB URI chọn primary tự động, lệnh xem oplog có thể đang chạy trên primary dù muốn quan sát secondary.

Khi cần chẩn đoán từng node, dùng kết nối trực tiếp phù hợp:

```bash
mongosh "mongodb://mongo-b.example.internal:27017/admin?directConnection=true&tls=true" --tlsCAFile /secure/path/ca.pem --username monitor_user --password
```

`directConnection=true` thích hợp cho chẩn đoán riêng một node, **không** phải lựa chọn cho URI ứng dụng cần tự động failover.

## 7. Danh sách kiểm tra trước planned switchover

### 7.1. Tình trạng replica set

1. Xác nhận primary hiện tại và ít nhất một secondary ứng viên.
2. Kiểm tra có đủ majority voters đang giao tiếp.
3. Kiểm tra ứng viên `health: 1` và `stateStr: "SECONDARY"`.
4. Đảm bảo ứng viên có `priority > 0` và `votes: 1`.
5. Kiểm tra replication lag gần mục tiêu chấp nhận được.
6. Kiểm tra oplog window/headroom rộng.
7. Xem có initial sync, rollback, RECOVERING hoặc election storm không.
8. Kiểm tra cluster không thiếu disk/CPU/network capacity.

### 7.2. Trạng thái ứng dụng

1. Java driver phiên bản được hỗ trợ và đã cấu hình replica set discovery.
2. Có đủ seed hosts/SRV và DNS/TLS đúng cho primary mới.
3. Có retryable reads/writes phù hợp.
4. Có application-level idempotency cho các operation quan trọng.
5. API xử lý lỗi chọn server, write concern timeout và transaction retry.
6. Load balancer/health checks không khóa cứng một primary hostname.
7. Monitoring có dashboard MongoDB + application cùng timeline.
8. Có thời gian bảo trì, người chịu trách nhiệm và đường rollback.

### 7.3. Không có điều kiện nào được tự coi là đúng

Ví dụ `health:1` chưa đủ chứng minh secondary mới đủ điều kiện election; `lag:0` chưa đủ chứng minh application đã sử dụng đúng read preference; driver có `retryWrites=true` chưa đủ để bảo đảm mọi business command idempotent.

## 8. `rs.stepDown()`: chuyển primary có kế hoạch

### 8.1. Cú pháp

Trong `mongosh` kết nối trực tiếp tới **primary hiện tại** trên **replica set lab**:

```javascript
rs.stepDown(60, 15);
```

Ý nghĩa:

- `60`: khoảng thời gian primary cũ không được trở lại primary, tính giây.
- `15`: khoảng thời gian tối đa dành cho secondary bắt kịp trước khi stepdown theo cơ chế command.

Method sử dụng command `replSetStepDown`. Tham số và hành vi cụ thể phải đối chiếu với MongoDB version đang vận hành.

### 8.2. Lệnh command tương đương

```javascript
db.getSiblingDB("admin").runCommand({
  replSetStepDown: 60,
  secondaryCatchUpPeriodSecs: 15
});
```

**Không chạy thử** lệnh này trên production. Đây là thao tác có thể khiến writes bị gián đoạn ngắn trong election.

### 8.3. Điều kiện stepdown bình thường

Trong chế độ không ép buộc, server kiểm tra điều kiện election/catch-up để không rời primary một cách thiếu an toàn khi không có secondary thích hợp.

Nếu không đủ điều kiện, lệnh có thể thất bại thay vì chuyển primary. Cần kiểm tra nguyên nhân trước khi lặp lại.

### 8.4. Vì sao lệnh có thể trả network error?

Khi server step down, các connections/in-flight operations tới primary cũ có thể bị ngắt. Shell có thể thấy lỗi mạng hoặc thông báo kiểu “not primary” dù việc stepdown đã có tác dụng.

**Không suy rằng network error nghĩa là stepdown chắc chắn thất bại.**

Hãy reconnect qua **replica set URI**, lấy lại `rs.status()` và xác nhận primary mới.

### 8.5. Không dùng `force` như đường tắt

Một command với `force: true` có thể bỏ qua một số kiểm tra an toàn và làm primary rời vai trò ngay cả khi không có secondary bắt kịp.

Đây là hành động rủi ro với availability và các writes chưa commit. Không dùng để “ép cho xong lịch bảo trì”.

## 9. Trình tự switchover giảm gián đoạn

```text
            PREPARE
          kiểm tra quorum
          kiểm tra lag
          ứng viên electable
          client retry/metrics
                |
                v
             EXECUTE
           rs.stepDown()
                |
                v
       Election / topology update
                |
                v
             VERIFY
       new primary identified
       majority writes succeed
       app operations recover
       old primary becomes SECONDARY
                |
                v
          CONTINUE MAINTENANCE
          on old primary host
                |
                v
          POST-CHECK / REPORT
```

### 9.1. Bước 1: ghi snapshot trạng thái ban đầu

```javascript
printjson({
  at: new Date(),
  status: rs.status(),
  config: rs.conf()
});
```

Ở môi trường thật, output này có topology/hostnames nhạy cảm; lưu bằng kênh bảo mật và hạn chế quyền truy cập.

### 9.2. Bước 2: chọn maintenance window

Ưu tiên:

- Lượng writes ít.
- Không có bulk import/backfill lớn.
- Không trong lúc initial sync hoặc resharding phức tạp.
- Ứng dụng có khả năng retry và observability.
- Có operator theo dõi và phương án hoãn.

### 9.3. Bước 3: kiểm tra ứng viên

Ứng viên cần:

```text
state=SECONDARY
health=1
votes=1
priority>0
replication lag phù hợp
không đang rollback/initial sync
network / disk ổn định
```

Nếu không có ứng viên, **không cưỡng ép stepdown** chỉ để hoàn tất kế hoạch.

### 9.4. Bước 4: thực hiện

```javascript
// Trên primary của replica set lab, sau khi đủ preflight.
rs.stepDown(60, 15);
```

Không kèm vòng lặp vô hạn gọi lại lệnh nếu mất connection.

### 9.5. Bước 5: reconnect qua URI đầy đủ

```bash
mongosh "mongodb://mongo-a.example.internal:27017,mongo-b.example.internal:27017,mongo-c.example.internal:27017/?replicaSet=rsShop&tls=true" --tlsCAFile /secure/path/ca.pem --username monitor_user --authenticationDatabase admin --password
```

Ứng dụng nên sử dụng seed list/SRV và driver discovery; không bắt buộc biết trước primary mới là ai.

### 9.6. Bước 6: xác minh

```javascript
const after = rs.status();
printjson(after.members.map(m => ({
  host: m.name,
  state: m.stateStr,
  health: m.health,
  optimeDate: m.optimeDate
})));
```

Đồng thời kiểm tra:

- Có đúng một primary hoạt động theo view cluster hợp lệ.
- Majority write trong lab thành công.
- Old primary chuyển thành secondary và tiếp tục đồng bộ.
- Replication lag ổn định trở lại.
- Application errors/retries trở lại baseline.
- Không có rollback/data inconsistency bất thường.

## 10. Không thể hứa zero downtime tuyệt đối

Ngay cả với replica set khỏe và driver được cấu hình đúng:

- Election mất thời gian.
- Client cần phát hiện topology mới.
- In-flight operations có thể nhận lỗi.
- Một số operations **không thể retry an toàn**.
- Transaction đang chạy có thể bị abort.
- Write concern timeout có thể tạo trạng thái kết quả không chắc chắn.

Do đó, mục tiêu thực tế là **tự phục hồi nhanh và có biện pháp xử lý lỗi/duplicate đúng**.

### 10.1. “Ứng dụng vẫn phục vụ” khác “mọi request thành công”

API có thể vẫn nhận HTTP request trong election nhưng một phần writes tạm thất bại. Nếu frontend có chức năng retry hợp lý và backend có idempotency, người dùng có thể ít nhận ra.

Điều này không được phép che giấu những request đã thất bại hoặc trả kết quả sai. Hệ thống vẫn cần đo error rate, latency và user-visible failures.

### 10.2. SLO nên định nghĩa rõ

Ví dụ nội bộ:

```text
Planned switchover:
  p95 database failover completion <= mục tiêu đã đo
  user-visible write failure rate <= ngưỡng tổ chức chấp nhận
  no acknowledged majority write loss
```

Không đặt con số cố định dựa trên ví dụ; đo với cluster/driver/network thật.

## 11. Automatic failover khi primary mất bất ngờ

### 11.1. Timeline minh họa

```text
T0       mongo-a PRIMARY dừng
T0+...   members phát hiện heartbeat thất bại
T0+...   election bắt đầu
T0+...   mongo-b được bầu PRIMARY
T0+...   driver cập nhật topology
T0+...   write requests tiếp tục trên mongo-b
```

Không có thời gian cố định cho mỗi bước; network partition, election timeouts, topology/priority, driver configuration và tải hạ tầng ảnh hưởng kết quả.

### 11.2. Không majority: không có primary

Nếu không đủ votes để bầu, MongoDB **không** tạo primary mới chỉ vì có một secondary khỏe. Đây là hành vi bảo vệ consistency.

### 11.3. Primary cũ có thể quay lại

Sau khi mạng hồi phục hoặc máy được bật, primary cũ thường tái nhập với vai trò secondary và đồng bộ theo lịch sử hợp lệ; có thể cần rollback những writes chưa được majority committed.

### 11.4. Không nhầm failover với backup restore

Failover chuyển quyền phục vụ sang member khác. Nó không phục hồi được dữ liệu đã bị xóa hợp lệ và replication sang mọi member; cần backup/PITR để xử lý xóa nhầm.

## 12. Rollback, write concern và dữ liệu đã được xác nhận

### 12.1. Write concern `w:1`

Với `w:1`, primary có thể acknowledgement trước khi write được sao chép tới majority. Nếu primary mất trước khi write trở thành majority committed, write đó có thể bị rollback sau election.

### 12.2. Write concern `w:"majority"`

Với `w:"majority"`, write được acknowledged khi đạt majority criteria theo topology/version. Nó giúp giảm rủi ro rollback của write đã được majority acknowledged.

Tuy nhiên:

- Không yêu cầu mọi secondary đều đã cập nhật.
- Không thay thế backup.
- Một write concern timeout không tự chứng minh write **chưa** được áp dụng.
- Chính sách journal/durability và write concern cần được xét theo version/config.

### 12.3. Ví dụ Java mongosh

Trong mongosh:

```javascript
const orders = db.getSiblingDB("ops_lab_376").orders;

orders.insertOne(
  {
    _id: "ORDER-LAB-001",
    status: "CREATED",
    createdAt: new Date()
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
```

Chỉ chạy trên lab mới; `_id` cố định giúp tránh chèn trùng khi xử lý request thử nghiệm. Với production cần chính sách idempotency toàn bộ nghiệp vụ.

### 12.4. `wtimeout` và uncertainty

Nếu server trả lỗi write concern timeout, lệnh có thể đã được thực hiện trên primary nhưng chưa đạt write concern trong khoảng chờ.

**Không tự lặp một thao tác non-idempotent với request mới rồi khẳng định an toàn**. Cần reconciliation dựa trên operation ID/unique business key.

## 13. Retryable writes: ích lợi và giới hạn

### 13.1. Cơ chế

MongoDB driver hỗ trợ retryable writes trên replica set/sharded cluster tương thích. Khi gặp lỗi mạng hoặc lỗi khả dụng phù hợp, driver có thể tự retry **một số loại thao tác ghi được hỗ trợ**, sử dụng thông tin session/transaction number để giảm nguy cơ thực hiện lại cùng một write.

```text
App issues write
     |
     v
Driver sends to PRIMARY-A
     |
     v
Primary-A steps down / connection lost
     |
     v
Driver discovers PRIMARY-B
     |
     v
Driver retries if operation and error are eligible
```

### 13.2. Những điều retryable writes không giải quyết

- Không làm mọi lệnh MongoDB retryable.
- Không bảo đảm transaction phức tạp tự thành công.
- Không xử lý business API request được gửi lại như một **tác vụ mới**.
- Không giúp nếu timeout client quá ngắn khiến không tìm được primary mới.
- Không thay majority durability hay application idempotency.

### 13.3. Retryable writes khác application-level retry

Ví dụ:

```text
Client POST /orders
  -> API tạo order mới O1
  -> DB insert thành công
  -> response mất

Client POST /orders lần nữa
  -> API tạo order mới O2
```

Driver retryable writes có thể bảo vệ **cùng một database operation trong cùng retry protocol**; nó không tự ngăn backend tạo một order mới khi client gửi lại HTTP request khác.

### 13.4. Idempotency key

Một API nên dùng khóa nghiệp vụ ổn định:

```javascript
{
  _id: "O1001",
  tenantId: "T01",
  requestId: "CHECKOUT-REQ-123",
  status: "CREATED"
}
```

Và unique index theo phạm vi:

```javascript
db.orders.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true }
);
```

Khi retry request, backend kiểm tra order đã gắn với requestId đó và trả kết quả phù hợp. Đối với sharded collection, unique-index constraints còn phụ thuộc shard key; phải thiết kế theo topology.

## 14. Retryable reads, transaction và change streams

### 14.1. Retryable reads

Driver có thể retry một số read operations khi lỗi đủ điều kiện. Tuy nhiên:

- Không phải mọi aggregation/command đều retryable.
- Read sau failover có thể thấy state khác nếu dữ liệu đang thay đổi.
- Một read retry không có nghĩa truy vấn dùng chung snapshot.

### 14.2. Transaction giữa lúc chuyển primary

Một transaction có thể bị abort do stepdown, election hoặc network error. Ứng dụng cần xử lý các error labels/transient transaction errors và unknown commit results theo API driver.

### 14.3. Callback transaction và side effects

Khi driver/helper retry transaction callback, code callback có thể chạy lại. **Không gửi email, trừ tiền ngoài MongoDB hoặc gọi HTTP side effect không idempotent bên trong callback** nếu không có cơ chế kiểm soát.

### 14.4. Change streams

Change streams có thể resume sau gián đoạn ngắn bằng resume token nếu oplog history còn đủ. Nhưng:

- Phải lưu checkpoint token an toàn.
- Oplog window phải phù hợp downtime.
- Event handler cần idempotency.
- Resume token không phải bản sao dữ liệu vĩnh viễn.

Một switchover tốt cần kiểm tra cả consumers CDC, không chỉ ứng dụng CRUD.

## 15. URI ứng dụng phải mô tả một replica set, không khóa primary

### 15.1. URI replica set đúng mục đích

```text
mongodb://mongo-a.example.internal:27017,mongo-b.example.internal:27017,mongo-c.example.internal:27017/shop?replicaSet=rsShop&retryWrites=true&retryReads=true&tls=true&w=majority
```

Ứng dụng kết nối vào **replica set topology**, driver theo dõi ai là primary.

### 15.2. Vì sao không dùng directConnection cho application?

```text
mongodb://mongo-a.example.internal:27017/?directConnection=true
```

URI này nhắm một host cụ thể. Nếu host đó stepdown/mất, application không có cấu hình topology discovery phù hợp để tự chuyển sang primary khác theo cách dùng replica set thông thường.

`directConnection=true` có chỗ dùng cho chẩn đoán member riêng, không phải mặc định cho service cần high availability.

### 15.3. MongoDB Atlas và SRV

Atlas thường dùng URI `mongodb+srv://...`, qua DNS SRV để tìm topology/seed hosts. Cần:

- DNS có thể resolve từ application environment.
- TLS certificate chain hợp lệ.
- IP access list/private endpoint đúng.
- Driver tương thích phiên bản.
- Secret không hardcode trong source hoặc log.

### 15.4. Hostnames do replica set công bố

Seed hosts chỉ là điểm khởi đầu. Driver còn đọc hostnames trong replica set configuration.

Vì vậy **tất cả names trong `rs.conf().members[].host` phải resolvable và reachable từ clients phù hợp**, không chỉ hostname đầu tiên ở URI.

## 16. DNS, TLS và certificate khi thay member

### 16.1. Một thay đổi hostname có thể phá discovery

Giả sử member mới:

```text
mongo-d.example.internal:27017
```

được thêm vào `rs.conf()` nhưng application network chỉ có DNS tới `mongo-a/b/c`. Driver có thể phát hiện `mongo-d` qua hello và cố kết nối nhưng thất bại.

### 16.2. Kiểm tra trước khi thêm

- DNS resolution từ mọi member và client environment.
- Network routes và firewall/security group.
- TLS SAN chứa hostname được kết nối.
- Certificate chain/CA trusted.
- MongoDB authentication/cluster internal auth.
- MongoDB `replSetName` trùng.
- Data path và disk capacity đúng.
- Clock synchronization/OS hardening.

### 16.3. Không tắt TLS validation để “cho chạy”

Không dùng các tùy chọn bỏ qua certificate/hostname validation trong production chỉ vì member mới bị lỗi SAN. Sửa certificate/DNS hợp lệ.

### 16.4. Reusing hostname có rủi ro

Nếu thay hardware nhưng giữ DNS name cũ, phải chắc chắn node cũ đã ngừng và không có **hai mongod cùng tự nhận một identity** hoặc data directory không tương thích.

Nếu thay bằng hostname mới, dùng quy trình add/sync/remove đúng cấu hình thay vì sửa DNS mà bỏ qua replica set membership.

## 17. Driver SDAM: phát hiện primary mới

Các MongoDB drivers thực hiện **Server Discovery and Monitoring (SDAM)**. Chúng quan sát server descriptions, topology type, hello responses và trạng thái kết nối để chọn server cho lệnh.

### 17.1. Những điều xảy ra khi election

```text
Primary A                     Driver
  |                             |
  +-- steps down --------------> connection error/not primary
                                |
                                v
                         topology marked unknown
                                |
                                v
                         hello / monitoring
                                |
                                v
                         Primary B discovered
                                |
                                v
                         eligible operations retried
```

Tốc độ ứng dụng phục hồi phụ thuộc nhiều yếu tố, không chỉ election time: heartbeat/hello, server selection timeout, connection establishment và TLS.

### 17.2. Không tự hardcode primary vào business logic

Không nên:

```java
String primaryHost = "mongo-a.example.internal";
// Mỗi lệnh ghi luôn nhắm primaryHost cũ.
```

Nên để MongoDB driver quản lý replica set topology và dùng một `MongoClient` sống lâu cho service.

### 17.3. Một MongoClient cho cả pool

Không tạo `MongoClient` mới cho mọi HTTP request. Làm vậy tạo nhiều connection pools, nhiều TLS handshakes và tăng độ trễ khi topology thay đổi.

Sử dụng client singleton/managed bean theo vòng đời ứng dụng, đóng khi service shutdown.

## 18. Cấu hình Java MongoDB Sync Driver

### 18.1. Ví dụ cơ bản

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

import java.util.concurrent.TimeUnit;

public final class MongoClientFactory376 {
    public static MongoClient create() {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is missing");
        }

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .retryWrites(true)
            .retryReads(true)
            .applyToClusterSettings(builder ->
                builder.serverSelectionTimeout(
                    15, TimeUnit.SECONDS))
            .applyToConnectionPoolSettings(builder ->
                builder.maxSize(100))
            .build();

        return MongoClients.create(settings);
    }
}
```

Ví dụ yêu cầu Java 11+ do `String.isBlank()`. Kích thước pool, timeout và retry settings **không phải cấu hình chuẩn cho mọi workload**; phải đo và chọn theo SLO.

### 18.2. Connection string qua secret manager

`MONGODB_URI` chỉ là ví dụ nhận cấu hình từ environment. Production nên dùng secret manager/identity solution và không in URI chứa credentials ra logs.

### 18.3. Những timeout phải phân biệt

| Cấu hình | Mục đích | Rủi ro khi quá thấp/quá cao |
|---|---|---|
| `serverSelectionTimeoutMS` | Thời gian driver cố chọn server phù hợp | Quá thấp: fail request khi election; quá cao: HTTP treo lâu |
| `connectTimeoutMS` | Giới hạn thời gian thiết lập TCP connection | Quá thấp: network chậm thất bại; quá cao: chờ lâu |
| `socketTimeoutMS` | Giới hạn chờ I/O trên socket theo driver | Quá thấp: cắt query hợp lệ; quá cao: request kéo dài |
| `maxPoolSize` | Số connection tối đa trong pool | Quá nhỏ: queue; quá lớn: áp lực connection |
| `waitQueueTimeoutMS` hoặc tùy chọn tương đương | Chờ connection từ pool | Cần phối hợp request deadline |

Tên tùy chọn/khả năng builder cụ thể phụ thuộc driver version. Không chỉnh một timeout đơn lẻ mà bỏ qua tổng HTTP request deadline, retry budget và hệ quả idempotency.

### 18.4. Timeout không giúp tự sinh majority

Nếu cụm mất quorum, tăng `serverSelectionTimeoutMS` lên một phút chỉ làm client đợi lâu hơn. Nó không khiến một secondary không đủ votes tự thành primary.

## 19. Java: kiểm tra kết nối và topology sau switchover

```java
import com.mongodb.MongoException;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class ReplicaHealth376 {
    public static void check(MongoClient client) {
        MongoDatabase admin = client.getDatabase("admin");

        try {
            Document hello = admin.runCommand(
                new Document("hello", 1));
            System.out.println(
                "isWritablePrimary=" +
                hello.getBoolean("isWritablePrimary"));
        } catch (MongoException e) {
            System.err.println(
                "MongoDB health check failed: " +
                e.getClass().getSimpleName());
            throw e;
        }
    }
}
```

### 19.1. Một `hello` không chứng minh toàn cụm ổn

Đây chỉ là kết quả từ **server được driver chọn** cho command. Với health monitoring cần thêm replica set status, application write probes và metrics từ nhiều members theo quyền được cấp.

### 19.2. Không lộ thông tin topology trên endpoint công khai

Một endpoint `/health` công khai không nên trả raw `rs.status()`, hostnames, auth details, config và credentials.

Đưa thông tin chi tiết vào internal monitoring có AuthN/AuthZ.

## 20. Xử lý lỗi write khi primary thay đổi

### 20.1. Những nhóm lỗi

- Network connection closed/reset.
- Server selection timeout khi không có primary.
- `NotWritablePrimary` hoặc lỗi repl-state change.
- Write concern timeout.
- Transaction transient/unknown commit outcome.
- Duplicate key khi retry business request với cùng ID.

### 20.2. Đừng bắt mọi exception rồi retry vô hạn

Một đoạn code nguy hiểm:

```java
// KHÔNG NÊN:
while (true) {
    try {
        inventory.updateOne(filter, update);
        break;
    } catch (Exception ignored) {
        // Retry forever; có thể double-apply business operation.
    }
}
```

### 20.3. Quy tắc retry đúng hơn

1. Xác định operation có thuộc nhóm driver retryable không.
2. Sử dụng driver retry semantics trước khi tự viết cơ chế riêng.
3. Với business retry, dùng idempotency key hoặc state machine.
4. Giới hạn số lần thử/thời gian theo request deadline.
5. Dùng backoff/jitter thích hợp để tránh retry storm.
6. Phân biệt lỗi vĩnh viễn như validation/duplicate key với lỗi tạm thời.
7. Ghi metrics về retry và unknown results, không chỉ log thành công.

### 20.4. Một write trả timeout nhưng có thể đã xảy ra

Nếu client nhận network timeout sau khi gửi `$inc`, không kết luận lệnh chưa chạy. Cần **đối chiếu trạng thái theo requestId** trước khi áp thêm một business increment.

## 21. Giữ thao tác nghiệp vụ idempotent

### 21.1. Đặt hàng có khóa request

```javascript
db.getSiblingDB("ops_lab_376").orders.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true }
);
```

API ghi:

```javascript
{
  _id: "O1001",
  tenantId: "T01",
  requestId: "REQ-913",
  total: 890000,
  status: "CREATED"
}
```

Khi client retry, backend có thể truy vấn theo `tenantId/requestId` để xác định request đã hoàn tất/chưa hoàn tất, tránh tạo đơn khác.

### 21.2. Reservation nhiều document

Nếu một order cần giữ 3 SKUs, phải xem:

- Atomic conditional updates từng SKU.
- Transaction hoặc reservation saga có compensation.
- Unique operation ID.
- Trạng thái pending/confirmed/released.
- Retry sau failover và xử lý kết quả chưa chắc chắn.

Một `$inc` atomic trên document inventory **không** làm toàn bộ multi-SKU reservation tự atomic.

### 21.3. Giao dịch với hệ thống ngoài MongoDB

Nếu sau khi insert order còn gửi email/charge payment:

```text
MongoDB transaction commit
      |
      v
Outbox event
      |
      v
Worker xử lý với idempotency
      |
      v
Payment/notification service
```

Không giả định retry MongoDB transaction đồng bộ với side effect bên ngoài; dùng outbox/saga khi cần.

## 22. Read preference khi có election

### 22.1. `primary`

Mặc định, MongoDB driver ưu tiên reads từ primary. Khi election đang diễn ra, reads cần primary có thể chờ hoặc thất bại tạm thời.

### 22.2. `secondary` hoặc `secondaryPreferred`

Có thể tiếp tục đọc từ secondary trong một số tình huống, nhưng:

- Secondary có thể stale.
- Khi một member bị maintenance, read capacity có thể giảm.
- `secondaryPreferred` có fallback semantics riêng; không bảo đảm tất cả reads luôn vào secondary.
- Đọc từ secondary không giải quyết việc **ghi cần primary**.

### 22.3. Không đổi read preference tùy tiện để che lỗi

Nếu ứng dụng cần read-your-writes hoặc consistency mạnh, đổi sang secondary có thể tạo bug hiển thị dữ liệu chưa đồng bộ.

### 22.4. Causal consistency

MongoDB sessions với causal consistency cùng read/write concerns phù hợp có thể hỗ trợ các quan hệ nhân quả như read-your-writes trong những điều kiện được tài liệu quy định.

Không suy rằng một request mới, một session khác và read preference secondary luôn thấy write vừa thực hiện.

## 23. Readiness và liveness của ứng dụng

### 23.1. Liveness

Trả lời: “Tiến trình Java còn chạy và có khả năng phục vụ hay không?”. Không nên giết/restart toàn bộ application mỗi khi MongoDB có election ngắn.

### 23.2. Readiness

Trả lời: “Instance có thể nhận thêm traffic cho các chức năng được yêu cầu không?”.

Nếu toàn bộ hệ thống phụ thuộc writes, readiness có thể gắn với khả năng chọn primary trong giới hạn thời gian hợp lý; nhưng cần tránh **đồng loạt loại mọi pod** khi database có vài giây election, tạo cascade failure.

### 23.3. Bảo vệ khỏi retry storm

```text
Election starts
  |
  +-> 100 service instances
       mỗi instance 1000 requests pending
          |
          v
       retry ngay cùng lúc
          |
          v
       new primary quá tải
```

Dùng bounded queues, backpressure, exponential backoff/jitter và request deadlines theo mục tiêu.

### 23.4. Degrade gracefully khi phù hợp

Một UI có thể vẫn hiển thị thông tin catalog đã cache trong lúc vài giây không ghi được, nhưng phải **thông báo rõ** đơn hàng chưa được xác nhận, không trả success giả.

## 24. Thay một secondary khỏe: phương án giảm rủi ro

Giả sử:

```text
mongo-a PRIMARY
mongo-b SECONDARY (cần thay)
mongo-c SECONDARY
```

### 24.1. Ưu tiên thêm trước, bỏ sau nếu có tài nguyên

Nếu có máy mới `mongo-d` và cấu hình cho phép, cách tiếp cận thường an toàn:

```text
1. Chuẩn bị mongo-d (TLS, DNS, network, storage).
2. Thêm mongo-d như non-voting, priority=0.
3. Cho mongo-d initial sync và bắt kịp.
4. Chuyển vai trò voting/election eligibility theo quy trình.
5. Loại mongo-b sau khi kiểm tra quorum.
6. Verify replication/app connections.
```

Điểm chính: **đừng tạo khoảng thiếu data-bearing members lâu hơn cần thiết**.

### 24.2. Khi không thể thêm trước

Một topology/license/capacity hạn chế có thể buộc phải tháo máy cũ rồi thêm máy mới. Khi đó window rủi ro lớn hơn, cần đánh giá quorum, backups và business maintenance plan.

### 24.3. Không xem “thêm node” là vô hại

Initial sync có thể gây tải network/disk trên sync source. Config reconfiguration có thể ảnh hưởng elections/quorum. Cần đo kỹ trước và trong thao tác.

## 25. `rs.add()`: thêm secondary mới

### 25.1. Chuẩn bị host

MongoDB `mongod` mới phải:

- Chạy phiên bản tương thích với replica set.
- Có đúng `replSetName`.
- Dùng internal authentication và TLS phù hợp.
- Có disk data path/permissions hợp lệ.
- Có kết nối hai chiều với những members cần thiết.
- Có cấu hình hostname/DNS ổn định.
- Không phải máy đang chạy member khác cùng identity.

### 25.2. Thêm non-voting member trong lab

Kết nối tới primary:

```javascript
rs.add({
  host: "mongo-d.example.internal:27017",
  priority: 0,
  votes: 0
});
```

Lợi ích: member mới không thay đổi voting majority ngay lúc bắt đầu initial sync và không có khả năng thành primary khi dữ liệu chưa đồng bộ xong.

### 25.3. Theo dõi tiến độ

```javascript
rs.status();
```

Quan sát:

- `STARTUP2` trong initial sync.
- `initialSyncStatus` nếu có.
- `RECOVERING` trong các giai đoạn phù hợp.
- `SECONDARY` khi hoàn tất.
- Replication lag và sync source.
- Disk, network và oplog window.

### 25.4. Chờ đủ điều kiện trước promotion

Không nâng `votes/priority` chỉ vì process đã chạy hoặc đã ping được. Đợi member hoàn thành initial sync, ổn định, bắt kịp và được monitor trong khoảng phù hợp.

## 26. Promotion một member từ non-voting thành voting

Sau khi `mongo-d` đã hoàn tất đồng bộ, có thể điều chỉnh cấu hình bằng `rs.reconfig()` trong **quy trình được phê duyệt**.

### 26.1. Ví dụ minh họa trên lab

```javascript
const cfg = rs.conf();
const newMember = cfg.members.find(
  m => m.host === "mongo-d.example.internal:27017"
);

if (!newMember) {
  throw new Error("New member not present in replica config");
}

newMember.votes = 1;
newMember.priority = 1;

rs.reconfig(cfg);
```

### 26.2. Tại sao không sửa theo index mảng cố định?

Không nên:

```javascript
// Chống chỉ định nếu chưa kiểm tra đúng member.
cfg.members[3].votes = 1;
```

Thứ tự array có thể đổi trong quá trình vận hành. Chọn member theo hostname hoặc identity đã xác minh.

### 26.3. Kiểm tra quorum khi thêm voter

Từ 3 voters sang 4 voters:

```text
Trước: 3 voters -> majority 2
Sau:   4 voters -> majority 3
```

Do đó thêm một voter có thể **tăng số phiếu cần cho majority**. Nếu một node đang DOWN, đừng chỉ thấy “có thêm voter” và kết luận availability tốt hơn.

### 26.4. Reconfiguration restrictions

MongoDB áp những giới hạn với thay đổi membership/voting để bảo vệ quorum, bao gồm quy tắc về số voting members được thêm/bớt trong một reconfiguration, commit của cấu hình và concurrency giữa các thay đổi.

Không tự sửa nhiều fields/voters cùng lúc trên production mà chưa kiểm tra quy trình của version; dùng các bước thay đổi đã được hỗ trợ.

## 27. `rs.remove()`: loại thành viên cũ

Sau khi member thay thế đã ổn định và cấu hình quorum được xác minh:

```javascript
// CHỈ TRÊN LAB/SAU CHANGE APPROVAL.
rs.remove("mongo-b.example.internal:27017");
```

### 27.1. Trước khi remove

1. Xác định member sẽ remove chính xác.
2. Đảm bảo member không phải primary cần phục vụ writes.
3. Kiểm tra member mới đã sync/bắt kịp.
4. Tính majority sau thay đổi.
5. Xác định khả năng tồn tại nếu thêm một node lỗi.
6. Kiểm tra monitoring/backup/read preference đang dùng member cũ không.
7. Duy trì cách rollback và record cấu hình.

### 27.2. Không remove primary trực tiếp khi chưa chuẩn bị

Nếu member cần bỏ vẫn là primary, hãy lập planned switchover trước. Loại primary vội có thể làm outage lớn hơn và tăng rủi ro config bất nhất.

### 27.3. Sau remove

- Dừng/hủy service của member cũ theo quy trình.
- Thu hồi certs/keys và quyền hạ tầng không cần thiết.
- Cập nhật DNS/monitoring/runbooks.
- Xác minh ứng dụng có thể kết nối qua replica set URI.
- Kiểm tra trạng thái của remaining members.

### 27.4. Không dùng remove để chữa lỗi network mơ hồ

Nếu một secondary chỉ tạm mất heartbeat, cần chẩn đoán trước. Tự loại node khỏi replica set có thể làm thay đổi majority và khiến việc quay lại phức tạp.

## 28. Ví dụ kế hoạch thay một secondary trong cụm ba voters

Ban đầu:

```text
A PRIMARY votes1
B SECONDARY votes1 (cần thay)
C SECONDARY votes1
majority=2
```

### 28.1. Trường hợp có thể tạm có bốn data-bearing members

```text
Phase 1:
A votes1, B votes1, C votes1, D votes0 priority0
majority=2
D initial sync

Phase 2:
D đã bắt kịp; promote D votes1
A votes1, B votes1, C votes1, D votes1
majority=3

Phase 3:
Remove B
A votes1, C votes1, D votes1
majority=2
```

Đây là **sơ đồ tư duy**, không phải trình tự bắt buộc cho mọi deployment. Từng thay đổi config cần xác nhận cluster khỏe và phù hợp các giới hạn reconfiguration.

### 28.2. Một khoảng thời gian majority=3

Nếu B đã DOWN ngay khi D được promote, ba members A/C/D phải đều liên lạc để đạt majority=3/4 cho tới khi remove B.

Do đó **thứ tự thay đổi phải tính theo topology thực tế**, không máy móc làm “promote rồi remove” khi đang có sự cố khác.

### 28.3. Khi thay member đã mất hẳn

Nếu B đã hỏng, A/C vẫn có majority 2/3. Thêm D nonvoting và chờ sync là một phương án; việc thay voters tiếp theo cần bảo đảm không mất quorum giữa các bước. Nếu A hoặc C tiếp tục lỗi trước khi D hoàn tất, availability có thể bị ảnh hưởng.

### 28.4. Không tự dùng `force:true` cho nhanh

`rs.reconfig(cfg, { force: true })` bỏ qua một số kiểm tra và có thể tạo đường lịch sử phải rollback trong trường hợp đặc biệt. Chỉ cân nhắc trong recovery procedure được kiểm chứng, có người chuyên trách và backup, không phải bước thường quy.

## 29. Thay primary bằng máy mới

Giả sử cần thay `mongo-a`, hiện là primary:

```text
mongo-a PRIMARY (cần thay)
mongo-b SECONDARY
mongo-c SECONDARY
mongo-d newly added
```

### 29.1. Chiến lược an toàn hơn

1. Chuẩn bị và thêm `mongo-d` như secondary nonvoting.
2. Cho D initial sync, bắt kịp, kiểm tra logs/metrics.
3. Bảo đảm B hoặc C là primary candidate khỏe.
4. Chủ động `rs.stepDown()` trên A theo change window.
5. Xác nhận primary mới B/C và writes phục hồi.
6. Bảo trì/loại A theo quy trình reconfig/quorum phù hợp.
7. Chuyển quyền vote/priority của D theo kế hoạch và theo dõi.
8. Kiểm tra ứng dụng, replication, backup, monitoring.

### 29.2. Vì sao không “tắt A rồi thêm D”?

Nếu A đang primary và B/C có lag/mạng vấn đề, tắt A ngay có thể làm election thất bại hoặc kéo dài. Thêm D trước khi tắt A tạo khả năng chuẩn bị mà không ngừng writes.

### 29.3. Nếu phải chuyển primary trước khi D được tạo?

Đảm bảo B/C đủ điều kiện và majority. Chuyển A → B/C rồi thay A như secondary. Đây là một lựa chọn tùy hạn chế hardware và rủi ro.

### 29.4. Thay host vs thay disk

Nếu cùng hostname nhưng data disk mới:

- Có thể cần initial sync lại.
- Không sao chép data directory tùy tiện khi process còn chạy.
- Xác nhận node cũ dừng và disk chứa dữ liệu cũ không bị khởi chạy song song.
- Theo quy trình MongoDB/automation/Operator cụ thể của deployment.

Nếu hostname mới, cập nhật membership bằng supported operations.

## 30. Initial sync và rủi ro ảnh hưởng hiệu năng

### 30.1. Các giai đoạn tổng quát

```text
Member joins
   |
   v
STARTUP2 / initial sync
   |
   +-- copy database contents
   +-- build indexes
   +-- fetch/apply oplog while data is copied
   |
   v
RECOVERING / catch-up
   |
   v
SECONDARY
```

Trình tự chi tiết tùy MongoDB version/initial sync method.

### 30.2. Ảnh hưởng lên sync source

Initial sync có thể tăng:

- Network transfer.
- Disk read/write IOPS.
- WiredTiger cache pressure.
- Oplog fetching.
- CPU và index build load.

### 30.3. Không initial sync nhiều members đồng thời nếu không cần

Nếu cùng lúc thay hai secondaries trong replica set ba members, vừa giảm redundancy vừa gây tải lớn. Ưu tiên thay **từng member**, đợi bắt kịp trước khi chuyển sang member tiếp theo.

### 30.4. Khi oplog window không đủ

Một initial sync quá lâu trong khi write rate cao có thể cần nhiều oplog entries hơn lịch sử hiện được giữ. Phải xem window/headroom, thay vì chỉ tăng timeout ứng dụng.

### 30.5. Theo dõi completion

```javascript
const s = rs.status();
printjson(s.members.map(m => ({
  host: m.name,
  state: m.stateStr,
  health: m.health,
  optimeDate: m.optimeDate
})));
```

Đừng coi `health:1` là bằng chứng hoàn tất initial sync; cần `SECONDARY`, lag và log/metrics phù hợp.

## 31. Rolling maintenance và rolling upgrade

### 31.1. Mục tiêu

Thay đổi OS/kernel/certificates/MongoDB binaries từng node để **giữ phần lớn replica set hoạt động** thay vì dừng tất cả cùng lúc.

### 31.2. Nguyên tắc tổng quát

1. Kiểm tra compatibility matrix của MongoDB version/FCV/driver và tooling.
2. Kiểm tra backup/PITR, quorum, replication lag.
3. Bảo trì **một secondary**.
4. Khởi động lại, đợi member trở lại `SECONDARY` và bắt kịp.
5. Lặp lại cho những secondary khác.
6. Chủ động stepdown primary nếu cần, rồi bảo trì former primary.
7. Kiểm tra topology mới và ứng dụng.
8. Chỉ nâng FCV khi đủ điều kiện theo upgrade procedure/version.

### 31.3. Trình tự primary last không phải không điều kiện

Rolling upgrade/maintenance của mỗi MongoDB version có quy định riêng, và Atlas/Operators có automation khác. Không lấy một sơ đồ chung thay tài liệu nâng cấp chính thức.

### 31.4. Không bảo trì secondary tiếp theo quá sớm

```text
B restart -> B SECONDARY nhưng lag 30 phút
C restart ngay -> chỉ A phục vụ mới nhất
```

Nếu A lỗi lúc đó, election/availability có thể rủi ro cao.

Đợi B healthy/caught up, verify majority và headroom trước khi bắt đầu C.

### 31.5. Các việc có thể làm tăng rủi ro khi upgrade

- Thay đổi FCV trước khi nâng tất cả binaries.
- Thay đổi replica set config cùng lúc upgrade.
- Cập nhật certificates không tương thích SAN/CA.
- Restart nhiều voters cùng lúc.
- Bỏ qua application compatibility tests.
- Không kiểm tra feature deprecation/removed settings.

## 32. Thay TLS certificates mà không làm rơi toàn cụm

### 32.1. Cần xác định identities

- MongoDB server certificate.
- CA trusted bởi drivers.
- Internal member-to-member certificates hoặc keyfiles.
- Credentials và role mapping nếu dùng X.509 auth.

### 32.2. Vấn đề CA rotation

Nếu application chỉ tin CA cũ còn member mới dùng CA mới, TLS handshake thất bại dù DB vẫn healthy.

### 32.3. Kế hoạch overlap trust

Một phương án tùy hạ tầng:

```text
1. Clients/members tin cả CA cũ và CA mới trong giai đoạn chuyển.
2. Rotate certificates từng member.
3. Verify TLS/replication/app connectivity.
4. Chuyển clients sang CA mới.
5. Thu hồi CA cũ sau khi mọi consumer đã đổi.
```

Cơ chế cụ thể phụ thuộc TLS/certificate handling của MongoDB và deployment; không áp dụng tùy tiện nếu platform yêu cầu trình tự khác.

### 32.4. Không sửa bằng `tlsAllowInvalidCertificates`

Việc bỏ xác minh cert khiến kết nối có thể bị mạo danh. Sửa chain, SAN, CA trust và hostnames đúng nguồn.

## 33. Atlas: switchover và thay node được quản lý

MongoDB Atlas quản lý nhiều thao tác hạ tầng/elections/rolling restarts. Khả năng thực hiện một hành động như Test Failover, restart, scaling hoặc maintenance tùy cluster tier và giao diện ở thời điểm dùng.

### 33.1. Điều khác với self-managed

- Không điều khiển trực tiếp mọi host process.
- Một số lệnh `rs.reconfig()`/`rs.stepDown()` có thể bị giới hạn.
- Node replacement, certificates, rolling changes có cơ chế managed.
- Monitoring/alerts dùng Atlas metrics và activity logs.

### 33.2. Không áp runbook `rs.remove()` self-managed lên Atlas

Atlas có control-plane automation riêng; thay node bằng công cụ được Atlas hỗ trợ, không cố sửa replica set membership thủ công.

### 33.3. Khả năng gián đoạn vẫn tồn tại

Dù cluster managed, ứng dụng vẫn cần correct URI/driver version/retries/idempotency và điều chỉnh timeout theo SLO.

### 33.4. Dùng Test Failover có kiểm soát

Khi môi trường/tier hỗ trợ, một test failover có thể giúp kiểm tra:

- Tốc độ ứng dụng phát hiện primary mới.
- Server selection và retry behavior.
- Transaction errors.
- Hành vi frontend khi request đang chạy.
- Alert/dashboard.

Test phải có approval và tác động dự kiến, không phải thao tác “không có rủi ro”.

## 34. Sharded cluster: `mongos`, shard replica sets và config servers

### 34.1. Kiến trúc

```text
Java app
   |
   v
mongos routers
   |
   +-- Shard-A replica set
   |      A-P, A-S1, A-S2
   |
   +-- Shard-B replica set
   |      B-P, B-S1, B-S2
   |
   +-- Config-server replica set
          C-P, C-S1, C-S2
```

### 34.2. Switchover của một shard

Primary thay đổi trong shard A không nhất thiết làm shard B mất primary. Tuy nhiên query hoặc transaction xuyên shards có thể bị ảnh hưởng.

### 34.3. Không bypass `mongos`

Ứng dụng sharded cluster thông thường kết nối tới `mongos` routers, không tùy ý kết nối trực tiếp shard member để né sự cố primary.

### 34.4. Config server replica set cũng cần quorum

Config servers giữ metadata phân mảnh quan trọng. Bảo trì các nodes này cần runbook riêng, không xem chúng chỉ là secondary “không chứa dữ liệu” hoặc bỏ qua topology.

### 34.5. Quorum mỗi replica set là riêng

Không tính tổng phiếu của shard A, shard B và config server thành một quorum duy nhất. Mỗi replica set có voting majority riêng.

## 35. Kịch bản một region bị mất

Giả sử ba members phân bố:

```text
Region A: PRIMARY + SECONDARY
Region B: SECONDARY
```

Nếu region A mất, chỉ còn một vote ở region B ⇒ không đủ majority cho replica set ba voters.

### 35.1. Multi-region không tự bảo đảm region-failover

Availability phụ thuộc phân bố voters giữa failure domains, network partition, write concern và topology.

### 35.2. Một thiết kế ba regions

```text
Region A: voter1
Region B: voter2
Region C: voter3
```

Mất một region còn hai votes, nhưng latency/quorum giữa regions và primary placement cũng cần xem.

### 35.3. Không tạo một arbiter trong region xa chỉ để “đủ ba”

Arbiter có thể làm election đủ phiếu nhưng không bổ sung bản sao dữ liệu hay đáp ứng backup; kiến trúc cần được đánh giá theo RPO/RTO và data residency.

## 36. Thiết kế metrics và alert cho các lần chuyển primary

| Metric/alert | Câu hỏi trả lời |
|---|---|
| Primary availability | Có primary writable không? |
| Election count/reasons | Có failover quá thường xuyên không? |
| Replica member state | Có node DOWN/RECOVERING/ROLLBACK không? |
| Replication lag | Candidate đã bắt kịp chưa? |
| Oplog window/headroom | Node đang offline còn đủ lịch sử để trở lại không? |
| Majority commit point | Writes được majority acknowledged tới đâu? |
| Driver server-selection errors | Client không tìm được primary trong bao lâu? |
| Driver connection pool | Pool có bị cạn hoặc reconnect storm không? |
| Retry count/error labels | Retry có tăng khi election không? |
| API HTTP 5xx/latency | Người dùng có bị gián đoạn không? |
| Transaction abort/retry | Nghiệp vụ có cần reconcile không? |
| Change stream resume failures | CDC có theo kịp không? |
| Disk/network/CPU | Có bottleneck cản initial sync không? |

### 36.1. Dashboard trước/sau bảo trì

```text
T-10 min: baseline requests/sec, p95, write errors, lag
T0:      operator triggers planned switchover
T+...:   election, term changes, new primary observed
T+...:   driver topology updated; errors/retries settle
T+10m:   verify secondary health, lag, SLO
```

Đặt cùng một timeline cho **MongoDB events** và **application metrics** để phân biệt election time với client recovery time.

### 36.2. Không gộp mất metrics thành zero

Nếu monitoring không nhận dữ liệu `rs.status()` từ node bị ngắt, không ghi lag = 0. Đặt trạng thái unknown/missing và alert riêng cho availability.

### 36.3. Đo thời gian gián đoạn thật

Một metric “election completed in 4 seconds” không chứng minh mọi service đã hoạt động trở lại ở giây thứ tư. Cần đo **end-to-end time-to-success** của các writes API hợp lệ.

## 37. Runbook A — Chuyển primary phục vụ bảo trì

### Preconditions

- Change ticket, owner, maintenance window và rollback.
- Backup/PITR hoặc recovery plan phù hợp.
- Primary hiện tại xác định.
- Có ≥1 candidate khỏe/electable/caught up.
- Đủ majority ngay cả khi former primary tạm dừng.
- Driver/clients có topology discovery và retry.
- Không có sự cố replication/network đang mở.

### Thao tác

```text
1. Thu baseline metrics và config.
2. Thông báo người quản trị API/CDC/reporting.
3. Kiểm tra lag/headroom của candidates.
4. Chủ động stepDown theo quy trình.
5. Reconnect qua replica set URI.
6. Xác nhận primary mới.
7. Test majority write và application paths.
8. Theo dõi former primary thành SECONDARY.
9. Bảo trì former primary.
10. Theo dõi và đóng change khi mọi SLO trở lại.
```

### Stop conditions

**Dừng/hoãn** nếu:

- Candidate chậm hoặc không còn electable.
- Quorum có rủi ro.
- Đang rollback/initial sync/RECOVERING bất thường.
- Network/TLS/DNS lỗi.
- Backup/checkpoint không có hoặc không đủ điều kiện.
- Chưa rõ cách ứng dụng xử lý writes chưa chắc chắn.

## 38. Runbook B — Thay secondary với hostname mới

### Preconditions

- Chuẩn bị `mongo-d` với version/replSetName/network/cert.
- Xác nhận disk capacity cho full initial sync.
- Xác nhận primary và members hiện tại khỏe.
- Xem write throughput/oplog window.

### Thao tác

```text
1. Add D non-voting, priority 0.
2. Monitor initial sync.
3. Confirm D SECONDARY and caught up.
4. Plan voter/priority transition based on quorum.
5. Reconfig stepwise, verify each step.
6. Remove B after D is usable and quorum safe.
7. Decommission B and revoke secrets.
8. Verify all members and application discovery.
```

### Lỗi thường gặp

- Hostname D không resolvable từ app.
- SAN certificate không phù hợp.
- D có `replSetName` sai.
- D không đủ disk.
- Chuyển votes quá sớm.
- Remove B khi một member khác vẫn DOWN.
- Không kiểm tra backup/read workloads đang phụ thuộc B.

## 39. Runbook C — Primary chết bất ngờ

### Bước 1: không can thiệp tùy tiện

Đợi/quan sát election tự động trong khoảng SLO trước khi quyết định thao tác khẩn, trừ khi có dấu hiệu sự cố nghiêm trọng đã được xác nhận.

### Bước 2: xác định quorum

Xem:

- Những voting members còn reachable.
- Member nào là candidate hợp lệ.
- Có primary mới chưa.
- Có network partition giữa các zones không.

### Bước 3: application impact

Đo:

- API write errors, server selection timeouts.
- Transaction failures.
- Unknown outcomes cần reconcile.
- CDC consumers và read staleness.

### Bước 4: primary cũ quay lại

Xác minh nó tái nhập với role hợp lệ, replication/rollback logs và disk. Không tự ép nó thành primary chỉ vì trước đây nó là primary.

### Bước 5: phân tích nguyên nhân

Node crash, disk, CPU, DNS/TLS, heartbeat, network partition, operator change hay quá tải đều có thể gây failover.

## 40. Runbook D — Không có primary vì mất majority

```text
Replica set: 3 voters
Healthy reachable: 1
Primary: none
```

### Điều nên làm

1. Xác định lỗi network hay host.
2. Khôi phục khả năng liên lạc với những voting members đã tồn tại.
3. Kiểm tra disk/auth/TLS/OS và logs.
4. Bảo toàn dữ liệu/không khởi chạy song song identity trùng.
5. Có evidence về optime/majority commit trước khi chọn recovery path.
6. Dùng MongoDB-supported disaster recovery procedure nếu thực sự không thể khôi phục majority.

### Điều không nên làm

- Không `rs.reconfig(...,{force:true})` chỉ vì muốn có primary ngay.
- Không loại mọi unavailable members bằng một vòng lặp.
- Không chạy `rs.initiate()` lại trên dữ liệu cũ.
- Không xóa data files để “reset cluster”.

Các thao tác trên có thể dẫn tới divergence/rollback hoặc hỏng cơ chế phục hồi, cần người có kinh nghiệm và kế hoạch rõ.

## 41. Runbook E — Member mới không hoàn tất initial sync

### Những kiểm tra chính

```javascript
rs.status();
db.getReplicationInfo();
```

Kèm:

- Logs `initialSyncStatus`/errors.
- Network throughput và TLS.
- Disk capacity/I/O latency.
- Source member load.
- Oplog window so với thời gian clone.
- Index build errors.

### Hướng xử lý

Khắc phục nguyên nhân, điều chỉnh capacity/maintenance nếu phù hợp và làm theo quy trình retry/resync của version. Không vội tăng size oplog hoặc restart liên tục khi chưa hiểu vì sao initial sync thất bại.

## 42. Runbook F — Ứng dụng còn lỗi sau khi đã có primary mới

### 42.1. Cần phân biệt lỗi database và driver

Đã có primary mới nhưng Java vẫn báo `serverSelectionTimeout` có thể do:

- URI dùng `directConnection=true` tới primary cũ.
- DNS/SRV không resolve host mới.
- TLS CA/SAN sai.
- Network/firewall không mở tới member mới.
- Driver version cũ/connection pool unhealthy.
- Auth mechanism hoặc credentials khác giữa nodes.
- Application instances chưa refresh hoặc có retry storm.

### 42.2. Checklist điều tra

1. Xác minh `rs.status()` từ cluster.
2. Kiểm tra `rs.conf().members[].host`.
3. Kiểm tra DNS/TLS từ application hosts.
4. Kiểm tra driver SDAM/server-selection logs đã redact.
5. Kiểm tra pool size, waiting requests và reconnect rate.
6. So sánh traffic theo từng app instance.
7. Chạy test có phân quyền từ một instance lab/diagnostic.
8. Không in password/URI raw ra log khi debug.

### 42.3. Không sửa bằng cách restart tất cả services ngay

Restart đồng loạt có thể tạo connection storm, làm primary mới quá tải. Nếu cần rollout, dùng batch/rolling application restart với capacity và connection backoff.

## 43. `rs.freeze()` và `rs.stepUp()`: công cụ điều khiển có giới hạn

### 43.1. Freeze một secondary

Trong một số tình huống vận hành, `rs.freeze(seconds)` trên secondary có thể ngăn thành viên ứng cử primary trong khoảng thời gian đặt.

```javascript
// CHỈ trong lab được phép, trên secondary phù hợp.
rs.freeze(60);
```

`rs.freeze(0)` có thể bỏ freeze theo semantics được hỗ trợ.

### 43.2. Freeze không phải bảo đảm quorum

Nếu freeze hết các candidates rồi stepdown primary, bạn có thể làm failover không xảy ra. Không dùng freeze như phương án “giữ cluster yên” mà không tính votes/priority/eligibility.

### 43.3. StepUp

Một số phiên bản/công cụ MongoDB có `replSetStepUp`/shell helper tương ứng để đề nghị secondary trở thành primary. Yêu cầu chỉ có thể thành công khi member đủ điều kiện và có quorum.

Việc ép một member cụ thể làm primary **không** nên là mặc định; bình thường hãy để election/priority quyết định sau preflight.

### 43.4. Tránh thao tác không cần thiết

Một planned switchover thường không cần vừa sửa priority, vừa freeze, vừa stepUp và stepDown cùng lúc. Càng nhiều thay đổi topology đồng thời, càng khó hiểu kết quả/rollback.

## 44. Đánh giá tác động trước khi đổi votes/priority

### 44.1. Bảng tình huống

| Thao tác | Quorum có thể thay đổi? | Ứng viên primary có thể thay đổi? | Cần lưu ý |
|---|---|---|---|
| `rs.stepDown()` | Không trực tiếp đổi số voters | Có, do election | Gián đoạn writes tạm thời |
| Thêm non-voting secondary | Không đổi voting count | Chưa | Initial sync tải tài nguyên |
| Promote non-voter thành voter | Có | Có nếu priority > 0 | Tính majority mới |
| Đổi priority | Không tự đổi số votes | Có | Có thể kích hoạt election |
| Remove voting secondary | Có | Có thể | Mất redundancy tạm |
| Remove primary | Có/thay role | Có | Rủi ro cao, cần switchover trước |
| Force reconfig | Có thể | Có thể | Chỉ cho recovery đặc biệt |

### 44.2. Cấu hình phải được commit

MongoDB có các bước/điều kiện để xác nhận replica set reconfiguration. Không thực hiện reconfig tiếp theo ngay khi chưa xác định cấu hình trước đã được áp dụng/commit theo cơ chế của version.

### 44.3. Không tạo “quorum giả”

Thêm nhiều arbiters hoặc voters ở cùng một máy/hạ tầng mất chung nguồn điện không thực sự tăng resilience tương ứng; phải xét **failure domains** chứ không chỉ đếm số node.

## 45. Bài lab an toàn: quan sát trước khi thay đổi

### 45.1. Tạo dữ liệu độc lập

Trong replica set lab, sau khi xác nhận namespace chưa có dữ liệu:

```javascript
const lab = db.getSiblingDB("ops_lab_376");
const orders = lab.orders;

if (orders.countDocuments({}) !== 0) {
  throw new Error("Lab collection not empty; choose a new namespace");
}

orders.insertMany([
  {
    _id: "O376-1",
    tenantId: "T01",
    status: "CREATED",
    createdAt: new Date()
  },
  {
    _id: "O376-2",
    tenantId: "T01",
    status: "CREATED",
    createdAt: new Date()
  }
]);
```

Không dùng `drop()`/`deleteMany({})` trên production để “dọn lab” khi chưa biết namespace có chứa dữ liệu gì.

### 45.2. Ghi trạng thái trước

```javascript
const before = rs.status();
printjson(before.members.map(m => ({
  host: m.name,
  state: m.stateStr,
  health: m.health,
  optimeDate: m.optimeDate
})));
```

### 45.3. Xem voting config

```javascript
const cfg = rs.conf();
printjson(cfg.members.map(m => ({
  host: m.host,
  votes: m.votes,
  priority: m.priority
})));
```

### 45.4. Tính lag đơn giản

```javascript
const s = rs.status();
const p = s.members.find(m => m.stateStr === "PRIMARY");

if (!p || !(p.optimeDate instanceof Date)) {
  print("PRIMARY_UNKNOWN");
} else {
  const lag = s.members.map(m => ({
    host: m.name,
    state: m.stateStr,
    lagSeconds:
      m.stateStr === "SECONDARY" &&
      m.optimeDate instanceof Date
        ? (p.optimeDate.getTime() -
           m.optimeDate.getTime()) / 1000
        : null
  }));

  printjson(lag);
}
```

Không tính lag cho arbiter và không ép null thành 0.

### 45.5. Xem oplog window

```javascript
printjson(db.getReplicationInfo());
```

Đây là window của member đang kết nối, không phải toàn cụm.

### 45.6. Thử nghiệm planned switchover

Chỉ khi đã kiểm tra quorum, ứng viên và có phép trên lab:

```javascript
// Lệnh làm thay đổi primary; không chạy trên production tự ý.
rs.stepDown(60, 15);
```

Sau đó reconnect bằng replica set URI, xác minh primary mới và ứng dụng. Nếu lệnh trả connection error, đừng tự lặp lại ngay; xem trạng thái thực.

## 46. Một script mongosh chỉ đọc để quan sát membership

```javascript
function replicaView376() {
  const status = rs.status();
  const conf = rs.conf();
  const configByHost = new Map(
    conf.members.map(m => [m.host, m])
  );

  const primary = status.members.find(
    m => m.stateStr === "PRIMARY");
  const primaryMs =
    primary?.optimeDate instanceof Date
      ? primary.optimeDate.getTime()
      : null;

  return {
    sampledAt: new Date(),
    replicaSet: status.set,
    term: status.term ?? null,
    members: status.members.map(m => {
      const c = configByHost.get(m.name);
      const appliedMs =
        m.optimeDate instanceof Date
          ? m.optimeDate.getTime()
          : null;

      return {
        host: m.name,
        state: m.stateStr,
        health: m.health,
        votes: c?.votes ?? null,
        priority: c?.priority ?? null,
        syncSourceHost: m.syncSourceHost ?? null,
        lagSeconds:
          m.stateStr === "SECONDARY" &&
          primaryMs !== null &&
          appliedMs !== null
            ? (primaryMs - appliedMs) / 1000
            : null
      };
    })
  };
}

printjson(replicaView376());
```

### 46.1. Giới hạn

- Một snapshot từ member đang được hỏi.
- Member state/optime có thể chưa đồng thời.
- Thiếu field có thể do version hoặc trạng thái.
- Không quyết định election chỉ từ bảng này.
- Không thay thế metrics liên tục hoặc quorum check.

## 47. Checklist giảm gián đoạn trong Java/Spring Boot

### 47.1. Connection management

- Dùng một `MongoClient` sống lâu, pool được cấu hình.
- URI chứa replica set seeds hoặc Atlas SRV.
- Không dùng `directConnection=true` cho primary-dependent app.
- DNS/TLS có thể truy cập mọi member được công bố.
- Không hardcode host primary trong business code.

### 47.2. Retry và correctness

- Bật retryable writes/reads khi phù hợp.
- Có idempotency key ở API/order/payment flows.
- Có bounded retries và deadline.
- Xử lý transaction retry/unknown commit theo driver.
- Không nuốt exception rồi trả success giả.
- Có reconciliation cho kết quả chưa chắc chắn.

### 47.3. Availability

- Health probes không làm restart storm.
- Connection pool và backpressure đã đo.
- Có degradation path cho reads không quan trọng.
- Alert user-visible failures, không chỉ database state.
- Có test failover trong staging.

### 47.4. Security

- Credentials và TLS CA quản lý an toàn.
- Không in raw connection strings/query chứa PII.
- MongoDB user quyền tối thiểu.
- Diagnostics endpoint không lộ topology.

## 48. Sự cố giả lập: primary chuyển nhưng đơn hàng bị nhân đôi

### 48.1. Timeline

```text
10:00:00  Client gửi POST /orders với cart X
10:00:01  Backend insert O1 thành công
10:00:01  Primary stepdown; HTTP response bị mất
10:00:03  Client retry POST /orders
10:00:04  Backend tạo O2 từ cùng cart X
```

### 48.2. Root cause

Ứng dụng không nhận diện hai HTTP requests là **cùng một ý định nghiệp vụ**.

### 48.3. Cách xử lý

1. Client gửi idempotency key ổn định cho checkout request.
2. Backend unique-index key theo tenant/customer scope phù hợp.
3. Khi duplicate request, truy vấn trạng thái order gốc.
4. Thanh toán/giữ tồn kho dùng protocol tránh double side effect.
5. Response chỉ success khi business state được xác nhận.

### 48.4. Tại sao driver retryWrites không đủ?

Vì lệnh insert thứ hai từ một HTTP request mới có thể tạo ID mới. Driver chỉ thấy hai database operations khác nhau, không có căn cứ để biết chúng cùng đại diện một lần checkout.

## 49. Sự cố giả lập: member mới khỏe nhưng clients không kết nối được

### 49.1. Timeline

```text
mongo-d:
  state=PRIMARY
  health=1

Java service:
  server selection timeout
  TLS hostname mismatch
```

### 49.2. Giải thích

MongoDB cluster có thể bầu primary mới nhưng application environment **không tin certificate hoặc không reach được hostname của member đó**.

### 49.3. Biện pháp

- Xem `rs.conf().members[].host`.
- Kiểm tra DNS từ pod/VM ứng dụng.
- Kiểm tra TLS SAN/CA trust.
- Kiểm tra firewall/private endpoints.
- Xem driver topology logs đã redact.
- Kiểm tra secrets/auth.

Không giảm TLS validation để chữa lỗi tức thời.

## 50. Sự cố giả lập: secondary bị too stale sau bảo trì

### 50.1. Tình huống

```text
Secondary B offline 6h.
Trong lúc đó write rate tăng.
Sync source oplog window co còn 3h.
```

Khi B quay lại, oplog entries nó cần có thể đã bị truncate.

### 50.2. Hậu quả

B có thể báo lỗi too stale/RECOVERING và không thể tiếp tục incremental replication. Cần initial sync/resync theo quy trình của deployment.

### 50.3. Bài học vận hành

Mọi rolling maintenance phải kiểm tra oplog window/headroom **trước, trong và sau**. Không chỉ xem bảo trì mất bao nhiêu giờ trên lịch.

## 51. Sự cố giả lập: mất quorum trong lúc thay node

### 51.1. Tình huống

```text
rsShop có 3 voters:
  A PRIMARY
  B SECONDARY (đang bảo trì)
  C SECONDARY

Trong lúc B offline, C mất mạng.
Chỉ A còn kết nối.
```

### 51.2. Kết quả

Không còn majority 2/3. Primary có thể step down vì không còn giữ đủ điều kiện phục vụ writes theo topology.

### 51.3. Phương án tốt hơn

- Chỉ bảo trì một member tại một thời điểm.
- Đảm bảo member trước đã quay lại và bắt kịp trước lượt tiếp theo.
- Theo dõi quorum real-time và có stop condition.
- Tách hạ tầng voters qua failure domains.
- Không vội force reconfig khi mất quorum.

## 52. Sự cố giả lập: hạ write concern để “giữ tốc độ”

### 52.1. Tình huống

Sau stepdown, ứng dụng thấy `w:"majority"` tăng latency nên hạ thành `w:1` mà không đánh giá RPO.

### 52.2. Hệ quả

Writes được ack sớm hơn có thể chưa đạt majority. Nếu primary mất trong thời điểm bất lợi, rủi ro rollback tăng.

### 52.3. Cách quyết định

Không đổi consistency/durability guarantees như một thao tác performance tuning khẩn cấp mà không có business approval. Phân tích secondary apply, network, flow control và workload trước.

## 53. Những anti-pattern cần tránh

| Anti-pattern | Hậu quả | Cách thay thế |
|---|---|---|
| Tắt primary trước khi kiểm tra secondary | Election có thể thất bại | Preflight/quorum/candidate |
| Dùng `rs.stepDown(..., force)` vô điều kiện | Có thể mất availability/write safety | Non-force planned switchover |
| Hardcode primary IP trong Java | Mất kết nối sau failover | Replica set/SRV URI |
| Dùng `directConnection=true` trong API | Không discovery đầy đủ | Driver topology mode |
| Chỉ có một seed host không reachable dài hạn | Bootstrap/recovery kém | Nhiều seeds/SRV và DNS đúng |
| Tắt TLS validation khi đổi host | Mạo danh/MITM | Sửa CA/SAN/DNS |
| Coi `health=1` là data caught up | Promote node chậm | Kiểm tra optime/lag |
| Thêm node voting trước khi sync | Election/quorum rủi ro | Thêm non-voter trước |
| Thay 2 secondaries cùng lúc | Giảm redundancy/quorum | Rolling từng member |
| Promote mới nhưng không tính majority | Quorum có thể tăng | Tính votes trước/sau |
| Remove member theo index mảng | Xóa nhầm member | Chọn đúng host/ID |
| Force reconfig để hết alert | Rủi ro divergence/rollback | Recovery runbook có chuyên gia |
| Coi arbiter là bản sao dữ liệu | Đánh giá sai redundancy | Data-bearing members |
| Ignoring delayed/hidden roles | Chọn candidate sai | Xem votes/priority |
| Tăng timeout vô hạn | Request treo, backlog | Bounded deadline/backpressure |
| Retry mọi exception vô hạn | Retry storm/double writes | Driver eligibility + idempotency |
| Retry `$inc` như command nghiệp vụ mới | Double increment | Operation ID/protocol |
| Không xử lý transaction retry | Error/sai business flow | Driver transaction semantics |
| Đặt side effect ngoài DB trong callback retry | Gửi lặp email/charge | Outbox/idempotency |
| Đọc secondary rồi coi luôn mới nhất | Stale reads | Read preference/consistency |
| Xem election done là app recovered | Client vẫn lỗi | End-to-end SLO |
| Restart toàn bộ app khi election ngắn | Connection storm | Health probe hợp lý |
| Không xem oplog window khi bảo trì | Too stale | Monitor headroom |
| Chỉ xem average lag | Che một member quá chậm | Per-member metrics |
| Bỏ qua config server trong sharding | Sự cố metadata | Runbook riêng |
| Thay cert mọi node cùng lúc | Cluster TLS break | Staged rotation |
| Đổi FCV trước khi upgrade đúng trình tự | Incompatibility | Version-specific rolling upgrade |
| Không kiểm tra rollback sau election | Bỏ qua data risks | Write concern/optime/logs |
| Coi replica set thay backup | Xóa nhầm replication theo | Backup/PITR, restore drills |

## 54. Bài tập thực hành

### Bài 1 — Majority

Với replica set có 3, 4, 5 và 7 voting members, tính majority và số voters tối đa có thể mất mà vẫn duy trì majority.

### Bài 2 — Chọn candidate

Replica set:

```text
A PRIMARY votes1 priority1
B SECONDARY votes1 priority1 lag2s
C SECONDARY votes1 priority0 lag0s
```

Nếu A stepdown, B hay C có thể ứng cử? Vì sao lag thấp hơn không tự đủ điều kiện?

### Bài 3 — Dự đoán gián đoạn

Ứng dụng có serverSelectionTimeout 2 giây nhưng election trong lab thường kéo dài hơn. Khi nào application sẽ báo lỗi dù replica set có thể phục hồi? Cần thiết kế SLO và retry budget ra sao?

### Bài 4 — Đọc `rs.status()`

Viết mongosh script trả host, `stateStr`, `health`, `optimeDate`, `syncSourceHost`. Tại sao không coi member DOWN là lag=0?

### Bài 5 — Optime

Primary/secondary có last applied oplog time đều là 10:00, wall clock hiện tại 11:30. Replication lag có bằng 90 phút không?

### Bài 6 — Planned switchover

Viết checklist trước/sau khi gọi `rs.stepDown(60,15)`. Những bước nào chỉ đọc và bước nào làm thay đổi primary?

### Bài 7 — Connection error

Sau `rs.stepDown()`, mongosh báo connection reset. Phải xác minh điều gì trước khi retry lệnh?

### Bài 8 — Force vs non-force

Một operator đề xuất `force:true` vì secondary còn lag 10 phút. Phân tích rủi ro về durability/rollback và hành động thay thế.

### Bài 9 — Thay secondary

Thiết kế các bước thay `mongo-b` bằng `mongo-d`: add non-voter, initial sync, promote, remove, verify. Ở bước nào majority đổi từ 2/3 sang 3/4?

### Bài 10 — Voting changes

Một cụm có 4 voters, một node DOWN. Majority hiện tại là bao nhiêu? Nếu thêm voter thứ năm, majority mới là bao nhiêu? Vì sao phải tính cả trạng thái thực tế?

### Bài 11 — Hidden secondary

Member hidden có `priority:0` và lag 0. Có nên chọn nó làm primary trong planned switchover? Nêu thay đổi nào cần xét và vì sao không nên làm trong lúc sự cố.

### Bài 12 — Initial sync

Member mới ở `STARTUP2` ba giờ, oplog window giảm từ 12 giờ xuống 4 giờ. Hãy thiết kế cảnh báo và điều tra network/disk/write throughput.

### Bài 13 — Oplog retention

Secondary offline 5 giờ nhưng oplog window chỉ 2 giờ. Khi quay lại có thể gặp điều gì? Tại sao tăng server selection timeout trên Java không giải quyết?

### Bài 14 — DNS/TLS

Primary mới có hostname chưa trong certificate SAN. Driver báo TLS hostname verification failure. Nêu đúng các bước sửa, và giải thích vì sao không dùng tlsAllowInvalidHostnames.

### Bài 15 — Java SDAM

Giải thích driver tìm primary qua replica set membership/hello. So sánh replica set URI với `directConnection=true` khi primary thay đổi.

### Bài 16 — Retryable writes

So sánh driver retry cùng một write với client HTTP gửi lại `POST /orders`. Vì sao trường hợp sau cần idempotency key?

### Bài 17 — Unknown write outcome

Một `updateOne` tăng `available` trả network timeout. Có thể khẳng định chưa cập nhật không? Thiết kế cách đối chiếu bằng operation ID.

### Bài 18 — Transactions

Transaction gồm ba updates và một callback gửi email. Vì sao callback có thể gây duplicate email khi retry? Đề xuất outbox pattern.

### Bài 19 — Read staleness

Sau switchover, ứng dụng chuyển đọc sang secondary để giảm lỗi. Nêu rủi ro read-your-writes và những lựa chọn về session, read preference và read concern.

### Bài 20 — Readiness probes

Một Kubernetes deployment tự restart tất cả 200 pods khi server selection thất bại trong 3 giây. Vì sao điều này có thể làm outage nặng hơn? Đề xuất probe/backoff hợp lý.

### Bài 21 — Rolling maintenance

Cụm A primary, B/C secondary. Viết runbook restart B, đợi B caught up, restart C, sau đó planned stepdown A để bảo trì A.

### Bài 22 — Thay certificate

Thay CA cho replica set gồm ba members và Java clients. Viết kế hoạch overlap trust, staged rollout, rollback và kiểm tra TLS.

### Bài 23 — Multi-region

Ba voting members nằm trong hai regions: region A có hai, region B có một. Khi region A mất, có primary mới ở region B không? Thiết kế lại để đáp ứng mục tiêu region failure như thế nào?

### Bài 24 — Sharded cluster

Phân biệt switchover primary của một shard replica set với lỗi `mongos` hoặc config server replica set. Có được gộp votes của các shards để tính majority không?

### Bài 25 — Monitoring

Thiết kế dashboard theo timeline gồm election events, primary availability, retry/error rate của Java, p95 latency, replication lag, oplog headroom và CDC resume errors.

### Bài 26 — Atlas

Một Atlas cluster cho phép test failover theo tier. Hãy liệt kê những điều nên thử từ phía application, cùng stop conditions và người phê duyệt.

### Bài 27 — Không đủ majority

Một replica set ba voters chỉ còn một member reachable. Viết incident response an toàn, nêu vì sao force reconfig không phải bước đầu tiên.

### Bài 28 — Thay primary thật

Giả sử A đang primary phải tháo phần cứng, B/C đang healthy và D mới đã đồng bộ. Viết kế hoạch switchover, promote/remove stepwise, rollback và validation.

### Bài 29 — Write concern

So sánh `w:1` và `w:"majority"` khi primary bị mất ngay sau write. Một write concern timeout có nghĩa write chưa được thực hiện hay không?

### Bài 30 — End-to-end chaos test

Trong staging có quyền, xây test plan:

1. Chạy read/write workload với business request IDs.
2. Thu baseline SLO.
3. Thực hiện planned switchover.
4. Đo errors/retries/latency.
5. Kiểm tra không có duplicate orders.
6. Kiểm tra replication và CDC recovery.
7. Ghi giới hạn quan sát và lessons learned.

Không áp phép thử phá vỡ primary lên production khi chưa có phê duyệt.

## 55. Quy trình ra quyết định khi có yêu cầu bảo trì

### Bước 1 — Xác định mục tiêu

```text
Đổi primary vì bảo trì OS?
Thay disk?
Nâng binary MongoDB?
Thay node down?
Xử lý mất quorum?
Thay certificate?
```

Mỗi mục tiêu có runbook khác nhau. **Đừng chọn `rs.reconfig()` là câu trả lời chung cho mọi tình huống.**

### Bước 2 — Chụp topology thật

Thu `rs.status()`, `rs.conf()`, lag, oplog window, voting majority, primary location, ứng viên và network.

### Bước 3 — Bảo vệ dữ liệu

Kiểm tra majority write concerns, backup/PITR, rollback risk và những business transactions có thể đang chạy.

### Bước 4 — Bảo vệ ứng dụng

Kiểm tra driver/SRV/seeds, TLS/DNS, retries, idempotency, application deadlines và metrics.

### Bước 5 — Chọn trình tự

- Chỉ đổi primary: preflight → stepdown → verify.
- Thay secondary: add nonvoting → initial sync → vote transition → remove old.
- Thay primary: chuẩn bị member/candidate → switchover → maintenance/removal.
- Rolling upgrade: từng secondary → switchover → old primary, theo procedure của version.
- Mất quorum: ưu tiên khôi phục connectivity/data-bearing members, không force reconfig tùy tiện.

### Bước 6 — Xác minh giữa từng bước

Không chỉ xác minh lệnh trả `ok:1`. Phải xem cluster state, quorum, lag, application errors và dữ liệu.

### Bước 7 — Đóng change

Ghi:

- Primary trước/sau.
- Membership/votes/priority sau thay đổi.
- Thời gian election/client recovery.
- SLO/errors/retries.
- Backup/rollback evidence.
- Những điểm cần cải thiện lần sau.

## 56. Checklist chuẩn bị triển khai production

### 56.1. Replica set

1. Tất cả voting members và quorum được xác định.
2. Có primary candidate khỏe và electable.
3. Replication lag/headroom đáp ứng maintenance window.
4. Không có initial sync/RECOVERING/ROLLBACK chưa điều tra.
5. Có backup/PITR và quy trình phục hồi.
6. Các member có version/FCV/certificates tương thích.
7. Có stop condition trước khi ảnh hưởng quorum.
8. Có rollback được thiết kế cho trường hợp ứng dụng tiếp tục ghi.

### 56.2. Ứng dụng

1. URI replica set/SRV, không hardcode primary.
2. Driver/monitoring hỗ trợ phát hiện topology.
3. TLS/DNS của mọi member đã được kiểm tra.
4. Retryable writes/reads đúng điều kiện.
5. Business idempotency và transaction retry.
6. Bounded connection pools/retry budgets.
7. Health checks không tạo restart storm.
8. Có cảnh báo user-visible failures và CDC consumers.

### 56.3. Sau thay đổi

1. Có đúng primary theo cấu hình/election hợp lệ.
2. Majority votes còn ổn.
3. Các members mong đợi đều healthy.
4. Replication lag/headroom trở về baseline.
5. Không có rollback/data divergence bất thường.
6. Application writes/reads thành công.
7. Duplicate/unknown business operations được reconcile.
8. Config, DNS, monitoring và runbooks đã được cập nhật.

## 57. Tổng kết

**Chuyển primary có kế hoạch là một quy trình vận hành, không phải chỉ một lệnh `rs.stepDown()`.** Trước khi chuyển cần kiểm tra quorum, member state, replication lag, oplog window và khả năng ứng cử. Sau khi chuyển cần xác nhận election, primary mới, sự trở lại của former primary và chất lượng phục vụ từ ứng dụng.

**Thay thành viên an toàn cần giữ redundancy qua từng bước.** Với tài nguyên cho phép, thêm member mới dưới dạng non-voting/priority 0, đợi initial sync và bắt kịp, rồi thay đổi quyền vote/priority theo các giới hạn reconfiguration trước khi bỏ member cũ. Phải tính majority sau **mỗi bước**, không chỉ ở trạng thái cuối.

**Giảm gián đoạn kết nối phụ thuộc nhiều vào phía client.** Java MongoDB driver cần kết nối bằng replica set URI/SRV, xác minh DNS/TLS cho tất cả hosts được công bố, dùng connection pool ổn định và retry các operations đủ điều kiện. Với orders, payments hoặc inventory, **application idempotency** vẫn bắt buộc để tránh lặp nghiệp vụ khi HTTP request hoặc transaction callback được thực hiện lại.

**Không đánh đổi consistency lấy cảm giác hệ thống “đã hoạt động lại”.** `w:"majority"`, election term, optime, rollback risk, transaction semantics, backup/PITR và monitoring người dùng đều cần được xem xét. Khi thiếu majority, ưu tiên khôi phục connectivity và dữ liệu hợp lệ, không force reconfig hoặc xóa member chỉ để lệnh trả thành công.

Một runbook tốt giúp đội vận hành trả lời được: **có đủ phiếu không, dữ liệu ứng viên mới đến đâu, ai sẽ nhận writes, ứng dụng cần bao lâu để phục hồi, những request nào có kết quả chưa chắc chắn và bước nào có thể làm an toàn tiếp theo**.

## 58. Tài liệu tham khảo

- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/): cơ chế bầu primary và eligibility.
- [MongoDB Manual — Replica Set Member States](https://www.mongodb.com/docs/manual/reference/replica-states/): các trạng thái PRIMARY, SECONDARY, RECOVERING, ROLLBACK.
- [MongoDB Manual — rs.stepDown()](https://www.mongodb.com/docs/manual/reference/method/rs.stepdown/): chuyển primary có kế hoạch.
- [MongoDB Manual — replSetStepDown](https://www.mongodb.com/docs/manual/reference/command/replsetstepdown/): tham số và quy tắc stepdown.
- [MongoDB Manual — Add Members to a Replica Set](https://www.mongodb.com/docs/manual/tutorial/expand-replica-set/): thêm members và initial sync.
- [MongoDB Manual — Remove Members from a Replica Set](https://www.mongodb.com/docs/manual/tutorial/remove-replica-set-member/): loại thành viên theo quy trình.
- [MongoDB Manual — rs.reconfig()](https://www.mongodb.com/docs/manual/reference/method/rs.reconfig/): thay đổi cấu hình, voting/quorum caveats.
- [MongoDB Manual — Replica Set Configuration](https://www.mongodb.com/docs/manual/reference/replica-configuration/): votes, priority, hidden và delayed members.
- [MongoDB Manual — Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/): retention, replication lag và initial sync.
- [MongoDB Manual — Rollbacks During Replica Set Failover](https://www.mongodb.com/docs/manual/core/replica-set-rollbacks/): rủi ro chưa majority committed.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): driver retry semantics.
- [MongoDB Manual — Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/): primary/secondary và khả năng stale reads.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): majority durability và timeouts.
- [MongoDB Manual — Upgrade a Replica Set](https://www.mongodb.com/docs/manual/release-notes/upgrade/): quy trình nâng cấp theo phiên bản.
- [MongoDB Atlas — Test Failover](https://www.mongodb.com/docs/atlas/tutorial/test-failover/): kiểm thử khả năng phục hồi ở managed clusters.
- [MongoDB Java Driver — Connection Options](https://www.mongodb.com/docs/drivers/java/sync/current/connection/specify-connection-options/): topology, timeouts và retry options.
