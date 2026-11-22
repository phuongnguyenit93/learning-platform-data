# Sao lưu liên tục và khôi phục đến thời điểm theo nền tảng hỗ trợ trong MongoDB

## 1. Vấn đề: backup hôm qua không cứu được mọi sự cố hôm nay

Giả sử hệ thống quản lý đơn hàng dùng MongoDB, có dữ liệu đang thay đổi liên tục:

```text
08:00   Snapshot hoàn tất, chứa 15 triệu orders.
09:15   Người dùng tạo đơn O100.
09:45   Đơn O100 được thanh toán.
10:12   Một batch job chạy sai, cập nhật nhầm hàng nghìn orders.
10:20   Phát hiện và tạm dừng batch job.
```

Nếu chỉ có snapshot lúc 08:00, restore sẽ làm biến mất cả những đơn/tác vụ hợp lệ phát sinh từ 08:00 đến 10:12.

**Point-in-Time Recovery (PITR)** — khôi phục đến một thời điểm được chọn — cho phép tổ chức phục hồi trạng thái dữ liệu tại một mốc như **10:11**, trước khi batch sai bắt đầu, **nếu** nền tảng backup đã lưu đủ snapshot và lịch sử thay đổi để replay tới mốc đó.

Về nguyên lý:

```text
Snapshot S0      Các thay đổi được ghi vào oplog            Sự cố
  08:00   E1   E2   E3   E4   E5 ... E1000                10:12
    |------|----|----|----|----------|----------------------|
                                           ^
                                     Chọn PITR 10:11
                                               |
                                               v
                                    Restore S0 + replay
                                    các thay đổi tới mốc
                                           mong muốn
```

**PITR không có nghĩa sao lưu lại toàn bộ database sau mỗi giây.** Thường nó kết hợp:

1. Một **snapshot nền** nhất quán.
2. Một **dòng thay đổi oplog** được thu thập và giữ lại liên tục.
3. Một engine/tool **restore và replay** theo thứ tự đến điểm mục tiêu.

Điều kiện quan trọng: phải có **lịch sử đầy đủ, không có khoảng hở**, và thời điểm mong muốn phải nằm trong **restorable window** mà nền tảng thực sự hỗ trợ.

> **Tư duy cần nhớ:** snapshot trả lời “khởi động từ trạng thái nào?”, còn oplog liên tục trả lời “áp dụng tiếp những thay đổi nào đến mốc T?”.

---

## 2. Thuật ngữ cần phân biệt

| Thuật ngữ | Định nghĩa | Ví dụ |
| --- | --- | --- |
| **Snapshot** | Ảnh chụp trạng thái database nhất quán tại một mốc | Snapshot 08:00 |
| **Continuous Backup** | Backup kết hợp snapshot với việc lưu thay đổi liên tục theo cơ chế nền tảng | Atlas Continuous Cloud Backup |
| **PITR** | Khôi phục đến một thời điểm/điểm oplog cụ thể trong window | Khôi phục 10:11 |
| **Oplog** | Log replication chứa các thao tác cần tái tạo trạng thái | `local.oplog.rs` trên replica set |
| **Oplog archive/store** | Nơi hệ backup giữ lịch sử oplog tách khỏi oplog vòng trên node nguồn | Atlas object storage hoặc Ops Manager Oplog Store |
| **Restore point** | Điểm thời gian hoặc timestamp có thể chọn khi restore | 10:11 UTC |
| **Restore window** | Khoảng thời gian nền tảng hiện có thể khôi phục | Ví dụ 7 ngày cuối |
| **Retention policy** | Quy tắc giữ snapshot, oplog và bản sao backup | Snapshot 30 ngày, PITR 7 ngày |
| **RPO** | Lượng dữ liệu tối đa chấp nhận mất, tính theo thời gian | RPO 5 phút |
| **RTO** | Thời gian tối đa chấp nhận để hệ thống hoạt động trở lại | RTO 2 giờ |
| **Recovery validation** | Kiểm tra sau restore để xác nhận dữ liệu và ứng dụng đủ đúng | Đối soát số orders, payments |
| **Cutover** | Chuyển application sang deployment đã restore | Đổi connection string có kiểm soát |

### 2.1. PITR khác snapshot gần nhất

Snapshot gần nhất có thể là 08:00; PITR có thể khôi phục 10:11 nếu lịch sử E1…En còn. Nếu chỉ giữ snapshots hàng ngày mà **không có oplog archive**, không được gọi đó là PITR thực thụ.

### 2.2. RPO khác restore window

- **Restore window 7 ngày** nghĩa là bạn có thể **chọn** một số thời điểm trong khoảng 7 ngày, theo điều kiện backup.
- **RPO 5 phút** nghĩa là doanh nghiệp chấp nhận mất tối đa 5 phút dữ liệu khi xảy ra sự cố.
- Một hệ có restore window 7 ngày vẫn có thể không đáp ứng RPO 5 phút nếu backup stream đang chậm hoặc lỗi.
- Một hệ có RPO thấp vẫn có thể có RTO cao do database lớn và phải replay nhiều oplog.

### 2.3. RTO bao gồm nhiều bước ngoài “restore data”

```text
RTO thực tế =
  nhận diện sự cố
  + quyết định thời điểm T
  + provision đích
  + restore snapshot
  + replay oplog
  + rebuild derived indexes
  + đối soát dữ liệu
  + chuyển traffic
  + kiểm thử ứng dụng
```

Đây là mô hình hoạch định, không phải phép cộng có các phần luôn chạy tuần tự. Nhiều công việc có thể song song nhưng vẫn phải đo end-to-end.

---

## 3. Oplog hoạt động như thế nào?

MongoDB replica set sử dụng **oplog**, một collection dạng capped trong database `local`. Oplog lưu các thao tác replication ở mức hệ thống cần để các secondary tái tạo trạng thái từ primary.

### 3.1. Hình dung dòng thay đổi

```text
Primary:
  INSERT order O100
  UPDATE order O100 -> PAID
  INSERT order O101
  DELETE temporary record

Oplog:
  ts1 -> insert
  ts2 -> update
  ts3 -> insert
  ts4 -> delete

Secondaries / backup tailer:
  đọc và áp dụng theo semantics replication
```

Không xem oplog như một API audit lịch sử vô thời hạn. Nó phục vụ replication và bị giới hạn bởi retention/capped behavior.

### 3.2. Oplog trên node và oplog do backup lưu

Phân biệt:

**Oplog của MongoDB node**:

- Có thời gian lưu thực tế phụ thuộc kích thước/cường độ ghi.
- Có thể bị rollover khi dữ liệu cũ bị thay thế.
- Không phải kho lịch sử dài hạn mặc định.

**Oplog archived by backup service**:

- Được backup agent/service thu thập liên tục.
- Được lưu ngoài oplog nguồn theo backup retention policy.
- Có thể cung cấp lịch sử dài hơn oplog trực tiếp trên node.
- Phải đủ liên tục từ snapshot nền tới restore point T.

Nếu agent ngừng tailing quá lâu và oplog trên node đã rollover, có thể tạo **oplog gap** làm một số mốc không còn restorable.

### 3.3. Oplog Timestamp không phải ISODate

MongoDB có **BSON Timestamp** dạng:

```javascript
Timestamp({ t: 1794632400, i: 1 })
```

- `t`: phần thời gian Unix tính bằng giây.
- `i`: increment logic trong giây đó.

Hai operations có thể cùng phần `t` nhưng khác `i`.

```text
2026-11-14T09:00:00Z:
  ts=(t, 1) -> update A
  ts=(t, 2) -> update B
  ts=(t, 3) -> insert C
```

BSON `Date` như `ISODate("2026-11-14T09:00:00Z")` không phải một `Timestamp(t,i)` đầy đủ.

---

## 4. Cơ chế khôi phục: snapshot + replay oplog

Giả sử nền tảng có:

```text
Snapshot S0 tại T0 = 08:00
Oplog archive có các events trong [08:00, 10:20]
Restore target T = 10:11
```

Quá trình:

1. Xác định snapshot hợp lệ tại hoặc trước T.
2. Phục hồi snapshot vào target cluster.
3. Tìm đoạn oplog cần áp dụng sau snapshot.
4. Replay các thao tác trong đúng thứ tự/ranh giới hỗ trợ.
5. Dừng tại restore point T.
6. Kiểm tra consistency, indexes, permissions và application invariants.
7. Chuyển traffic hoặc trích xuất dữ liệu cần phục hồi.

### 4.1. Tại sao không thể replay từ giữa mà không có snapshot?

Oplog chứa thay đổi, không phải bản sao toàn bộ database. Một update kiểu “tăng counter” không thể dựng toàn bộ document nếu không biết trạng thái trước đó.

### 4.2. Tại sao snapshot phải nhất quán?

Nếu snapshot được chụp khi collection A ở một mốc nhưng collection B ở mốc khác, các transaction/bản ghi liên quan có thể không nhất quán. Replay từ một điểm logic không tương thích có thể không khôi phục được state đúng.

Hệ backup chuyên dụng phải phối hợp snapshot và oplog, đặc biệt trên sharded cluster.

### 4.3. Ranh giới thời điểm rất quan trọng

Tùy công cụ:

- **Date/time** có granularity và quy tắc bao gồm/loại trừ riêng.
- **Oplog Timestamp** có thể chỉ định sát một thao tác hơn.
- Ops Manager mô tả restore theo **Point In Time** là áp dụng operations **trước** mốc thời gian chọn; restore theo **Oplog Timestamp** gồm operations **đến và bao gồm** timestamp đã chỉ định.
- Atlas UI có granularity date/time và oplog timestamp khác nhau.

**Không đoán quy tắc inclusive/exclusive giữa các nền tảng.** Luôn đọc mô tả tại giao diện/tool đang dùng và kiểm tra recovery trên môi trường tách biệt.

---

## 5. Các nền tảng hỗ trợ: không có một câu lệnh dùng cho tất cả

| Mô hình MongoDB | Cơ chế liên quan | PITR liên tục có sẵn? | Điều cần xác minh |
| --- | --- | --- | --- |
| **Atlas Core M10+ dedicated** | Cloud Backup + Continuous Cloud Backup | Có, nếu bật/tồn tại window | Tier, backup policy, oplog window, topology |
| **Atlas Infinite** | Cơ chế backup liên tục theo edition | Có theo policy/giới hạn edition; 24 giờ mặc định theo tài liệu 2026 | Thủ tục riêng cho Infinite, không sao chép hướng dẫn Core |
| **Atlas Free/Flex** | Chính sách backup riêng theo tier | Không coi PITR của M10+ là khả dụng mặc định | Tier/feature availability |
| **MongoDB Enterprise + Ops Manager** | Scheduled snapshots + oplog store + MongoDB Backup Restore Utility | Có khi được cấu hình và versions hỗ trợ | Ops Manager, FCV, agent, oplog continuity |
| **MongoDB Enterprise + Cloud Manager** | Dịch vụ backup có snapshot/oplog | Có theo feature/config được hỗ trợ | Enterprise license/backup activation/retention |
| **Self-managed Community + cron mongodump** | Logical dumps định kỳ | **Không tự có** PITR liên tục | Chỉ có mốc snapshot/dump nếu không có archival riêng |
| **Self-managed với filesystem snapshots** | Physical snapshot định kỳ | Không tự có continuous PITR | Snapshot consistency và oplog archive riêng |
| **Giải pháp backup bên thứ ba** | Snapshot + oplog archival tùy sản phẩm | Có thể có | Vendor support matrix, test consistency, restore |

**Điểm dễ mắc lỗi:** dùng `mongodump --oplog` rồi khẳng định đã có continuous backup giống Atlas. Nó chỉ bắt những oplog entries phát sinh **trong thời gian dump chạy** nhằm tạo dump nhất quán, không tự giữ lịch sử đến mọi thời điểm sau dump.

---

## 6. MongoDB Atlas: Cloud Backup khác Continuous Cloud Backup

### 6.1. Cloud Backup thông thường

Atlas Cloud Backup cung cấp snapshots theo backup policy:

- Hourly.
- Daily.
- Weekly.
- Monthly.
- Yearly, tùy chính sách/edition.

Có thể có snapshot incremental về mặt storage, nhưng mỗi snapshot đại diện một **restore point hoàn chỉnh**.

```text
08:00 snapshot
12:00 snapshot
16:00 snapshot

Chỉ snapshots:
  Có thể restore các mốc 08:00, 12:00, 16:00.
  Không mặc nhiên chọn chính xác 10:11.
```

### 6.2. Continuous Cloud Backup

Khi bật tính năng liên tục:

```text
08:00 snapshot
  + oplog 08:00...12:00
12:00 snapshot
  + oplog 12:00...16:00
16:00 snapshot

Có thể chọn T trong PIT restore window nếu
snapshot và oplog cần thiết đều khả dụng.
```

Atlas thu thập/lưu oplog ở object storage của cloud provider, ví dụ:

- AWS S3.
- Azure Blob Storage.
- Google Cloud Storage.

Tính năng này **phát sinh chi phí bổ sung** so với backup snapshots thông thường.

### 6.3. Mức hỗ trợ trên Atlas Core

Tài liệu Atlas Core hiện hành nêu Continuous Cloud Backup restore là tính năng dành cho **dedicated clusters M10+**. Không áp dụng nguyên xi cho Free/Flex.

Một người dùng có cluster hỗ trợ `$search` hoặc replica set không có nghĩa chắc chắn có Continuous Cloud Backup. Phải xác minh cấu hình backup thực tế.

---

## 7. Bật Continuous Cloud Backup trên Atlas Core

Quy trình khái niệm từ Atlas UI:

1. Mở tổ chức/project chứa cluster.
2. Chọn dedicated cluster đủ điều kiện.
3. Vào **Edit Configuration / Additional Settings**.
4. Bật **Cloud Backup** nếu chưa có.
5. Bật **Continuous Cloud Backup**.
6. Vào **Backup Policy**.
7. Cấu hình **Point-in-Time Restore Window**.
8. Xem danh sách snapshots và restorable ranges.
9. Bật monitoring/alerts, kiểm tra chi phí phát sinh.
10. Thực hiện một bài restore diễn tập vào cluster tách biệt.

Đừng coi việc bật toggle thành công là đủ để tuyên bố có PITR đến một thời điểm bất kỳ trong lịch sử. Nếu tính năng mới bật, không tự có oplog archive cho tuần trước đó.

### 7.1. Restore window bị giới hạn bởi hourly snapshot retention

Tài liệu Atlas quy định **không thể cấu hình continuous restore window dài hơn thời gian giữ hourly snapshots**.

Ví dụ:

```text
Hourly snapshot retention = 7 days
PIT restore window         = 7 days  -> có thể hợp lệ

Hourly snapshot retention = 2 days
PIT restore window         = 7 days  -> không hợp lệ
```

Muốn PITR 7 ngày cần thiết kế retention của snapshots tương ứng và trả chi phí lưu cả snapshot lẫn oplog.

### 7.2. Tắt Continuous Cloud Backup làm mất lịch sử

Atlas nêu rõ: **khi tắt Continuous Cloud Backup, lịch sử continuous backup sẽ bị xóa**.

Do đó, tắt để “giảm phí vài giờ rồi bật lại” không phải một thay đổi vô hại. Có thể mất khả năng chọn điểm khôi phục cũ.

Nếu project bật **Backup Compliance Policy**, việc giảm PIT restore window còn có thể bị ràng buộc bởi quy trình yêu cầu support/phê duyệt đặc biệt.

---

## 8. Chọn thời điểm khôi phục trong Atlas

Atlas cung cấp các cách xác định restore point trên Continuous Cloud Backup:

- **Date & Time**.
- **Oplog Timestamp**.

Theo tài liệu Atlas năm 2026:

| Lựa chọn | Granularity tại UI | Khi nào phù hợp |
| --- | --- | --- |
| Date & Time | Theo phút | Biết thời điểm xảy ra lỗi theo đồng hồ |
| Oplog Timestamp | Theo giây và timestamp/oplog semantics được hỗ trợ | Cần sát một thao tác cụ thể hơn |

### 8.1. Ví dụ sai batch update

```text
10:11:30 UTC: legitimate order completed
10:12:05 UTC: bad batch starts
10:12:45 UTC: bad batch ends
```

Mục tiêu nghiệp vụ: lấy trạng thái **trước thao tác sai đầu tiên**, nhưng vẫn giữ hợp lệ tối đa.

Quy trình:

1. Dùng audit logs/app logs để xác định thao tác sai bắt đầu lúc nào.
2. Chuyển mọi timestamp về **UTC**, lưu ý timezone của dashboard.
3. Nếu muốn phục hồi phút 10:11, chọn date/time theo semantics UI.
4. Nếu có oplog timestamp được chứng minh là ranh giới đúng, dùng lựa chọn Oplog Timestamp phù hợp.
5. **Restore vào cluster tách biệt để kiểm chứng**, trước khi quyết định cutover.

Không lấy giờ laptop cá nhân hoặc giờ hiển thị trong một hệ log có timezone khác rồi nhập trực tiếp.

### 8.2. Oplog Timestamp không phải một resume token

Một **Change Stream resume token** có thể chứa metadata vị trí sự kiện; nó không phải tham số thay thế trực tiếp cho BSON `Timestamp(t,i)` trong PITR UI.

Không biến `resume token._data` thành timestamp bằng cách cắt chuỗi một cách tự chế.

### 8.3. Điểm khôi phục quá gần “bây giờ”

Không mặc định được restore đến giây hiện tại. Recent writes có thể chưa được backup stream lưu đầy đủ, và Atlas có hạn chế khoảng khôi phục xung quanh quá trình restore/snapshot mới.

Hãy dựa vào **latest restorable point thực tế**, không dùng UTC now trừ khi UI xác nhận mốc đó hợp lệ.

---

## 9. Khôi phục Atlas Core: phải chọn đích an toàn

Quy trình lựa chọn target:

```text
Continuous backup source cluster
            |
            v
     Chọn restore point T
            |
            +-- restore vào existing target
            |       có nguy cơ xóa/ghi đè dữ liệu đích
            |
            +-- restore vào new isolated cluster
                    |
                    v
              Validate / compare
                    |
                    v
             Planned cutover
```

### 9.1. Cluster-level restore có thể phá dữ liệu đích

Tài liệu Atlas nêu: khi **cluster-level restore**, Atlas xóa dữ liệu hiện có trên target cluster trước khi restore và target không khả dụng trong thời gian khôi phục.

**Khuyến nghị mặc định:** restore sang **cluster mới, cô lập, không nhận traffic production**. Không chỉ định production cluster đang hoạt động làm đích khi chưa có phê duyệt và kế hoạch ghi đè rõ ràng.

### 9.2. Những bước trong Atlas UI

1. Mở **Backup** của project.
2. Chọn cluster source đã bật Continuous Cloud Backup.
3. Chọn **Point in Time Restore**.
4. Chọn **Date & Time** hoặc **Oplog Timestamp**.
5. Chọn target project/cluster hoặc tạo cluster mới theo yêu cầu.
6. Kiểm tra backup time, version và topology compatibility.
7. Xác nhận tác động xóa dữ liệu trên target.
8. Gửi restore job và theo dõi tiến độ.
9. Đợi target healthy; kiểm tra indexes và dữ liệu.
10. Chỉ chuyển traffic sau ứng dụng đã được validation.

### 9.3. Restore selected database/collection

Atlas hiện hỗ trợ những workflow **selected databases/collections** từ Continuous Cloud Backup theo điều kiện. Tuy nhiên:

- Không suy luận rằng partial restore bảo toàn mọi tham chiếu liên collection.
- Các permissions, indexes, metadata và dữ liệu bên ngoài có thể cần xử lý riêng.
- Partial restore không hoàn toàn tương đương khôi phục cluster từ cùng T.
- Chỉ dùng theo tài liệu chức năng và version hiện hành.

Nếu business yêu cầu tính nhất quán giữa orders, payments và inventory, restore một collection duy nhất có thể tạo thêm vấn đề.

---

## 10. Những hạn chế restore của Atlas cần biết

### 10.1. MongoDB version compatibility

Atlas có thể từ chối restore từ backup thuộc version không tương thích với target deployment. Ví dụ cluster đã upgrade có thể không restore liên tục tới một target ở version khác nếu workflow không hỗ trợ.

### 10.2. Topology của sharded cluster

Atlas Cloud Backup hỗ trợ sharded clusters, nhưng thay đổi số shard/topology có thể làm những snapshots cũ không restore về cùng cluster theo cách thông thường; có thể cần target topology tương thích.

### 10.3. Restore đồng thời với writes

Atlas khuyến nghị ngừng client operations tới **target cluster** trong lúc restore. Nếu target đang nhận ghi từ ứng dụng, restore có thể ghi đè hoặc làm mất tính nhất quán.

### 10.4. Derived indexes có thể cần rebuild

MongoDB Search/Vector Search:

- Snapshot có thể giữ **Search index definitions**.
- Search index data có thể phải được `mongot` rebuild/initial sync.
- Việc database restore xong không bảo đảm Search đã bắt kịp và ready.
- Tính RTO phải bao gồm thời gian rebuild derived indexes nếu ứng dụng phụ thuộc Search.

### 10.5. Restore window có thể có lỗ

Không phải mọi thời điểm giữa “7 ngày trước” và “bây giờ” luôn được đảm bảo khả dụng. Nền tảng hiện rõ **restorable time ranges**; các thay đổi topology/backup failure hoặc ràng buộc restore có thể tạo khoảng không khả dụng.

### 10.6. Restore không tự rollback external side effects

Nếu trong khoảng 10:11–10:20 ứng dụng đã:

- Gửi email.
- Gọi payment gateway.
- Publish Kafka events.
- Cập nhật Elasticsearch.
- Phát push notification.
- Tạo chứng từ ở hệ kế toán.

thì restore MongoDB về 10:11 **không thu hồi các side effects đã thực hiện**. Cần reconciliation/compensation riêng.

---

## 11. Atlas Infinite: đừng dùng nguyên runbook Atlas Core

Theo tài liệu MongoDB 2026, **Atlas Infinite** có kiến trúc backup và thủ tục restore riêng.

Một điểm đáng chú ý:

- Continuous backup window **24 giờ** được bật sẵn theo tài liệu của edition này.
- Không thực hiện bước bật toggle giống Atlas Core.
- Khả năng restore liên quan edition và các yêu cầu target/backup riêng.
- Một số tính năng là public preview hoặc có giới hạn cụ thể tại thời điểm triển khai.

Vì vậy:

```text
Có Atlas Infinite?
   |
   +-- dùng hướng dẫn restore Infinite riêng
   |
   +-- KHÔNG áp mặc định:
       "M10+ Core -> bật Continuous Cloud Backup -> restore Core"
```

Trong kiến trúc/lesson, cần kiểm tra **Atlas edition**, không chỉ thấy cùng logo Atlas rồi suy ra feature parity.

Nguồn quy trình: tài liệu “Recover a Point In Time with Continuous Cloud Backup” và “Restore an Atlas Infinite Cluster”.

---

## 12. MongoDB Enterprise self-managed: Ops Manager

MongoDB **Ops Manager** là nền tảng quản trị/backup cài đặt trong hạ tầng của tổ chức, hỗ trợ backup replica set và sharded cluster với snapshot cùng oplog archive.

Các thành phần khái niệm:

```text
MongoDB deployment:
  Replica sets / shards / config servers
               |
               | Backup Agent / Ops Manager components
               v
          Oplog capture
               |
       +-------+--------+
       |                |
       v                v
 Snapshot Store      Oplog Store
       |                |
       +-------+--------+
               |
               v
      Ops Manager metadata/control plane
               |
               v
   MongoDB Backup Restore Utility (MBRU)
               |
               v
          Target deployment
```

### 12.1. Snapshot Store và Oplog Store

**Snapshot Store** giữ trạng thái nền của database.

**Oplog Store** giữ thay đổi giữa các snapshots để có thể replay.

Nếu snapshot vẫn còn nhưng oplog liên tục từ snapshot tới T bị đứt, Ops Manager có thể không khôi phục tới T. Ngược lại có oplog mà snapshot nền cần thiết đã bị xóa cũng không đủ.

### 12.2. MongoDB Backup Restore Utility (MBRU)

Với point-in-time restore, Ops Manager dùng **MongoDB Backup Restore Utility** trên target để tải/áp dụng oplog entries từ snapshot nền đến điểm đã chọn.

Không nhầm MBRU với:

- `mongorestore` của MongoDB Database Tools.
- Lệnh replica set `rs.syncFrom()`.
- Application consumer dùng Change Streams.
- Tự chạy `applyOps` từng document thủ công.

### 12.3. Yêu cầu version

Tài liệu Ops Manager cho biết hỗ trợ PITR theo cơ chế hiện đại với **Ops Manager 6.0 trở lên và FCV 6.0 trở lên** trong những trường hợp được mô tả. Cần đối chiếu matrix chính thức với MongoDB Server version và Ops Manager đang chạy.

---

## 13. Ops Manager: quy trình Point-in-Time Restore

Khung quy trình:

1. Xác nhận deployment đã có backup và recent snapshots hợp lệ.
2. Vào **Continuous Backup / Overview**.
3. Chọn deployment cần phục hồi.
4. Chọn **Restore or Download**.
5. Chọn restore type **Point In Time** hoặc **Oplog Timestamp** theo mục tiêu.
6. Chọn thời điểm **nằm trong restorable range** được hiển thị.
7. Chọn phương thức automatic/manual restore theo khả năng quản trị.
8. Provision host/target storage và MongoDB Backup Restore Utility nếu cần.
9. Áp dụng snapshot và oplog tới restore point.
10. Xác minh node health, dữ liệu, indexes và application.
11. Cắt traffic theo kế hoạch nếu cần.

### 13.1. Ranh giới inclusive/exclusive của Ops Manager

Theo trang restore replica set/sharded cluster:

| Restore type | Semantics được mô tả |
| --- | --- |
| **Point In Time** | Chỉ bao gồm operations **trước**, không bao gồm đúng thời điểm Date & Time đã chọn |
| **Oplog Timestamp** | Bao gồm operations **đến và bao gồm** timestamp đã chỉ định |

Nếu muốn dừng trước một thao tác phá dữ liệu, ranh giới này quyết định bạn có vô tình replay luôn thao tác đó hay không.

### 13.2. Oplog Store retention

Tài liệu Ops Manager mô tả cấu hình mặc định có thể giữ **24 giờ oplog**. Nhưng đây là **giá trị mặc định/tham khảo**, không phải lời đảm bảo mọi deployment Ops Manager giữ đúng 24 giờ.

Phải xem retention policy và **restorable ranges thực tế** của deployment.

### 13.3. Restore sharded cluster

Khi restore từ một snapshot/point in time của sharded cluster, Ops Manager phải phối hợp **tất cả shards và config servers** để có trạng thái logic tương thích.

Một thao tác restore một shard đơn lẻ trong workflow tự động không bảo đảm tính nhất quán và có thể bị từ chối. Không tự lấy snapshot shard A lúc T1, shard B lúc T2 rồi ghép thành cluster.

---

## 14. Cloud Manager cho self-managed Enterprise

MongoDB **Cloud Manager** là dịch vụ hosted cung cấp backup, monitoring và automation cho MongoDB self-managed theo điều kiện.

Tài liệu Manual nêu:

- Backup replica sets và sharded clusters thông qua việc đọc oplog.
- Tạo snapshots theo lịch.
- Cung cấp **point-in-time recovery**.
- Để dùng backup Cloud Manager cho self-managed, phải có **MongoDB Enterprise Server** theo requirements hiện hành.

Về nguyên lý tương tự Ops Manager nhưng khác nơi vận hành control plane:

```text
Cloud Manager
  hosted management service
           |
           v
Self-managed MongoDB Enterprise
           |
           v
Snapshot/Oplog backup architecture
           |
           v
Point-in-time restore khi được cấu hình
```

Không suy luận rằng một deployment Community tự quản lý, chỉ vì có thể kết nối dashboard monitoring, sẽ tự có continuous PITR giống Enterprise Cloud Manager backup.

---

## 15. Self-managed không có Ops Manager/Cloud Manager

Với MongoDB Community hoặc Enterprise không dùng dịch vụ backup có PITR, các lựa chọn có thể gồm:

1. **Filesystem snapshot định kỳ**.
2. **`mongodump` / `mongorestore`**.
3. **Backup của cloud volume**.
4. **Giải pháp backup bên thứ ba** có continuous oplog archival tương thích.
5. Kiến trúc ứng dụng có **event sourcing/outbox** để tái dựng trạng thái nghiệp vụ, nếu được thiết kế từ trước.

Nhưng các cách 1–3 **không tự tạo PITR liên tục**.

### 15.1. Filesystem snapshot

Snapshot volume có thể tạo một ảnh chụp tại thời điểm cụ thể. Tuy nhiên:

- Đây là một restore point cố định nếu không có oplog archive.
- Phải đảm bảo snapshot nhất quán đối với MongoDB và filesystem.
- Replica set/sharded cluster có các lưu ý về checkpoint và coordination.
- Một snapshot VM không đồng nghĩa cluster-wide consistent snapshot trên các shards.
- Có thể cần `fsyncLock` hoặc giải pháp backup hỗ trợ, nhưng khóa ghi ảnh hưởng availability và không nên chạy thiếu kế hoạch.

### 15.2. Third-party PITR

Nếu chọn tool bên thứ ba, bắt buộc xác minh:

- Hỗ trợ đúng MongoDB version/FCV.
- Hỗ trợ replica set hay sharded cluster?
- Có hiểu multi-document transactions và chunk migrations?
- Snapshot và oplog archive liên tục có bảo đảm không?
- Restore đến timestamp có semantics gì?
- Backup encryption/key management như thế nào?
- Restoration có test được và vendor hỗ trợ không?

Một repository ghi “supports MongoDB backups” chưa đủ chứng minh nó hỗ trợ PITR cho sharded cluster.

---

## 16. MongoDB Database Tools: mongodump --oplog có tác dụng gì?

Đối với **replica set**, có thể tạo logical dump nhất quán khi có writes bằng:

```bash
# Ví dụ chỉ chạy trên môi trường test/staging hoặc
# production đã có backup plan, credentials và capacity.
mongodump \
  --uri "mongodb://backup-user@host1:27017,host2:27017,host3:27017/?replicaSet=rs0&authSource=admin" \
  --oplog \
  --out "./backup-2026-11-14"
```

Tùy cách cấu hình URI, không nên đặt password trong command line gây lộ qua shell history/process list; sử dụng credential handling an toàn.

### 16.1. --oplog capture điều gì?

`mongodump --oplog` ghi thêm **các oplog entries phát sinh trong lúc dump chạy** vào:

```text
backup-2026-11-14/
  admin/
  appdb/
  ...
  oplog.bson
```

Lúc restore, có thể replay những entries đó để dump đại diện một trạng thái nhất quán hơn.

### 16.2. --oplog không phải continuous archive

```text
mongodump starts: 10:00
mongodump ends:   10:10

--oplog captures changes while dump runs:
  10:00 ... 10:10

It does NOT automatically keep capturing:
  10:10 ... next week.
```

Nếu ứng dụng lỗi lúc 16:00, chỉ có dump 10:00–10:10 không làm phát sinh khả năng restore tùy ý tới 15:59.

### 16.3. Những giới hạn quan trọng

- `--oplog` chỉ áp dụng trên nodes có oplog (replica set members).
- Yêu cầu **full dump** của replica set member; không kết hợp `--db`/`--collection`/`--query` trong workflow này.
- `mongodump --oplog` **không hỗ trợ backup cả sharded cluster qua mongos**.
- Một số thao tác DDL/administrative khi dump có thể làm backup thất bại.
- Nó không dump toàn bộ oplog collection; chỉ lấy đoạn thay đổi trong thời gian dump.
- MongoDB Database Tools có giới hạn replay qua thay đổi FCV/time-series format theo phiên bản.

Dùng nó khi mục tiêu là **consistent logical backup**, không gọi đó là PITR liên tục trên toàn hệ thống.

---

## 17. mongorestore --oplogReplay và --oplogLimit

Khi đã có dump phù hợp:

```bash
mongorestore \
  --uri "mongodb://localhost:27018/?directConnection=true" \
  --drop \
  --oplogReplay \
  "./backup-2026-11-14"
```

**Nguy hiểm:** `--drop` sẽ xóa các collections tương ứng trên target trước khi restore. Chỉ sử dụng trên **đích test mới/cô lập**, đã xác minh URI. Đừng chạy vào production theo ví dụ.

### 17.1. --oplogLimit là ranh giới exclusive

MongoDB Database Tools định nghĩa:

```text
--oplogLimit=<seconds>:<increment>
```

Các oplog entries có timestamp **lớn hơn hoặc bằng** limit sẽ **không** được áp dụng. Nghĩa là giới hạn **exclusive**.

Ví dụ:

```bash
mongorestore \
  --uri "mongodb://localhost:27018/?directConnection=true" \
  --drop \
  --oplogReplay \
  --oplogLimit "1794632400:4" \
  "./backup-2026-11-14"
```

Theo semantics tham số, operation có timestamp `(1794632400,4)` và các operations sau nó **không** được replay. Không khẳng định dump nào cũng có entry đó.

### 17.2. Vì sao --oplogLimit không tự là PITR toàn thời gian?

- Bạn chỉ có thể replay **những oplog entries thật sự có trong nguồn dump/oplogFile**.
- Nếu không lưu lịch sử đến thời điểm cần, limit không làm lịch sử xuất hiện.
- Việc cung cấp oplog file thủ công có nguy cơ **corruption/inconsistency** khi các entries không khớp snapshot.
- `mongorestore --oplogReplay` **không hỗ trợ sharded cluster**.
- FCV/time-series migrations có thể tạo mốc không replay liên tục được bằng một lượt đơn giản.
- Một dump có dữ liệu nền sau thời điểm limit là một cấu hình restore không đúng logic; phải có snapshot nền tương thích.

### 17.3. Đừng tự làm “PITR service” bằng cron + oplog.rs copy ngẫu nhiên

Việc snapshot và export `local.oplog.rs` vào những thời điểm khác nhau không đảm bảo:

- Không có gaps.
- Có đúng đầu/cuối restore range.
- Có cùng replication history sau rollback.
- Có đủ thông tin transaction.
- Nhất quán đa shard.
- Bảo đảm replay across FCV.

Nếu không có engine được hỗ trợ, cần xem đây là một dự án backup/recovery chuyên sâu, không phải vài cron scripts.

---

## 18. Hiểu đủ về point-in-time consistency

Một backup có thể thỏa:

- **Crash consistency**: trạng thái tương tự hệ vừa mất điện, storage engine tự recovery.
- **Filesystem consistency**: các bytes trong snapshot được chụp ở một thời điểm/storage boundary.
- **MongoDB replication consistency**: dữ liệu phản ánh một lịch sử replication hợp lệ.
- **Cluster-wide consistency**: với sharded cluster, mọi shards/config metadata cùng thuộc một restore point logic tương thích.
- **Application consistency**: giữa MongoDB và dịch vụ ngoài không còn giao dịch dở dang mâu thuẫn.

Những mức này **khác nhau**.

### 18.1. Một transaction nhiều document

Giả sử transaction:

```text
Transaction TX1:
  Update account A: -100
  Update account B: +100
  Insert transfer record
```

Backup/PITR cần tránh phục hồi một trạng thái chỉ có debit nhưng thiếu credit.

Các giải pháp backup hỗ trợ MongoDB transaction semantics và consistent oplog replay mới có thể xử lý đúng. Không tách restore riêng collections của cùng một invariant mà không có reconciliation.

### 18.2. Application và external systems

Một payment gateway có thể đã nhận tiền lúc 10:13, nhưng MongoDB PITR tới 10:11 chưa có `payment.status=PAID`. Nếu app tự charge lại sau cutover, khách có thể bị charge hai lần.

Do đó phải phân loại:

- Dữ liệu có thể dựng lại từ source of truth.
- Side effects không thể đảo ngược (bank transfers, emails).
- Idempotency keys và event IDs.
- Reconciliation tasks sau khôi phục.

---

## 19. Sharded cluster: snapshot và oplog phải đồng bộ

Một sharded cluster có:

```text
                    mongos
                      |
             +--------+--------+
             |                 |
          Shard A            Shard B
         replica set        replica set
             |                 |
             +--------+--------+
                      |
                Config servers
```

Một transaction có thể chạm cả hai shards. Metadata chunk placement cũng thay đổi khi migration.

### 19.1. Nguy cơ khi ghép snapshot thủ công

```text
Shard A snapshot at 10:00
Shard B snapshot at 10:02
Config server snapshot at 09:58
```

Dù mỗi snapshot riêng lẻ hợp lệ, **toàn cluster** chưa chắc tương thích: chunk migrations, distributed transactions và metadata khác mốc.

### 19.2. Vì sao dùng backup platform hỗ trợ sharded cluster?

Atlas và Ops Manager có cơ chế phối hợp thời gian/lịch sử phục hồi các thành phần.

Tài liệu Atlas Core nói Atlas phối hợp snapshot time trên shards để bảo vệ consistency theo scope được hỗ trợ. Không tự thay bằng chụp từng volume/shard theo lịch cron độc lập.

### 19.3. Topology changes và oplog gaps

Các thay đổi:

- Thêm/bớt shard.
- FCV upgrade.
- Thay MongoDB major version.
- Các sự kiện migration lớn.

có thể tạo hạn chế PITR hoặc yêu cầu snapshot nền mới. Kiểm tra restorable ranges và topology compatibility trước restore.

---

## 20. Chọn đúng thời điểm trước thao tác lỗi

Không phải lúc nào sự cố có một timestamp rõ ràng.

Ví dụ:

```text
10:11:58  batch request được gửi
10:12:05  lần update thứ nhất
10:12:17  lần update thứ hai
10:12:40  lần update cuối
10:14:00  alert phát hiện
```

Nếu mục tiêu là **chưa có bất kỳ update lỗi nào**, chọn restore point **trước update đầu tiên** (10:12:05), không dựa vào giờ alert (10:14).

### 20.1. Nguồn xác định ranh giới

- Application logs có correlation ID.
- MongoDB audit logs (nếu được bật).
- Profiling/slow query logs (có giới hạn).
- Job execution timestamps.
- Change Streams event history, nếu còn.
- Oplog timestamp khi có quyền và phương pháp khai thác được hỗ trợ.
- Business records tự lưu `createdAt`, `updatedAt` và version.

### 20.2. UTC và timezone

```text
Asia/Ho_Chi_Minh: UTC+07:00

17:12 local = 10:12 UTC
```

Nếu ứng dụng log giờ local còn Atlas UI chọn UTC, **phải quy đổi**. Không chuyển timestamp theo cách thủ công tùy hứng khi chênh ngày hoặc daylight saving ở vùng khác.

### 20.3. Clock time khác oplog ordering

Wall-clock time cho biết khoảng xảy ra sự kiện; oplog timestamp cho thứ tự logic chính xác hơn trong phạm vi supported restore.

Đừng sử dụng client clock mà không xét clock skew, retries, network latency hoặc transaction commit time.

---

## 21. RPO thực tế: không đồng nghĩa “backup liên tục = zero loss”

Atlas có thể hỗ trợ RPO thấp **đến mức khoảng một phút** theo tài liệu Architecture Center. Nhưng đó là năng lực/khuyến nghị khi hệ thống và window phù hợp, **không là cam kết mọi thời điểm RPO=0**.

Giả sử:

```text
Primary committed last write:      10:20:00
Last backed-up restorable point:   10:18:30

Backup ingestion lag ≈ 90 seconds
```

Nếu phải restore ngay, có thể không có điểm tại 10:19:59.

### 21.1. Các thành phần của RPO

- Backup oplog tailing/ingestion delay.
- Buffer/network/backup service queue.
- Majority commit/replication visibility.
- Oplog gap hoặc backup failure.
- Restore range limitations.
- Thời điểm phát hiện và chọn restore point.

### 21.2. Khác biệt giữa RPO và “thời điểm trước lỗi”

Trong vụ thao tác sai, tổ chức **chủ động chọn PITR trước lỗi** và chấp nhận mất các writes hợp lệ diễn ra sau mốc đó (hoặc phải cherry-pick/reconcile). Đây là business tradeoff, không chỉ do backup quality.

Ví dụ phục hồi tới 10:11, sự cố phát hiện 10:20:

- Có thể mất 9 phút thay đổi hợp lệ sau 10:11.
- Có thể cứu bằng cách trích từ trạng thái trước/các systems khác và replay business events một cách chọn lọc.

---

## 22. RTO thực tế: dữ liệu lớn, replay dài, cutover chậm

RTO phụ thuộc:

1. Dung lượng snapshot và nơi đặt snapshot.
2. Băng thông từ backup storage tới target.
3. IOPS/storage capacity của target.
4. Số replica set members và shards.
5. Lượng oplog cần replay.
6. Index rebuild, nhất là Search/Vector Search.
7. Tốc độ initial sync/replication sau restore.
8. Kiểm tra application, tenants và data invariants.
9. Chuyển traffic và DNS/config.
10. Số lỗi retry, version incompatibility hoặc KMS dependency.

### 22.1. Tính ví dụ minh họa

```text
Snapshot restore:  70 phút
Oplog replay:      25 phút
Validation:        20 phút
Cutover:           15 phút
---------------------------
Total ≈          130 phút
```

Đây là số **giả định**, không phải benchmark MongoDB.

Nếu SLA yêu cầu RTO 60 phút, thiết kế trên **không đạt** dù có PITR 7 ngày.

### 22.2. Giảm RTO

- Tối ưu vị trí snapshot và target region.
- Chọn tier/storage đủ throughput.
- Có infrastructure-as-code để provision target nhanh.
- Diễn tập restore và chuẩn hóa checklist validation.
- Có route traffic/connection string cutover nhanh.
- Quản lý derived indexes và cache warm-up.
- Rà soát snapshot frequency: snapshot gần hơn có thể giảm phần oplog cần replay.

---

## 23. Chọn khôi phục tại chỗ hay vào cluster mới

| Chiến lược | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Restore vào chính production target | Có thể đơn giản về endpoint | Có thể **xóa/ghi đè** dữ liệu đang chạy, downtime cao |
| Restore vào cluster mới | Giữ nguồn cũ để điều tra, so sánh, rollback cutover | Tốn thêm tài nguyên và bước chuyển traffic |
| Restore partial database/collection | Phù hợp khôi phục một phạm vi nhỏ | Dễ lệch consistency với dữ liệu khác |
| Restore ra isolated forensic copy | Giữ chứng cứ và kiểm tra nguồn sự cố | Không trực tiếp đưa ứng dụng trở lại |
| Reconcile/cherry-pick từ restored copy | Cứu dữ liệu chọn lọc, giảm mất thay đổi hợp lệ | Phức tạp, cần business invariants |

### 23.1. Lựa chọn mặc định cho incident thật

Khi chưa rõ phạm vi tác động, **restore vào cluster mới và giữ nguyên nguồn để điều tra** thường giảm nguy cơ làm mất các dữ liệu đang còn khả năng phục hồi.

### 23.2. Đừng kết nối application write traffic ngay sau restore

Một restored cluster nên bắt đầu ở chế độ cô lập, không cho background jobs, stream consumers hoặc payment processors chạy ghi vào dữ liệu chưa được validation.

---

## 24. Runbook: khôi phục trước một thao tác xóa nhầm

Giả sử thao tác sai:

```javascript
db.orders.deleteMany({
  status: "PENDING"
});
```

Lệnh có thể xóa rất nhiều documents. Ví dụ này **chỉ để phân tích incident**, không chạy trên production.

### Pha A — Kiểm soát sự cố

1. Xác nhận action đang gây hại.
2. Dừng job/script hoặc thu hồi credential đang thực hiện thao tác.
3. Ghi nhận UTC time, user, command shape, tenant và phạm vi.
4. Bảo toàn logs, query ID, audit records.
5. Đánh giá có cần chuyển application sang read-only hoặc ngăn writes không.
6. Không xóa snapshot cũ, không tắt Continuous Backup.

### Pha B — Chọn restore point

7. Xác định timestamp của operation **đầu tiên** sai.
8. Xem restorable ranges từ Atlas/Ops Manager.
9. Chọn T trước thao tác sai, theo inclusive/exclusive semantics.
10. Ghi lại lý do chọn T và mức dữ liệu hợp lệ có thể bị mất.

### Pha C — Restore an toàn

11. Tạo target cluster riêng với version/topology/key policy tương thích.
12. Bắt đầu Point-in-Time Restore theo đúng platform.
13. Theo dõi tiến độ, lỗi và chi phí.
14. Giữ target tách khỏi production writes/consumers.

### Pha D — Validation

15. Kiểm tra collections/indexes/users/permissions.
16. Kiểm tra số lượng và trạng thái các orders quan trọng.
17. So sánh transactions/payments/inventory với hệ nguồn khác.
18. Xác định có cần cherry-pick hợp lệ từ giai đoạn sau T.

### Pha E — Cutover

19. Chọn all-or-nothing cutover hoặc phục hồi chọn lọc theo business rules.
20. Stop consumers/jobs có thể replay side effects sai.
21. Chuyển connection/config/traffic có kiểm soát.
22. Kiểm thử các API critical path.
23. Theo dõi lỗi và phục hồi tiến độ xử lý.
24. Lưu audit trail và postmortem.

---

## 25. Phục hồi chọn lọc hay toàn bộ: một bài toán nghiệp vụ

Giả sử:

```text
T = 10:11
10:12: batch sai cập nhật 50.000 orders
10:13: có 100 đơn hàng hợp lệ được tạo
10:14: có 20 giao dịch thanh toán thành công
```

Nếu khôi phục toàn bộ database về 10:11:

- 50.000 updates sai được tránh.
- 100 orders và 20 payments hợp lệ sau T cũng có thể biến mất khỏi MongoDB.
- Bên ngoài MongoDB vẫn có thể đã giao hàng/thu tiền.

### 25.1. Một cách xử lý chọn lọc

1. Restore một **bản sao** tới 10:11.
2. Xác định những documents có trạng thái đúng trong bản sao.
3. Đọc trạng thái hiện hành của production.
4. Áp dụng một chương trình reconciliation có business rules, dry-run và approval.
5. Không tự overwrite toàn bộ `orders`/`payments` từ bản sao nếu có giao dịch hợp lệ mới.
6. Ghi audit từng document thay đổi.

### 25.2. Vì sao PITR không thay undo script?

PITR tạo khả năng phục hồi **một trạng thái lịch sử**. Việc đưa trạng thái đó vào hệ thống hiện tại có thể cần logic nghiệp vụ khác, đặc biệt khi external side effects đã xảy ra.

---

## 26. Kiểm chứng sau restore: không chỉ kiểm countDocuments

Một restore job báo “Completed” không đồng nghĩa business đã khỏe.

### 26.1. Technical validation

- Các databases và collections mong đợi tồn tại.
- Indexes được phục hồi/đang rebuild đúng trạng thái.
- Replica set/sharded cluster healthy.
- Data files/chunks nếu có GridFS.
- Collection validators, users, roles theo phạm vi backup/restore.
- Schema/FCV/version và TTL indexes.
- Tài liệu encrypted key/backup access còn hợp lệ.
- MongoDB Search/Vector Search đã có index definitions và dữ liệu index được rebuild.

### 26.2. Business validation

Ví dụ:

```javascript
// Trên cluster ĐÃ RESTORE, không phải production:
// số orders theo trạng thái
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
```

```javascript
// Tìm orders "PAID" thiếu payment reference theo domain:
db.orders.find({
  status: "PAID",
  paymentId: { $exists: false }
});
```

Đây là **gợi ý invariant**; một hệ thống thật phải có schema và payment contract cụ thể.

### 26.3. Đối soát liên hệ nhiều collection

Cần kiểm tra:

- Đơn hàng PAID có payment event tương ứng.
- Inventory không âm theo policy.
- Contract documents còn owner/tenant references.
- Dữ liệu giữa orders/shipments/payment read models khớp.
- Background jobs đã được tạm dừng đúng và có checkpoint phù hợp.

### 26.4. Lấy mẫu theo tenant và thời gian

Không chỉ kiểm tra 10 documents đầu tiên. Dùng sampling có chủ đích:

- Các tenant lớn.
- Những records ngay trước/sau T.
- High-value transactions.
- Một số records bị tác động bởi incident.
- Bản ghi vừa tạo ở những collection liên quan.

---

## 27. Sau PITR: stream consumers và message brokers

Một consumer có thể giữ **resume token/checkpoint** ở hệ thống khác:

```text
MongoDB PITR đến 10:11
Kafka consumer offset vẫn ở 10:20
Search index snapshot vẫn ở 10:20
External cache vẫn phản ánh 10:20
```

Nếu khôi phục database mà không xử lý các checkpoints, ứng dụng có thể:

- Bỏ qua events cần replay.
- Áp lại events đã xử lý.
- Tạo read model sai.
- Gửi emails/notifications trùng.
- Tạo payments lần hai.

### 27.1. Phân loại checkpoints

- MongoDB Change Stream resume tokens.
- Kafka consumer offsets.
- Outbox/inbox markers.
- Job scheduler last-run timestamps.
- Search indexing checkpoints.
- CDC pipeline offsets.
- Cache generation identifiers.

### 27.2. Kế hoạch sau cutover

1. Đánh giá mỗi checkpoint thuộc snapshot T hay thuộc trạng thái mới hơn.
2. Không cố dùng token của stream lịch sử khác mà không xác minh.
3. Chạy reconciliation hoặc full rebuild read model nếu cần.
4. Giữ idempotency keys cho external effects.
5. Chỉ mở lại consumers sau khi business policy rõ.
6. Theo dõi lag và duplicate handling.

**PITR cho MongoDB không tự khôi phục atomically Kafka, S3, Redis hay payment gateway.**

---

## 28. PITR và các dịch vụ ngoài MongoDB

Trong kiến trúc microservices:

```text
Order Service -> MongoDB
Payment Service -> Payment Gateway
Notification Service -> Email
Search Service -> Search Index
Event Bus -> Kafka
```

Nếu MongoDB phục hồi về T nhưng những systems khác giữ state tại T+10m, có thể phát sinh divergence.

### 28.1. Kịch bản payment đã được charge

1. Payment Gateway đã thu 1.000.000 VND.
2. Order MongoDB được restore trước event payment.
3. Application thấy order ở trạng thái UNPAID.
4. Nếu API tự charge lại, khách có thể bị thu hai lần.

Đúng hơn:

- Query/reconcile transaction với gateway bằng stable payment reference.
- Dùng idempotency key.
- Tạo corrective event/update có audit.
- Không đảo trạng thái gateway nếu chưa có quyết định nghiệp vụ.

### 28.2. Search index/analytics

Có thể rebuild Search/Vector Search từ restored MongoDB state. Tuy nhiên:

- Rebuild mất thời gian.
- Query có thể trả dữ liệu cũ/missing tạm thời.
- Search definitions tại restore point có thể thay thế config hiện tại.
- Nếu còn external index, cần generation/cutover tránh mixing dữ liệu trước và sau T.

---

## 29. Chính sách backup theo RPO/RTO

Một policy chỉ nói “snapshot hàng ngày” là thiếu cho hệ nghiệp vụ quan trọng.

Ví dụ ma trận:

| Cấp dữ liệu | RPO mục tiêu | RTO mục tiêu | Strategy gợi ý |
| --- | --- | --- | --- |
| Thanh toán/đơn hàng critical | 5 phút | 1 giờ | Continuous backup + drills, HA và reconciliation |
| Quản lý tài liệu nội bộ | 1 giờ | 4 giờ | Snapshots thường xuyên + PITR nếu cần |
| Analytics có thể rebuild | 24 giờ | 24 giờ | Snapshots/ETL replay |
| Dev/test dữ liệu giả | Không yêu cầu cao | Không yêu cầu cao | Scheduled backups tùy chi phí |

Các con số trên **chỉ là ví dụ thiết kế SLA**, không phải capability guarantee của một Atlas tier cụ thể.

### 29.1. Một policy đầy đủ cần ghi

```yaml
backupPolicy:
  environment: production
  platform: atlas-core
  enabled: true
  continuousBackup: true
  restoreWindowDays: 7
  snapshotRetention:
    hourlyDays: 7
    dailyDays: 14
    weeklyWeeks: 4
  objectives:
    rpoMinutes: 5
    rtoMinutes: 120
  drills:
    restoreToIsolatedTarget: true
    frequency: monthly
  security:
    accessControl: least-privilege
    encryption: enabled
    restoreAudit: enabled
```

Đây là **manifest kiến trúc ví dụ**, không phải cấu hình Atlas API có thể apply nguyên dạng.

### 29.2. Thiết kế theo dữ liệu và rủi ro

- RPO quan trọng với số lượng writes và giá trị giao dịch.
- RTO phụ thuộc database size, storage, replay và application.
- Retention phụ thuộc khả năng phát hiện lỗi muộn.
- Backup compliance phụ thuộc tổ chức và pháp lý.

---

## 30. Chi phí Continuous Backup

Các thành phần chi phí có thể gồm:

- Snapshot storage.
- Oplog archive storage.
- Backup retention dài.
- Cross-region copy/multi-region distribution.
- Extra traffic và backup service operation.
- Restore target cluster tạm thời.
- Restore/network/IO.
- Search/Vector Search index rebuild.
- KMS access và encryption.
- Diễn tập DR.

### 30.1. High write rate làm oplog archive lớn

Hai clusters có cùng dung lượng dữ liệu hiện tại nhưng tần suất update khác nhau có thể phát sinh chi phí continuous backup khác đáng kể.

```text
Cluster A:
  100 GB stored
  1 GB/day changed

Cluster B:
  100 GB stored
  80 GB/day changed
```

Cả hai có snapshot nền cỡ tương tự nhưng **oplog/changed-data footprint** khác lớn.

### 30.2. Restore window càng dài càng tốn

Nếu giữ 7 ngày thay vì 24 giờ, phải giữ snapshot base và changelog đủ lịch sử. Không chọn retention chỉ vì “càng dài càng an toàn”; cần threat model, compliance và ngân sách.

---

## 31. Backup security: bản sao lưu là tài sản nhạy cảm

Backup thường chứa:

- PII.
- Password hashes.
- Access tokens nếu dữ liệu nghiệp vụ lưu chúng.
- Thanh toán/đơn hàng.
- Tài liệu người dùng.
- Các collections hệ thống/permissions tùy scope.

### 31.1. Controls tối thiểu

1. Mã hóa backup at rest và in transit.
2. Least-privilege cho backup/restore operators.
3. MFA và approval cho destructive restore.
4. Audit khi tạo/xóa/chuyển snapshot.
5. Hạn chế cross-project/cross-region sharing.
6. Retention và deletion protection.
7. Lưu khóa KMS/CMK theo lifecycle riêng.
8. Định kỳ restore thử với đúng key versions.
9. Không copy backup production sang laptop/dev thiếu bảo vệ.
10. Phân biệt quyền **view backup** và quyền **restore/overwrite**.

### 31.2. Với customer-managed keys

Nếu cluster/backup mã hóa bằng CMK:

- Target restore phải có key access đúng.
- Key version cũ có thể cần để decrypt snapshot.
- Disable/delete CMK có thể khiến backup **không restore được**.
- Cross-project restore có thể yêu cầu roles và key permissions ở cả hai phía.
- Không đủ khi chỉ lưu ciphertext mà làm mất key history.

---

## 32. Chống ransomware và backup deletion

Một kẻ tấn công có quyền cao có thể:

- Xóa records trong MongoDB.
- Xóa snapshots hoặc tắt Continuous Backup.
- Thu hồi KMS access.
- Ghi đè restore targets.
- Xóa audit logs.

Do đó, continuous backup phải đi kèm controls chống thay đổi trái phép.

### 32.1. Backup Compliance Policy

Atlas có **Backup Compliance Policy** nhằm hạn chế chỉnh sửa/xóa backups theo yêu cầu quản trị và compliance. Khi bật, một số thao tác giảm PITR restore window đòi quy trình với MongoDB Support và representative được chỉ định.

### 32.2. Phân tách quyền

- Application DB user không nên có quyền quản lý backup.
- Backup Recovery Operator không tự nhiên cần quyền đọc toàn bộ application documents.
- Project Owner/admin access phải được kiểm soát MFA/audit.
- Key administrator và backup operator nên được tách vai trò khi có thể.

### 32.3. Không dùng continuous PITR như defense duy nhất

Cần thêm:

- Multi-region copies.
- Offline/immutable snapshots theo policy.
- Incident detection.
- Restore drills.
- KMS lifecycle protection.
- RBAC, audit, application transaction controls.

---

## 33. Oplog gaps: nguyên nhân và hậu quả

Continuous PITR đòi **liên tục**. Một khoảng oplog bị mất có thể làm không thể khôi phục tới một khoảng thời gian.

### 33.1. Những nguyên nhân thường gặp

- Backup agent ngừng tailing oplog.
- Oplog trên node rollover trước khi agent bắt kịp.
- Network outage hoặc backup storage unavailable.
- Thay đổi sharded cluster topology.
- FCV/major version change.
- Replica set rollback/history discontinuity.
- Backup store thiếu capacity hoặc cấu hình retention không phù hợp.
- Thao tác restore khác ảnh hưởng active backup history.

### 33.2. Timeline có gap

```text
Snapshot 08:00
Oplog archived 08:00 ----- 09:10
                             GAP
Oplog archived 09:40 ----- 12:00

Không thể mặc định restore tới 10:15 bằng
snapshot 08:00 + các entries thiếu 09:10..09:40.
```

### 33.3. Cách xử lý

- Phát hiện gap và ghi incident.
- Không thử replay bỏ qua đoạn thiếu rồi công bố “consistent”.
- Chọn snapshot/restorable range khác theo nền tảng.
- Chờ/đợi snapshot mới được tạo nếu đó là cách phục hồi service.
- Đối soát business data sau restore.
- Mở rộng oplog sizing/tailing capacity để phòng ngừa.

Tài liệu MongoDB troubleshooting cũng nêu những thay đổi FCV/topology có thể tạo khoảng không PITR, cần snapshot mới.

---

## 34. Theo dõi backup health

Một dashboard tối thiểu:

| Metric/Signal | Ý nghĩa |
| --- | --- |
| Last successful snapshot | Snapshot nền mới nhất |
| Snapshot age | Khoảng thời gian từ snapshot tới hiện tại |
| Last archived oplog timestamp | Backup đã ghi lịch sử tới mốc nào |
| Latest restorable point | Mốc mới nhất thực sự có thể restore |
| Earliest restorable point | Mốc sớm nhất còn trong window |
| Oplog ingestion lag | Chênh nguồn/backup |
| Oplog gaps | Những khoảng không thể replay |
| Snapshot retention | Có đủ snapshot nền cho window không |
| Backup agent health | Agent/tailer có đang chạy |
| Backup storage capacity | Tránh hết dung lượng |
| Restore job duration | RTO thực tế |
| Restore failures | Khả năng recovery thực |
| Key/KMS availability | Backup có giải mã được |
| Search index rebuild time | Derived data RTO |
| Last DR drill | Tần suất diễn tập |
| Business validation pass rate | Khôi phục có dùng được không |

### 34.1. Cảnh báo theo RPO

Ví dụ policy:

```text
RPO target: 5 minutes
Alert when:
  latest recoverable point lags primary > 3 minutes
Escalate when:
  lag > 5 minutes or backup stream has a gap
```

Ngưỡng minh họa. Nên cảnh báo **trước** khi vi phạm RPO, không chỉ sau khi backup hoàn toàn thất bại.

### 34.2. Chỉ thấy “Backup Enabled” là chưa đủ

Một cluster có backup bật nhưng:

- Backup agent lỗi.
- Oplog archive lag.
- KMS key invalid.
- Restore window không đủ.
- Snapshots restore fail do version mismatch.

vẫn có thể **không đáp ứng mục tiêu phục hồi**.

---

## 35. Ảnh hưởng của MongoDB version và FCV

Một PITR range có thể đi qua:

- MongoDB major version upgrades.
- FCV transitions.
- Time-series collection format changes.
- Sharded topology changes.
- Search/Vector Search index migrations.

### 35.1. Giới hạn mongorestore liên quan time-series

Tài liệu MongoDB Database Tools hiện hành cảnh báo không replay một oplog range qua chuyển đổi định dạng time-series phát sinh từ thay đổi FCV giữa MongoDB 8.x và 9.0 bằng một lượt bình thường.

Từ Database Tools 100.18.0, công cụ có cơ chế báo lỗi rõ hơn thay vì tạo backup/replay không thể dùng như mong muốn.

Nếu phải restore qua FCV transition, cần làm theo runbook cụ thể cho version, không chỉ thêm `--oplogReplay`.

### 35.2. Không coi backup là portable giữa mọi versions

Một snapshot native storage hoặc Atlas backup có thể có ràng buộc version/topology. Trước một major upgrade:

1. Xác nhận recovery options trước/sau upgrade.
2. Giữ snapshot phù hợp với rollback plan.
3. Kiểm tra target cluster version.
4. Hiểu những PITR windows có thể gián đoạn.
5. Test restore sau upgrade ở staging.

---

## 36. Restore rehearsal — thử để biết có thực sự phục hồi được

Một tổ chức không nên chỉ lần đầu restore khi production đã bị mất dữ liệu.

### 36.1. Diễn tập hàng tháng hoặc theo yêu cầu SLA

Quy trình:

1. Chọn cluster staging/production backup phù hợp.
2. Xác định một thời điểm T cách hiện tại vài giờ/ngày nằm trong window.
3. Tạo target isolated cluster.
4. Trigger PITR.
5. Đo tổng thời gian từ bắt đầu đến ứng dụng đọc được.
6. Xác minh document counts, transactions, indexes.
7. Kiểm tra Search/Vector Search build.
8. Đối soát những documents đã có trước T và chưa có sau T.
9. Kiểm tra TLS/KMS/secrets và app connection.
10. Ghi kết quả, lưu audit, dọn target sau diễn tập.

### 36.2. Kiểm thử thao tác gây hại trên staging

```javascript
// Ví dụ dùng database thử nghiệm tách biệt:
const lab = db.getSiblingDB("pitr_lab");

lab.orders.insertMany([
  { _id: "O100", status: "CREATED" },
  { _id: "O101", status: "PAID" }
]);

// Ghi nhận thời gian/operation marker theo backup platform.
// Sau đó tạo thay đổi trong staging:
lab.orders.updateMany(
  {},
  { $set: { status: "CORRUPTED_IN_TEST" } }
);
```

Mục tiêu diễn tập: restore T trước update, xác nhận statuses đúng như trước thao tác test.

**Không làm bước này trên dữ liệu production.**

### 36.3. Nên giữ evidence nào?

```yaml
restoreDrill:
  date: "2026-11-14"
  sourceCluster: staging-rs
  targetCluster: isolated-dr-test
  platform: atlas-continuous-backup
  chosenRestorePointUtc: "2026-11-14T09:00:00Z"
  restoreJobCompleted: true
  dataValidation: pass
  applicationSmokeTests: pass
  measuredRtoMinutes: 74
  notes: "Example record only; not an Atlas API format."
```

Các field giả định ở trên giúp minh họa báo cáo. Không dùng thông tin giả như một báo cáo phục hồi đã diễn ra thực tế.

---

## 37. Kịch bản DR: hỏng disk, lỗi thao tác và ransomware

### 37.1. Disk/host mất dữ liệu

Mục tiêu: khôi phục từ snapshot gần nhất cùng log lịch sử tới mốc mới nhất khả dụng. Có thể muốn minimize data loss.

### 37.2. Accidental delete/update

Mục tiêu: chọn **trước thao tác sai**; có thể cần reconcile những thay đổi hợp lệ sau đó.

### 37.3. Ransomware/database compromise

Mục tiêu: chọn **trước khi kẻ tấn công làm thay đổi dữ liệu**, không chỉ trước khi alert nổ. Cần forensic timeline, kiểm tra backup có bị nhiễm bẩn/đã bị truy cập không, rotate credentials/key policy và harden target.

### 37.4. Bug ghi dữ liệu âm thầm nhiều ngày

Nếu bug bắt đầu 10 ngày trước, PITR window chỉ 7 ngày có thể **không chứa mốc sạch**. Retention policy phải xét **thời gian phát hiện sai sót**, không chỉ RPO.

Có thể phải dùng monthly snapshots dài hạn hoặc business repair script.

---

## 38. Chọn phương án xử lý trong incident

```text
Sự cố dữ liệu MongoDB
         |
         v
Có Continuous Backup/PITR?
   |                      |
  Có                     Không
   |                      |
   v                      v
Có restorable window     Xác định latest
chứa thời điểm sạch T?   consistent snapshot
   |         |            |
  Có        Không         v
   |         |        Không tự tuyên bố
   v         v        khôi phục được tới T
Chọn T   Dùng snapshot
   |     khác hoặc repair
   v
Restore vào target isolated
   |
   v
Data/application validation
   |
   +--> Failed: chọn T khác,
   |     investigation/retry
   |
   v
Reconcile external systems
   |
   v
Approved cutover
```

Quy trình thực tế còn cần chỉ huy incident, quyền truy cập, approvals và quy định pháp lý liên quan.

---

## 39. Bảng so sánh các phương án backup

| Tính năng | Atlas Cloud Backup snapshots | Atlas Continuous Cloud Backup | Ops Manager PITR | `mongodump --oplog` |
| --- | --- | --- | --- | --- |
| Snapshot nền | Có | Có | Có | Logical dump |
| Oplog liên tục giữa snapshots | Không phải tính năng snapshots thông thường | Có | Có | **Không**, chỉ trong lúc dump |
| Chọn T giữa 2 snapshots | Không mặc định | Có trong window | Có trong window | Chỉ giới hạn nguồn oplog của dump |
| Sharded cluster consistency | Nền tảng hỗ trợ theo policy | Nền tảng hỗ trợ theo policy | Nền tảng hỗ trợ theo policy | Không dùng `--oplog`/`--oplogReplay` như workflow sharded |
| Backup service được vận hành | Atlas | Atlas | Tổ chức/Enterprise | Tổ chức/script |
| Restore automation | Atlas UI/API | Atlas UI/API | Ops Manager/MBRU | CLI |
| Retention dài hạn | Theo snapshot policy | Snapshots + PITR window | Theo snapshot/oplog retention | Theo nơi lưu dump |
| Khả năng tính RPO thấp | Theo chu kỳ snapshots | Có thể rất thấp | Có thể rất thấp nếu đủ điều kiện | Không được bảo đảm |
| Cần test restore | Có | **Có** | **Có** | Có |
| Giới hạn version/FCV | Có | Có | Có | Có |

**Lưu ý:** mục trong bảng là khả năng khái quát. Mọi claim về hỗ trợ phải kiểm tra trên **MongoDB/Atlas/Ops Manager edition, version, tier và topology thực tế**.

---

## 40. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Có snapshot hằng ngày là có PITR.” | Không. Cần snapshot + oplog history liên tục tới T. |
| “Oplog có trên replica set nên tự có backup 7 ngày.” | Oplog nguồn có retention hữu hạn; cần archive riêng. |
| “Continuous Backup có thể phục hồi tới bất kỳ thời điểm nào trong quá khứ.” | Chỉ trong **restorable window** còn dữ liệu hợp lệ. |
| “PITR là backup toàn bộ database mỗi giây.” | Thường là snapshots + replay oplog. |
| “Restore window 7 ngày tức RPO 7 ngày.” | Restore window và RPO là hai khái niệm khác. |
| “RPO thấp thì RTO cũng thấp.” | Restore vẫn mất thời gian snapshot, oplog, validation, cutover. |
| “Bật backup thành công nghĩa có điểm restore tới hiện tại.” | Có ingestion lag/backup gaps. |
| “Tắt Continuous Cloud Backup rồi bật lại vẫn giữ lịch sử.” | Atlas xóa continuous history khi tắt. |
| “Atlas Free/Flex có PITR giống M10+.” | Không mặc định; phải kiểm tra tier hỗ trợ. |
| “Atlas Core và Atlas Infinite có cùng thao tác restore.” | Không; có workflows riêng. |
| “Restore vào production target sẽ không đụng dữ liệu.” | Cluster-level restore có thể xóa dữ liệu trên target. |
| “Backup restore completed thì Search sẵn sàng.” | Search index data có thể phải rebuild. |
| “Chọn 10:12 UTC là tương đương 10:12 giờ Việt Nam.” | Không; phải quy đổi timezone. |
| “Date/Time và oplog Timestamp có cùng độ chính xác.” | Chúng có granularity/semantics khác nhau. |
| “Cứ chọn giờ alert là an toàn.” | Cần chọn trước thao tác sai đầu tiên. |
| “Mọi restore inclusive đúng T.” | Có công cụ loại trừ T, công cụ cho phép đến hết timestamp. |
| “Resume token Change Stream là oplog restore timestamp.” | Hai khái niệm/định dạng khác nhau. |
| “mongodump --oplog tạo continuous backup.” | Chỉ capture oplog khi dump đang chạy. |
| “mongorestore --oplogLimit tự lấy missing oplog.” | Không; chỉ giới hạn entries đã có trong nguồn replay. |
| “mongorestore --oplogReplay hỗ trợ sharded cluster.” | Tài liệu nói không hỗ trợ sharded clusters. |
| “Tự copy oplog.rs là đủ để phục hồi bất kỳ T.” | Không có guarantee consistency/continuity. |
| “Mỗi shard restore độc lập vẫn đảm bảo cluster consistent.” | Không, cần cross-shard coordination. |
| “PITR khôi phục cả Kafka, Redis, payment gateway.” | Không, phải reconcile hệ ngoài. |
| “Ransomware bị xóa là khôi phục snapshot mới nhất được.” | Cần chọn restore point trước lúc compromise, bảo vệ backup. |
| “Backup đã mã hóa thì không cần giữ khóa cũ.” | Old snapshots có thể cần old key versions. |
| “Backup job xanh là không cần DR drill.” | Chỉ restore test chứng minh khả năng phục hồi. |
| “Restore một collection không thể làm sai dữ liệu khác.” | Có thể phá business invariants liên collection. |
| “RTO chỉ là thời gian copy snapshot.” | Gồm replay, rebuild, validation, cutover. |
| “Oplog gap có thể bỏ qua rồi replay tiếp.” | Không bảo đảm consistency, PITR có thể thất bại. |
| “Latest snapshot luôn đúng MongoDB version mới.” | Version/FCV/topology compatibility vẫn phải kiểm tra. |

---

## 41. Checklist production cho Continuous Backup/PITR

1. [ ] Xác định rõ nền tảng: Atlas Core, Atlas Infinite, Ops Manager, Cloud Manager hay self-managed khác.
2. [ ] Kiểm tra edition/tier và tính năng Continuous Backup có được hỗ trợ.
3. [ ] Mỗi production cluster đều có backup policy được bật.
4. [ ] Có snapshot nền hợp lệ trong thời gian lưu cần thiết.
5. [ ] Có oplog archive liên tục, không có gaps.
6. [ ] PIT restore window đủ dài cho thời gian phát hiện sự cố.
7. [ ] Hourly snapshot retention tương thích restore window theo Atlas.
8. [ ] Có alert cho last restorable point và backup lag.
9. [ ] RPO/RTO mục tiêu được phê duyệt bằng business SLA.
10. [ ] Có dashboard backup/snapshot/oplog storage và chi phí.
11. [ ] Có quy trình chọn UTC timestamp trước thao tác lỗi.
12. [ ] Hiểu inclusive/exclusive semantics của công cụ restore.
13. [ ] Có kế hoạch tạo isolated restore target.
14. [ ] Không thực hiện destructive restore vào production target thiếu approval.
15. [ ] Có quyền tối thiểu để tạo restore job và audit.
16. [ ] Có KMS/CMK/key version backup/restore requirements.
17. [ ] Có kiểm tra topology/version/FCV compatibility.
18. [ ] Sharded cluster được restore phối hợp tất cả shards/config metadata.
19. [ ] Có data validation theo business invariants, không chỉ document counts.
20. [ ] Có kế hoạch rebuild Search/Vector Search indexes.
21. [ ] Có reconciliation với payments, queues, caches và external systems.
22. [ ] Có reset/reconcile checkpoints CDC/change streams theo policy.
23. [ ] Có restore rehearsal định kỳ và ghi measured RTO.
24. [ ] Có disaster recovery runbook và escalation owners.
25. [ ] Có bảo vệ backup khỏi accidental deletion/ransomware.
26. [ ] Không tắt Continuous Backup mà không đánh giá mất history.
27. [ ] Retention có xét compliance và khả năng phát hiện lỗi muộn.
28. [ ] Không gọi `mongodump --oplog` là continuous PITR.
29. [ ] Có kiểm tra restore after major upgrade và topology change.
30. [ ] Có dự phòng bandwidth/disk/storage resources cho restore target.
31. [ ] Có post-restore application smoke tests.
32. [ ] Có cutover và rollback-cutover plan.
33. [ ] Có đánh giá ảnh hưởng tới writes hợp lệ sau restore point.
34. [ ] Có accountabilities và evidence lưu lại sau incident.

---

## 42. Bài tập vận dụng có đáp án

### Bài 1 — Snapshot và oplog

Hệ thống có snapshot 08:00, continuous oplog tới 12:00. Batch lỗi lúc 10:12.

**Hỏi:** Có thể khôi phục 10:11 không?

**Đáp án:** Có thể, nếu backup window bao gồm 10:11, oplog giữa 08:00 và T đầy đủ, snapshot nhất quán và nền tảng hỗ trợ.

### Bài 2 — Chỉ có snapshot

Hệ thống có snapshot 08:00 và 12:00, không lưu continuous oplog. Muốn 10:11.

**Đáp án:** Không được khẳng định có thể. Chỉ có restore points từ snapshots hoặc cơ chế khác nếu đã được chuẩn bị.

### Bài 3 — RPO/RTO

Backup archive gần như realtime nhưng restore 2 TB mất 5 giờ.

**Hỏi:** Có thể đạt RPO 5 phút và RTO 30 phút không?

**Đáp án:** RPO có thể thấp, nhưng RTO 30 phút không được đáp ứng nếu restore/validation thực tế mất 5 giờ.

### Bài 4 — Khác nhau giữa window và freshness

Atlas có PITR window 7 ngày, nhưng latest restorable point chậm 15 phút.

**Đáp án:** Có lịch sử 7 ngày không có nghĩa có thể khôi phục tới giây hiện tại. Cần cảnh báo lag và đánh giá vi phạm RPO.

### Bài 5 — Atlas tier

Một cluster Free/Flex muốn bật Continuous Cloud Backup như M10+.

**Đáp án:** Không được giả định hỗ trợ; kiểm tra tier. Hướng dẫn Core PITR được tài liệu mô tả cho M10+ dedicated.

### Bài 6 — Atlas restore vào target có dữ liệu

Target cluster đang chứa 500 GB dữ liệu quan trọng.

**Đáp án:** Cluster-level restore có thể xóa dữ liệu target. Dùng isolated target hoặc có explicit backup/approval trước thao tác.

### Bài 7 — Đổi timezone

Log ứng dụng ở giờ Việt Nam ghi lỗi lúc 17:12 ngày 14/11/2026.

**Hỏi:** UTC time là bao nhiêu?

**Đáp án:** 10:12 UTC ngày 14/11/2026, vì Asia/Ho_Chi_Minh là UTC+07:00.

### Bài 8 — Oplog timestamp

Hai operations có cùng giây nhưng increment 3 và 4.

**Hỏi:** Có thể dùng ISODate một giây để chắc chắn dừng giữa hai operations không?

**Đáp án:** Không. Cần hiểu granularity và ranh giới BSON oplog Timestamp của nền tảng.

### Bài 9 — Ops Manager inclusive/exclusive

Trong Ops Manager, chọn **Point In Time** 12:00.

**Hỏi:** Operation đúng 12:00 có được áp không?

**Đáp án:** Theo tài liệu restore type Point In Time, không; nó chỉ gồm operations trước thời điểm được chọn. Oplog Timestamp có quy tắc tới và bao gồm timestamp khác.

### Bài 10 — Mongodump oplog

`mongodump --oplog` chạy từ 10:00 đến 10:10. User muốn restore 15:59.

**Đáp án:** Dump không tự chứa oplog 10:10–15:59. Không thể lấy bằng `--oplogLimit` nếu không có nguồn archival hợp lệ.

### Bài 11 — mongorestore oplogLimit

Sử dụng `--oplogLimit "1794632400:4"`.

**Hỏi:** Entry có timestamp đúng `(1794632400,4)` được áp không?

**Đáp án:** Không; tool loại entries có timestamp lớn hơn hoặc bằng giới hạn.

### Bài 12 — Sharded cluster

Team snapshot shard A lúc 09:00, shard B lúc 09:02, config server lúc 09:03.

**Đáp án:** Không được bảo đảm cluster-wide consistency. Dùng backup mechanism hỗ trợ sharded snapshots/PITR.

### Bài 13 — Oplog gap

Backup agent lỗi 30 phút và oplog trên node rollover các entries cần thiết.

**Đáp án:** Có thể xuất hiện gap. PITR vào giữa gap không khả dụng; cần snapshot hợp lệ mới hoặc giải pháp khôi phục khác.

### Bài 14 — FCV change

Một PITR range đi qua major version/FCV transition.

**Đáp án:** Kiểm tra compatibility. MongoDB Database Tools có hạn chế đặc biệt khi replay qua time-series format conversion trong một số nâng cấp FCV.

### Bài 15 — Ransomware

Tấn công bắt đầu lúc 09:00 nhưng alert mãi 11:00 mới xuất hiện.

**Hỏi:** Có nên chọn restore 10:59 không?

**Đáp án:** Không mặc định. Phải điều tra thời điểm bắt đầu thay đổi có hại; chọn điểm trước compromise và đối soát.

### Bài 16 — Kafka

MongoDB được restore về 10:11; Kafka consumer offsets vẫn ở 10:20.

**Đáp án:** Phải xây lại/reconcile offsets, outbox/inbox, idempotency và external systems; MongoDB PITR không tự rollback Kafka.

### Bài 17 — Payment Gateway

Thanh toán thành công lúc 10:13, MongoDB restore về 10:11.

**Đáp án:** Không thu tiền lại mù quáng. Đối soát gateway bằng payment reference/idempotency và tạo corrective business events.

### Bài 18 — Search index

Data restore xong nhưng autocomplete không trả kết quả.

**Đáp án:** Search index definitions có thể đã được restore trong khi index data cần mongot initial sync/rebuild. Phải tính cả bước này vào RTO.

### Bài 19 — KMS

Snapshot được mã hóa bằng CMK version cũ đã bị xóa vĩnh viễn.

**Đáp án:** Backup có thể không giải mã được. Key lifecycle/old versions là dependency của restore.

### Bài 20 — Test restore

Team có badge “Backup Healthy” nhưng chưa từng restore test.

**Đáp án:** Chưa có bằng chứng thực tế hệ thống đáp ứng RTO và dữ liệu được validate. Cần DR drill.

### Bài 21 — Disable continuous history

Team muốn tắt Continuous Cloud Backup cuối tuần để tiết kiệm.

**Đáp án:** Atlas xóa continuous backup history khi tắt; đây là thay đổi có thể làm mất PITR window, cần explicit risk acceptance.

### Bài 22 — Bug bị phát hiện muộn

Bug được phát hiện 14 ngày sau khi bắt đầu; PITR window 7 ngày.

**Đáp án:** Restore point sạch có thể nằm ngoài window. Cần long-retention snapshots, application repair hoặc nguồn lịch sử khác.

### Bài 23 — Selected collection restore

Collection `orders` được PITR về T, `payments` giữ trạng thái hiện tại.

**Đáp án:** Có thể sai invariants. Cần xét cross-collection consistency hoặc reconciliation.

### Bài 24 — Bắt đầu query sau restore

API kết nối target restored rồi lập tức bật toàn bộ background workers.

**Đáp án:** Nguy hiểm. Phải xác minh version/tenant/ràng buộc, xử lý checkpoints và side effects trước khi mở write traffic.

---

## 43. Tài liệu MongoDB chính thức

- [MongoDB Atlas — Back Up Your Cluster](https://www.mongodb.com/docs/atlas/backup/cloud-backup/overview/): Cloud Backup, feature availability và backup requirements.
- [MongoDB Atlas — Recover a Point In Time with Continuous Cloud Backup](https://www.mongodb.com/docs/atlas/recover-pit-continuous-cloud-backup/): continuous restore window, date/time và oplog timestamp, quy trình.
- [MongoDB Atlas Core — Restore from Continuous Cloud Backup](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-from-continuous/): restore process, selected data, roles, topology, Search rebuild.
- [MongoDB Atlas — Manage Backup Policies](https://www.mongodb.com/docs/atlas/backup/cloud-backup/configure-backup-policy/): snapshot retention và PITR restore window.
- [MongoDB Atlas — Dedicated Cluster Backups](https://www.mongodb.com/docs/atlas/backup/cloud-backup/dedicated-cluster-backup/): snapshots, oplog storage, consistency và restore behavior.
- [MongoDB Atlas — Restore Your Cluster](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-overview/): yêu cầu stop clients, target cluster và restore constraints.
- [MongoDB Atlas Architecture Center — Guidance for Atlas Backups](https://www.mongodb.com/docs/atlas/architecture/current/backups/): lựa chọn RPO/RTO, continuous backup và tối ưu restore.
- [MongoDB Atlas — Operational Readiness Checklist](https://www.mongodb.com/docs/atlas/architecture/current/operational-readiness-checklist/): backup policy và DR recommendations.
- [MongoDB Ops Manager — Restore Overview](https://www.mongodb.com/docs/ops-manager/current/tutorial/nav/restore-overview/): snapshot/PITR với MBRU.
- [MongoDB Ops Manager — Restore Replica Set](https://www.mongodb.com/docs/ops-manager/current/tutorial/restore-replica-set/): restore types và timestamp semantics.
- [MongoDB Ops Manager — Restore Sharded Cluster](https://www.mongodb.com/docs/ops-manager/current/tutorial/restore-sharded-cluster/): cross-shard consistency và workflow.
- [MongoDB Ops Manager — Backup FAQ](https://www.mongodb.com/docs/ops-manager/current/reference/faq/faq-backup/): oplog store, PITR retention/FCV và troubleshooting.
- [MongoDB — Troubleshoot Backup and Restore Failures](https://www.mongodb.com/docs/manual/troubleshooting/backup-restore-failures/): oplog gaps, version/topology issues.
- [MongoDB — Backup Methods for Self-Managed Deployments](https://www.mongodb.com/docs/manual/core/backups/): Cloud Manager/Ops Manager, filesystem snapshots, mongodump.
- [MongoDB Database Tools — mongodump](https://www.mongodb.com/docs/database-tools/mongodump/): `--oplog` và những giới hạn.
- [MongoDB Database Tools — mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/): `--oplogReplay`, `--oplogLimit` và sharded limitations.
- [MongoDB Database Tools — mongorestore Behavior and Usage](https://www.mongodb.com/docs/database-tools/mongorestore/mongorestore-behavior-access-usage/): FCV/time-series conversion, rollback và restore failure.
- [MongoDB — Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/): rollover, sizing và oplog behavior.
- [MongoDB Atlas — Backup Compliance Policy](https://www.mongodb.com/docs/atlas/backup/cloud-backup/backup-compliance-policy/): chống chỉnh sửa/xóa backup theo policy.

Các chi tiết **feature/tier**, granularity của điểm khôi phục, retention, tương thích server/FCV và thủ tục restore có thể thay đổi theo phiên bản. Đối chiếu tài liệu ứng với **Atlas Core/Infinite, Ops Manager, Cloud Manager, Server và MongoDB Database Tools** đang sử dụng trước khi áp dụng vào sản xuất.

## 44. Kết luận

**Sao lưu liên tục trong MongoDB** có ý nghĩa khi nền tảng lưu được **snapshot nền cùng chuỗi oplog đầy đủ** và có công cụ áp dụng thay đổi đến một **restore point T** nằm trong window.

- Với **Atlas Core M10+**, có thể dùng **Continuous Cloud Backup** và **Point-in-Time Restore**, theo cấu hình restore window, backup policy và các giới hạn edition/topology.
- Với **Atlas Infinite**, cần dùng workflow riêng, không suy ra giống Atlas Core.
- Với **self-managed Enterprise**, **Ops Manager/Cloud Manager** hỗ trợ snapshot + oplog với PITR nếu được triển khai và cấu hình đúng.
- Với **mongodump --oplog** hoặc filesystem snapshots đơn thuần, không được mặc định có PITR liên tục; chúng phục vụ những điểm khôi phục/cơ chế consistency khác nhau.

**RPO** đo mức mất dữ liệu chấp nhận được; **RTO** đo thời gian phục vụ trở lại; **restore window** đo khoảng lịch sử có thể chọn. Ba thông số không thay thế nhau.

Khôi phục an toàn đòi hỏi **chọn đúng thời điểm trước lỗi, không có oplog gap, restore vào target cô lập, kiểm chứng dữ liệu, quản lý KMS/backup permissions và đối soát với hệ thống ngoài** trước khi chuyển traffic.

**Có backup chưa đủ; chỉ khi restore được đúng mốc, đúng dữ liệu, trong thời gian SLA và không gây tác dụng phụ mới thì chiến lược PITR mới thực sự hữu ích.**
