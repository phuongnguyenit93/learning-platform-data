# Phân biệt sao chép nhiều bản với sao lưu có thể phục hồi

Một hệ thống NoSQL có ba bản sao dữ liệu ở ba máy chủ vẫn có thể mất dữ liệu. Nếu ứng dụng chạy một lệnh xóa nhầm, cả ba bản sao có thể nhận và áp dụng cùng lệnh xóa. Khi ấy cluster vẫn khỏe, các replica đồng bộ tốt, nhưng dữ liệu nghiệp vụ đã biến mất.

Đây là lý do phải phân biệt **replication (sao chép nhiều bản)** và **backup (sao lưu có thể phục hồi)**:

- **Replication** duy trì một hoặc nhiều bản sao của **trạng thái đang hoạt động**, phục vụ tính sẵn sàng, chịu lỗi node/zone, đôi khi hỗ trợ đọc và giảm thời gian gián đoạn.
- **Backup** bảo quản những **trạng thái có thể khôi phục**, thường theo các điểm thời gian hoặc chuỗi snapshot + log, để cứu dữ liệu khi trạng thái hiện hành bị hỏng, xóa nhầm hoặc không còn đáng tin.

Replication và backup có thể cùng sử dụng thao tác sao chép dữ liệu, nhưng mục đích, thời gian giữ, phạm vi lỗi được bảo vệ và cách phục hồi khác nhau. Muốn hệ thống bền vững, không chỉ hỏi “có mấy bản dữ liệu?” mà còn hỏi “có thể phục hồi trạng thái đúng tại thời điểm nào, trong bao lâu và dưới những loại sự cố nào?”.

Bài học thuộc chủ đề **Lưu trữ và độ bền** của **Database No SQL**. Các ví dụ lấy từ MongoDB, Cassandra, DynamoDB và Redis. Chi tiết lệnh, backup tooling, retention và khả năng PITR phụ thuộc phiên bản, gói dịch vụ và topology cụ thể.

## 1. Sao chép nhiều bản giải quyết điều gì?

Giả sử một replica set có một primary và hai secondary:

~~~text
              Application
                   |
                   v
               Primary A
                 /   \
                v     v
        Secondary B  Secondary C
~~~

Khi một node hỏng, hệ quản trị có thể sử dụng node còn sống, bầu leader hoặc tiếp tục đáp ứng yêu cầu theo cơ chế quorum/failover đã cấu hình.

Replication thường giúp:

1. **Khả dụng:** giảm gián đoạn khi một hoặc vài node lỗi.
2. **Chịu lỗi phần cứng:** không phụ thuộc vào đúng một ổ đĩa hoặc máy.
3. **Mở rộng đường đọc:** một số hệ có thể đọc từ replica, với đánh đổi về độ mới.
4. **Phân bố dữ liệu theo vùng:** giảm rủi ro mất một zone hoặc region theo thiết kế.
5. **Duy trì dữ liệu được xác nhận:** write acknowledgment/quorum góp phần vào độ bền dưới fault model cụ thể.

Nhưng replication thường **không giữ mãi trạng thái cũ sau khi một thay đổi hợp lệ được áp dụng**. Lệnh xóa được sao chép cũng là một thao tác của hệ thống.

### Một số mô hình replication

| Mô hình | Ý tưởng | Điều cần kiểm tra |
|---|---|---|
| Primary–secondary | Một leader phục vụ ghi, các node còn lại theo dõi | Failover, lag, rollback, write concern |
| Leaderless / quorum | Nhiều replica phối hợp đọc/ghi | Consistency level, read repair, conflict |
| Multi-writer | Nhiều nơi cùng nhận ghi | Conflict resolution, ordering |
| Synchronous | Chờ một số xác nhận trước khi trả thành công | Latency, durability và phạm vi quorum |
| Asynchronous | Replica tiếp nhận thay đổi sau | Lag và write gần nhất có thể mất khi failover |
| Cross-region | Sao sang vùng địa lý khác | Latency, chi phí và lỗi logic lan truyền |

Số lượng replica không tự quyết định bảo đảm an toàn của từng write. Cần đọc giao thức và cấu hình acknowledgement của hệ quản trị.

## 2. Backup là gì?

**Backup** là tập dữ liệu, bản chụp và thông tin đi kèm được lưu để **dựng lại trạng thái dữ liệu** sau sự cố. Nó có thể là:

- Full snapshot của database ở một điểm phù hợp.
- Incremental backup ghi những thay đổi sau bản trước.
- Differential backup so với full backup gần nhất.
- Chuỗi log có thể phát lại tới một mốc thời gian.
- Logical export có thể import trở lại.
- Physical backup gồm data files/blocks và metadata cần thiết.
- Managed backup của nhà cung cấp, với API restore và recovery window rõ.

Backup thường không trực tiếp phục vụ truy vấn người dùng. Nó cần retention, bảo vệ quyền xóa, kiểm tra tính nguyên vẹn và **quy trình restore đã được thử**.

### Khi nào mới có thể nói “backup dùng được”?

Không đủ khi hệ thống báo “job backup succeeded”. Cần trả lời:

1. Bản backup có đủ collection/table, schema và metadata không?
2. Nó có nhất quán với các transaction hoặc shard không?
3. Có thể giải mã bằng các key còn truy cập được không?
4. Backup còn tồn tại nếu production account hoặc cluster bị mất không?
5. Có thể phục hồi tới những thời điểm nào?
6. Phần mềm và phiên bản nào có thể đọc nó?
7. Có thể khởi động ứng dụng trên dữ liệu restore không?
8. Sau restore có thể đối soát tính đúng đắn nghiệp vụ không?
9. Thời gian restore thực tế có đạt mục tiêu không?

Một file còn tồn tại nhưng không mở được, thiếu log hoặc mất khóa giải mã không phải phương án phục hồi hữu ích.

## 3. Bảng đối chiếu replication và backup

| Khía cạnh | Replication | Backup |
|---|---|---|
| Mục tiêu | Khả dụng và duy trì trạng thái hiện hành | Khôi phục trạng thái ở thời điểm được chọn |
| Dữ liệu được sao | Các thay đổi đang hoạt động | Snapshot/log hoặc điểm phục hồi lịch sử |
| Xóa nhầm | Thường lan truyền xóa | Có thể quay về trước lúc xóa |
| Lỗi logic | Có thể nhân bản dữ liệu sai | Có thể giữ trạng thái sạch trước lỗi |
| Node hỏng | Có thể failover nhanh | Có thể restore nhưng tốn thời gian |
| Khả năng đọc trực tiếp | Một số replica phục vụ truy vấn | Thường không phải đường đọc production |
| Độ trễ chính | Replication lag, failover | Backup lag, restore time |
| Cách ly lỗi | Phụ thuộc topology | Cần storage/identity độc lập |
| Khả năng giữ lịch sử | Không mặc định | Là mục đích quan trọng |
| Số đo | Health, lag, quorum, availability | RPO, RTO, restore success, retention |
| Có thay thế nhau? | Không | Không |

Replication giúp **tiếp tục chạy** trong nhiều sự cố node. Backup giúp **quay lại dữ liệu đúng** khi các bản dữ liệu đang chạy không còn đúng.

## 4. Ví dụ xóa nhầm được nhân bản hoàn hảo

Một công ty dùng MongoDB replica set ba member cho collection `orders`. Vào 15:00, một script vô tình xóa tất cả Order của tenant `shop-17`.

~~~javascript
// Tình huống minh họa nguy hiểm — KHÔNG thực thi.
db.orders.deleteMany({ tenantId: "shop-17" });
~~~

Dòng thời gian:

~~~text
14:55  Có điểm phục hồi dữ liệu trước khi lỗi
15:00  Primary chấp nhận lệnh deleteMany sai
15:00+ Secondary B áp dụng thao tác xóa
15:00+ Secondary C áp dụng thao tác xóa
15:03  Đội vận hành phát hiện dữ liệu biến mất
~~~

Lúc 15:03, cluster có thể:

- Vẫn có ba node khỏe mạnh.
- Không có replication lag đáng kể.
- Đạt write concern theo cấu hình.
- Tiếp tục trả request bình thường.

Tuy nhiên **cả ba bản sao đều chứa trạng thái đã xóa**. Chuyển leader sang B hoặc C không phục hồi những Order đó nếu lệnh xóa đã được áp dụng.

Backup/PITR có thể giúp phục hồi trạng thái trước 15:00, với điều kiện điểm trước lỗi còn nằm trong recovery window và artifact có thể restore.

### Bài học

Replication thường sao chép **điều database được yêu cầu làm**, không kiểm tra mọi thao tác có phù hợp ý định nghiệp vụ của con người hay không. Backup tạo **lối quay về trước một quyết định sai**.

## 5. Threat model: bảo vệ loại sự cố nào?

| Sự cố | Replication | Backup | Điều cần chú ý |
|---|---|---|---|
| Một ổ đĩa hỏng | Thường có ích | Có ích | Replica có thể giảm gián đoạn |
| Một node chết | Thường có ích | Có ích | Failover thường nhanh hơn restore |
| Một availability zone lỗi | Nếu đủ zone/quorum | Nếu lưu ngoài fault domain | Kiểm tra topology |
| Cả region không hoạt động | Cross-region nếu đã thiết kế | Backup ở region khác | Quy trình DR cần thử |
| Xóa nhầm một collection | Thường không | Có nếu còn điểm sạch | Có thể cần selective restore |
| Migration ghi dữ liệu sai | Trạng thái sai có thể lan truyền | Có thể quay về trước migration | Data consistency |
| Bug âm thầm ghi sai nhiều ngày | Không | Chỉ khi retention đủ dài | Detection window |
| Ransomware | Replica có thể cùng bị ảnh hưởng | Chỉ nếu cô lập và bảo vệ | IAM, immutability |
| Credential bị chiếm | Có thể xóa mọi replica | Có thể mất nếu cùng quyền | Control-plane isolation |
| Mất khóa mã hóa | Không giải mã dữ liệu liên quan | Backup vô dụng nếu mất khóa | Key recovery |
| Lỗi search index | Có thể rebuild | Có thể restore/rebuild | RTO cho projection |
| Mất cả cluster và backup trong cùng môi trường | Không | Không | Cần tách fault domain |

Thiết kế cần chọn nhiều lớp bảo vệ theo loại sự cố, không dựa vào một khẩu hiệu “dữ liệu luôn an toàn”.

## 6. Fault domain và lỗi chung

**Fault domain** là phạm vi có thể cùng bị ảnh hưởng: disk, node, rack, availability zone, region, tài khoản cloud, nhà cung cấp hoặc control plane.

Ba replica đặt trên ba node cùng một rack có thể cùng mất điện. Ba replica trên các zone khác nhau có thể chống một lỗi zone tốt hơn, nhưng vẫn có thể nhận cùng thao tác xóa sai.

Một backup lưu ngay trong cùng tài khoản quản trị với quyền xóa không hạn chế có thể cùng bị mất nếu tài khoản đó bị chiếm quyền.

Cần xem cả:

- **Physical fault domain:** phần cứng, mạng, vị trí.
- **Logical fault domain:** ứng dụng, dữ liệu sai, migration.
- **Administrative fault domain:** tài khoản và quyền xóa.
- **Security fault domain:** credential, key, ransomware.
- **Operational fault domain:** script automation và con người.

**Khoảng cách địa lý giúp trước một số lỗi vật lý, nhưng không tự cách ly lỗi logic hay tài khoản bị compromise.**

## 7. Replication lag không phải retention

Hai thông số dễ bị nhầm:

~~~text
Replication lag: 2 giây
Backup retention: 30 ngày
~~~

**Replication lag** đo khoảng chậm giữa replica với nguồn theo semantics của engine.

**Backup retention** cho biết những điểm hoặc chuỗi dữ liệu phục hồi được lưu trong thời gian nào.

Lag bằng 0 có thể nghĩa mọi replica đã nhận lệnh xóa sai. Retention 30 ngày có thể giữ nhiều điểm trước lỗi, nhưng **không hứa restore mất 2 giây**.

Với backup còn cần phân biệt:

- Lịch tạo backup.
- Latest recoverable point.
- Recovery window.
- Retention policy.
- Restore throughput.
- RPO và RTO.

## 8. Write acknowledgment và durability không phải PITR

Trong NoSQL, các thiết lập như write concern, quorum, journaling, WAL/AOF, consistency level và số replica có thể quyết định một write được xác nhận khi nào và có khả năng sống sót qua crash/failover ra sao.

Những thiết lập này quan trọng nhưng **khác khả năng quay lại dữ liệu cũ**.

Ví dụ một lệnh sai:

~~~javascript
db.products.updateMany(
  { tenantId: "shop-17" },
  { $set: { status: "INACTIVE" } }
);
~~~

Nếu lệnh được xác nhận và bền vững trên nhiều replica, dữ liệu sai có thể tồn tại rất chắc chắn. Durability là đặc tính **giữ được write**, không tự quyết định **write đó có đúng nghiệp vụ**.

Muốn phục hồi trạng thái trước lệnh sai cần backup, event/audit đủ đầy và quy trình rollback/reconciliation đáng tin cậy.

## 9. Các loại backup thường gặp

### Full backup

Chứa một tập dữ liệu hoàn chỉnh tại một điểm nhất quán được hỗ trợ. Nó thường là nền cho các bản incremental hoặc log.

### Incremental backup

Chứa những thay đổi kể từ bản backup/checkpoint trước theo định nghĩa công cụ.

~~~text
Sunday: Full F0
Monday: Incremental I1
Tuesday: Incremental I2
Wednesday: Incremental I3
~~~

Restore Wednesday có thể cần `F0 + I1 + I2 + I3`. Nếu một phần chuỗi bị thiếu, trạng thái cuối có thể không khôi phục được.

### Differential backup

Chứa thay đổi từ bản full gần nhất:

~~~text
Sunday: Full F0
Monday: Differential D1 (so với F0)
Tuesday: Differential D2 (so với F0)
Wednesday: Differential D3 (so với F0)
~~~

Restore Wednesday có thể dùng `F0 + D3`. Dung lượng differential có thể tăng dần cho tới lần full mới.

### Continuous log backup

Lưu những thay đổi có thứ tự sau base snapshot, phục vụ một dạng point-in-time recovery nếu công cụ có hỗ trợ replay nhất quán.

**Các tên gọi có thể khác giữa sản phẩm.** Một managed backup service có thể lưu incremental blocks nhưng hiển thị cho người dùng một dải điểm phục hồi liên tục.

## 10. Snapshot không mặc nhiên là backup độc lập

Snapshot có thể được tạo ở cấp:

- Volume/virtual disk.
- File system.
- Database engine.
- Managed cloud storage.
- Collection hoặc logical export.
- Snapshot nền cho PITR.

Một snapshot chỉ nằm trong cùng storage account, có thể bị xóa bởi credential production hoặc thiếu log cần để database startup thì chưa đủ an toàn.

Cần hỏi:

1. Snapshot **crash-consistent** hay **transaction-consistent**?
2. Các volume/shard có cùng checkpoint không?
3. Có WAL/oplog/metadata để recovery không?
4. Có thể restore khi nguồn mất hoàn toàn không?
5. Có cơ chế chống xóa ngoài ý muốn không?
6. Khóa mã hóa có còn tồn tại không?
7. Có thử khởi động engine với snapshot chưa?

### Crash-consistent và application-consistent

Một volume snapshot có thể tương đương trạng thái sau khi máy đột ngột mất điện. Database có cơ chế crash recovery nếu snapshot hợp lệ theo yêu cầu công cụ và đủ các file/log.

**Application-consistent** còn cần dữ liệu qua nhiều collection hoặc dịch vụ không vi phạm invariant nghiệp vụ. Chụp Order DB lúc 09:02 và Payment DB lúc 09:00 không tự tạo được một ảnh chụp logic thống nhất cho toàn nghiệp vụ.

Không copy tùy tiện thư mục dữ liệu đang mở của database rồi mặc định backup có thể dùng được.

## 11. Point-in-time recovery (PITR)

**PITR** là khả năng phục hồi tới một thời điểm được chọn trong recovery window mà dịch vụ/công cụ hỗ trợ.

Ví dụ:

~~~text
01:00  Base snapshot B0
01:00–08:42  Archived changes/log
08:43  Lệnh xóa nhầm
~~~

Nếu có snapshot hợp lệ và chuỗi log đủ, hệ thống có thể phục hồi trạng thái **trước 08:43**, theo độ hạt/thời điểm mà công cụ hỗ trợ.

Một PITR workflow thường cần:

1. Base backup hợp lệ.
2. Chuỗi log/changes liên tục.
3. Metadata checkpoint và transaction ordering.
4. Replay đúng tới điểm mục tiêu.
5. Cách giải quyết multi-shard consistency.
6. Kiểm tra database sau restore.

**PITR không mặc nhiên hỗ trợ mọi mili giây trong quá khứ.** Phạm vi thời gian, độ hạt và tính nhất quán phải theo API của dịch vụ cụ thể.

## 12. Oplog, WAL, CDC và backup log không đồng nhất

| Cơ chế | Mục đích chính | Tự đủ làm backup dài hạn? |
|---|---|---|
| WAL/journal | Crash recovery, durability | Không |
| MongoDB oplog | Replication của replica set | Không |
| CDC/change stream | Quan sát/chuyển những thay đổi | Không |
| Event bus | Tích hợp dịch vụ, truyền sự kiện | Không |
| Audit log | Theo dõi thao tác/đối soát | Không |
| Log archive phục vụ PITR | Giữ chuỗi thay đổi để restore | Là một thành phần của PITR |

Oplog hoặc event stream có thể bị giới hạn retention, không chứa đủ base state, không ghi đầy đủ metadata hoặc không có tính nhất quán cần cho replay. Phải có **công cụ backup chủ động thu thập và bảo quản** những thành phần cần thiết.

Một event bus lưu `OrderConfirmed` không nhất thiết chứa đầy đủ dữ liệu của mọi Order để dựng lại database. Event sourcing có thể thiết kế khả năng replay có chủ đích, nhưng nó không tự xuất hiện chỉ vì hệ thống sử dụng event.

## 13. RPO là gì?

**Recovery Point Objective (RPO)** là mục tiêu khoảng mất dữ liệu tối đa được chấp nhận khi phục hồi theo fault scenario đã định nghĩa.

Ví dụ:

- RPO = 15 phút: mong muốn có thể phục hồi tới một điểm không quá 15 phút trước sự cố.
- RPO = 1 giờ: có thể chấp nhận mất thay đổi hợp lệ gần nhất tới một giờ.
- RPO gần 0: đòi bảo đảm và kiến trúc nghiêm ngặt hơn; chi phí/rủi ro phải được xác định rõ.

Nếu chỉ full backup lúc 00:00, sự cố xảy ra 23:59 có thể khiến các thay đổi hợp lệ gần 24 giờ không còn trong backup.

Một phép đo khái niệm:

\[
\text{Observed recovery gap}
=
\text{Failure time}
-
\text{Latest valid recoverable point}
\]

Cần nhấn mạnh **valid**. Backup mới nhất có thể chứa dữ liệu sai do bug, khi ấy phải chọn một điểm xa hơn mới còn đúng.

RPO là **mục tiêu**, không phải điều tự được đảm bảo chỉ vì đã bật backup.

## 14. RTO là gì?

**Recovery Time Objective (RTO)** là mục tiêu thời gian để dịch vụ trở lại mức hoạt động chấp nhận được sau một sự cố theo định nghĩa của tổ chức.

Nó có thể bao gồm:

1. Phát hiện và phân loại incident.
2. Chặn thao tác đang phá dữ liệu.
3. Chọn điểm restore.
4. Khởi tạo môi trường an toàn.
5. Tải và giải mã backup.
6. Restore base, replay log.
7. Dựng index và config cần thiết.
8. Kiểm tra consistency và invariant.
9. Chuyển traffic.
10. Theo dõi sau cutover.

Ví dụ một backup 5 TB phục hồi được nhưng cần 8 giờ dựng lại. Nếu RTO là 30 phút, hệ thống chưa đạt mục tiêu dù dữ liệu cuối cùng vẫn có thể lấy lại.

### RPO và RTO trả lời hai câu hỏi khác nhau

| Mục tiêu | Câu hỏi |
|---|---|
| RPO | Có thể mất bao nhiêu thay đổi mới nhất? |
| RTO | Dịch vụ ngừng hoạt động tối đa bao lâu? |
| Retention | Có thể quay lại bao xa trong lịch sử? |
| Replication lag | Replica đang chậm trạng thái nguồn bao nhiêu? |

RPO thấp **không tự động** dẫn đến RTO thấp. Recovery gần thời điểm lỗi vẫn có thể tốn nhiều giờ.

## 15. Ví dụ xác định chiến lược theo RPO/RTO

Hệ Order có mục tiêu:

~~~yaml
objectives:
  rpoMinutes: 15
  rtoMinutes: 240
  recoveryWindowDays: 30
data:
  size: "2 TB"
  type: businessCritical
~~~

Một chiến lược có thể gồm:

- Replica trải các availability zone để chịu lỗi node/zone.
- Full/base backup ở mốc phù hợp.
- Continuous log capture hoặc incremental theo khả năng để đáp ứng RPO.
- Lưu backup trong fault/control domain tách biệt.
- Mã hóa, immutable retention và key recovery.
- Tự động hóa restore hạ tầng và dữ liệu.
- Restore drill định kỳ với 2 TB thật hoặc mẫu đại diện được kiểm chứng.
- Số liệu latest recoverable point và actual recovery time.

Không thể kết luận chỉ từ YAML rằng lịch backup nào chắc chắn đạt mục tiêu. Cần đo throughput network, restore, index, log replay và đối soát trong môi trường thật.

## 16. Retention phải tính tới lỗi phát hiện muộn

Giả sử một bug ghi sai giá bắt đầu ngày 01/11 nhưng tới 20/11 mới phát hiện. Nếu backup chỉ giữ 7 ngày, mọi điểm còn lại có thể đã chứa dữ liệu sai.

Do đó retention cần cân nhắc:

- Thời gian tối đa một lỗi có thể âm thầm tồn tại.
- Chu kỳ đối soát và kiểm toán.
- Chính sách dữ liệu cá nhân và yêu cầu xóa/ẩn.
- Tài nguyên lưu trữ và chi phí.
- Nhu cầu khôi phục giao dịch lịch sử.
- Khả năng rollback migration.
- Thời gian còn lưu base + log chain.

**Backup mới nhất không luôn là backup tốt nhất** cho một lỗi logic. Cần xác định điểm dữ liệu **cuối cùng còn đúng**.

## 17. 3-2-1-1-0 là heuristic, không phải bảo đảm

Một quy tắc tham khảo thường được áp dụng trong bảo vệ dữ liệu:

- **3** bản dữ liệu theo mô hình bảo vệ.
- **2** loại lưu trữ hoặc fault domain khác nhau.
- **1** bản ở địa điểm khác.
- **1** bản immutable/offline hoặc được cô lập để tránh xóa đồng thời.
- **0** lỗi chưa được phát hiện nhờ kiểm tra/restore.

Không nên đếm máy rồi tuyên bố an toàn. Ba replica cùng nhận DELETE không phải ba điểm lịch sử. Ba backup cùng tài khoản với một quyền xóa toàn bộ vẫn có lỗi chung.

Cốt lõi là **độc lập về rủi ro, có lịch sử, có thể giải mã, có thể phục hồi và đã được kiểm chứng**.

## 18. Cô lập backup khỏi production

Một mô hình bảo vệ:

~~~mermaid
flowchart TD
    A["Production NoSQL cluster"] --> B["Replica trong nhiều AZ"]
    A --> C["Backup job / CDC log archive"]
    C --> D["Recovery vault/account riêng"]
    D --> E["Immutable retention"]
    D --> F["Isolated restore environment"]
~~~

Các lớp kiểm soát:

- Tách tài khoản/kho backup khỏi quyền ứng dụng production.
- Dùng least-privilege IAM cho backup writer.
- Hạn chế tài khoản có thể xóa hoặc rút ngắn retention.
- Dùng immutable/WORM policy khi phù hợp.
- Kiểm soát truy cập và audit hoạt động restore.
- Có emergency access được phê duyệt và thử.
- Không để một secret bị lộ có thể xóa cả production lẫn backup.

**Versioning trên object storage không mặc nhiên tương đương immutable backup** nếu credential vẫn xóa được mọi version hoặc kho lưu.

## 19. Immutable backup và ransomware

Ransomware có thể mã hóa/xóa dữ liệu đang chạy và cố phá backup. Một bản backup immutable được cấu hình đúng có thể giảm khả năng bị xóa trước hạn.

Nhưng vẫn còn các rủi ro:

- Bản backup được tạo sau khi dữ liệu đã bị hỏng.
- Key mã hóa bị mất.
- Tài khoản có quyền quản trị đặc biệt phá được policy tùy chế độ.
- Backup có thời hạn quá ngắn.
- Khôi phục vào môi trường còn bị compromise.
- Các bản copy chứa dữ liệu cá nhân không được quản lý retention theo chính sách.

Immutability là một lớp bảo vệ, không thay thế khả năng **xác định điểm sạch và restore an toàn**.

## 20. Mã hóa và quản lý khóa

Backup có thể chứa nhiều dữ liệu nhạy cảm hơn một API thông thường. Nên dùng:

- Mã hóa khi truyền và khi lưu.
- Quản lý key có quyền tối thiểu.
- Rotation policy phù hợp.
- Audit mọi truy cập backup/key.
- Kế hoạch khôi phục quyền dùng key trong sự cố.
- Kiểm thử decrypt bằng cùng quy trình emergency thực tế.
- Không để key chỉ tồn tại trong production đã có nguy cơ mất.

Một backup có checksum đúng nhưng khóa giải mã bị xóa vĩnh viễn **không còn phục hồi được**. Do đó key management thuộc chiến lược durability.

## 21. Backup phải nhất quán theo nghiệp vụ

Giả sử có ba collection:

~~~text
orders
payments
inventoryReservations
~~~

Tại:

~~~text
09:00:00  Payment = PENDING, Order = PENDING
09:00:01  Payment = SUCCEEDED
09:00:02  Order = CONFIRMED
~~~

Nếu backup `orders` lúc 09:02 nhưng `payments` lúc 09:00, sau restore có thể là:

~~~text
Order = CONFIRMED
Payment = PENDING
~~~

Cả hai bản có thể đọc được và checksum đúng, nhưng **tập trạng thái chưa nhất quán**.

### Các mức nhất quán

| Mức | Ý nghĩa |
|---|---|
| File-level | Các file/khối được snapshot theo cơ chế storage |
| Crash-consistent | Database có thể phục hồi sau tình huống tương đương crash |
| Transaction-consistent | Transaction trong phạm vi hỗ trợ không bị cắt dở |
| Cross-shard consistent | Các shard và metadata cùng thuộc một trạng thái được hỗ trợ |
| Application-consistent | Bất biến giữa nhiều collection/service được bảo toàn hoặc đối soát |

Không giả định snapshot của từng node/collection ở các mốc riêng lẻ đủ để tái dựng hệ phân tán nhất quán.

## 22. Backup của sharded cluster

Một NoSQL cluster phân mảnh có thể chứa dữ liệu trên nhiều shard và metadata định tuyến.

Backup cần xem xét:

1. Tất cả shard liên quan.
2. Config/metadata về vị trí dữ liệu.
3. Các transaction và range/chunk migration đang xảy ra.
4. Checkpoint và thứ tự log trên các shard.
5. Index definitions và schema.
6. Cấu hình/phiên bản được hỗ trợ khi restore.
7. Quy trình kiểm tra số liệu sau phục hồi.

Copy tùy ý file của một node ở mỗi shard tại thời điểm khác nhau **không chứng minh** backup toàn cluster nhất quán. Cần công cụ hỗ trợ topology và point-in-time recovery phù hợp.

## 23. MongoDB replica set và backup

MongoDB replica set sao chép dữ liệu giữa các thành viên và có thể hỗ trợ failover. Ví dụ đọc trạng thái:

~~~javascript
rs.status();
~~~

Đây là thao tác quan sát replica set, **không tạo backup**.

### Write concern và majority

Write concern, ví dụ `majority`, liên quan số thành viên xác nhận và durability theo semantics/cấu hình. Nó giúp xử lý một số lỗi node/leader, nhưng không biến lệnh update sai thành thao tác có thể undo tự động.

### Oplog không phải kho lịch sử vô hạn

MongoDB oplog dùng cho replication. Nếu backup tool lưu base snapshot cùng những phần log đủ đầy, nó có thể cung cấp PITR theo phạm vi được hỗ trợ. **Chỉ có oplog chạy trong replica set không có nghĩa tự có backup dài hạn**.

### Logical và physical backup

- **Logical backup/export:** tài liệu/dữ liệu được xuất theo công cụ thích hợp; cần xác định consistency khi dữ liệu đang được ghi.
- **Physical backup:** backup data blocks/files theo cơ chế hỗ trợ; có thể cần log, metadata và version đúng.

Chạy một export trong lúc production thay đổi không mặc định tạo snapshot transaction-consistent trên mọi collection/shard. Hãy sử dụng quy trình backup được hỗ trợ theo topology.

## 24. Delayed replica có phải backup?

Một replica cố ý chậm so với primary có thể cho thêm khoảng thời gian để phát hiện xóa nhầm trước khi replica áp dụng thao tác đó. Đây là một lớp bảo vệ bổ sung.

Nhưng nó **không thay thế backup** vì:

- Có giới hạn độ trễ và cửa sổ cứu dữ liệu.
- Có thể chịu cùng lỗi hạ tầng/control plane.
- Nếu phát hiện muộn, nó cũng sẽ nhận thao tác sai.
- Không tạo nhiều restore point tùy chọn.
- Có thể mất khả năng bắt kịp log hoặc gặp sự cố node.
- Cần thao tác cứu dữ liệu thận trọng để không vô tình tiếp tục apply lỗi.

Đừng dùng delayed replica làm phương án duy nhất cho lỗi logic.

## 25. Cassandra: RF khác snapshot backup

Trong Cassandra, **replication factor (RF)** quyết định số replica dữ liệu theo chiến lược placement. Nó không phải số bản backup lịch sử.

Các consistency level như `ONE`, `QUORUM` và `ALL` điều khiển bảo đảm đọc/ghi theo API, nhưng không tự cho phép quay về trước một DELETE sai.

Nếu một delete đã được chấp nhận, tombstone và cơ chế đồng bộ/repair sẽ giúp các replica hội tụ theo semantics hiện hành. **Repair không phải công cụ undo dữ liệu đã xóa.**

### Snapshot và restore Cassandra

Cassandra có cơ chế snapshot SSTable, ví dụ thông qua `nodetool snapshot` trong các phiên bản phù hợp. Nhưng muốn DR đúng cần:

- Backup đủ dữ liệu/token ranges theo topology.
- Lưu schema/keyspace metadata và config.
- Hiểu consistency của snapshot giữa các node.
- Bảo vệ snapshot ở storage độc lập.
- Có quy trình restore full cluster hoặc table.
- Đối soát tombstone/timestamp và repair theo hướng dẫn.
- Lập kế hoạch incremental nếu RPO yêu cầu.

Một snapshot từng node được tạo không phối hợp không mặc nhiên là một backup cluster-wide nhất quán.

## 26. DynamoDB: Global Tables khác PITR

DynamoDB Global Tables sao chép dữ liệu giữa nhiều region theo kiến trúc được hỗ trợ, hữu ích cho multi-region availability và access pattern.

Nhưng một thao tác delete hợp lệ có thể lan sang các region. **Replication xuyên region không tự khôi phục bản ghi đã xóa**.

DynamoDB còn có các chức năng managed backup theo yêu cầu và Point-in-Time Recovery (PITR) theo gói/cấu hình/retention hỗ trợ.

Cần nhớ:

- Global Tables là năng lực replication.
- On-demand backup là điểm sao lưu.
- PITR là khả năng chọn mốc phục hồi trong cửa sổ hỗ trợ.
- Restore thường tạo tài nguyên/table mới theo quy trình dịch vụ, không tự tua ngược một table production.
- Sau restore có thể phải kiểm tra GSI, streams, TTL, policies, tags và tích hợp liên quan theo tài liệu dịch vụ.
- Cutover ứng dụng và đối soát dữ liệu mới vẫn là công việc vận hành riêng.

Không coi “đã bật Global Tables” là “đã bảo vệ khỏi xóa nhầm”.

## 27. Redis: replica, persistence và backup

Redis có nhiều phương án bảo vệ trạng thái:

| Cơ chế | Vai trò |
|---|---|
| Replica | Bản sao dữ liệu đang hoạt động |
| RDB snapshot | Ảnh chụp trạng thái tại một thời điểm |
| AOF | Persistence dựa trên ghi nhận thay đổi theo cơ chế Redis |
| Backup độc lập | Bản RDB/AOF hoặc artifact được lưu riêng, có retention/restore |

RDB/AOF có thể giúp phục hồi Redis sau crash/restart, nhưng nếu file chỉ nằm trên cùng máy đã mất hoặc bị xóa cùng credential, nó chưa đáp ứng DR độc lập.

AOF cũng không tự là lịch sử PITR vô hạn. Cần hiểu chính sách rewrite, fsync và lưu trữ phiên bản backup.

### Redis là cache hay nguồn dữ liệu?

Nếu có thể dựng lại toàn bộ Redis từ NoSQL nguồn, mất Redis chủ yếu ảnh hưởng hiệu năng/cold-start. Nếu Redis giữ session, queue hoặc trạng thái không có nguồn khác, yêu cầu RPO/RTO có thể khác và cần backup riêng.

Không mặc định mọi Redis đều “chỉ là cache”.

## 28. Search index và read model có thể rebuild?

Trong nhiều kiến trúc, search index, materialized view và cache là dữ liệu dẫn xuất.

Nếu nguồn vẫn đầy đủ, có thể **rebuild** thay vì restore backup projection. Nhưng cần hỏi:

1. Source có đủ dữ liệu để tái dựng không?
2. Event/log cần thiết còn được giữ không?
3. Rebuild mất bao lâu?
4. Tốc độ rebuild có đạt RTO không?
5. Có thể đối soát version và số document không?
6. Projection có chứa field không tồn tại ở nguồn không?

Nếu read model chỉ là tên gọi nhưng chứa dữ liệu độc quyền không thể dựng lại, nó đã trở thành một **nguồn dữ liệu cần bảo vệ**.

## 29. Không quên những phụ thuộc ngoài NoSQL

Một hệ Order có thể lưu:

~~~text
NoSQL order document
  -> object storage attachment
  -> external payment provider
  -> email/notification system
  -> event broker
  -> authentication/tenant config
  -> encryption keys
  -> search projection
~~~

Backup riêng `orders` không tự khôi phục file đính kèm, trạng thái payment bên ngoài hay key giải mã. DR runbook phải xác định dependency, nguồn có thẩm quyền và thứ tự phục hồi.

Đặc biệt các hệ ngoài như payment provider có **side effect thực**; không đơn thuần replay lại mọi command sau restore.

## 30. Event replay sau restore có thể gây side effect trùng

Giả sử Order đã được thanh toán, nhưng database được restore về thời điểm trước khi consumer lưu xong checkpoint. Nếu consumer đọc lại sự kiện thanh toán và gọi provider lần nữa, có thể phát sinh yêu cầu trùng.

Cần định nghĩa:

- Event nào chỉ để tái tạo dữ liệu dẫn xuất.
- Event nào kích hoạt side effect ra thế giới ngoài.
- Idempotency key có được lưu đúng không.
- Consumer offset/checkpoint tương thích với restore point chưa.
- Có chế độ replay không gửi email/không charge payment không.
- External provider đang có trạng thái nào và cách đối soát.

**Restore dữ liệu đúng byte vẫn có thể dẫn đến ứng dụng sai** nếu replay và side effect không được kiểm soát.

## 31. Restore vào môi trường cô lập trước

Đặc biệt sau xóa nhầm một tenant, không nên mặc định restore backup cũ đè lên production. Điều đó có thể làm mất các giao dịch hợp lệ của những tenant khác phát sinh sau điểm phục hồi.

Mặc định an toàn:

1. Chọn điểm trước khi lỗi.
2. Restore vào một môi trường riêng, network và quyền hạn được kiểm soát.
3. Tắt tác vụ có side effect tự động.
4. Kiểm tra số lượng, ID, trạng thái và schema.
5. Xác định data cần cứu: toàn hệ hay chỉ một tập con.
6. Đối soát các thay đổi hợp lệ sau restore point.
7. Chọn cutover toàn hệ hoặc selective import/merge.
8. Chỉ mở lại traffic khi các invariant thiết yếu được xác nhận.

**Selective restore** có thể giữ được dữ liệu mới của tenant khác, nhưng phức tạp hơn vì unique keys, references và trạng thái liên hệ. Không có một cách phù hợp cho mọi sự cố.

## 32. Dữ liệu nhất quán sau restore cần được kiểm tra

Các kiểm tra ví dụ cho domain đặt hàng:

- `orderId` duy nhất.
- OrderLine không có quantity/price sai kiểu hoặc âm trái quy tắc.
- Tổng tiền khớp snapshot đã chốt.
- Payment record và Order status nhất quán.
- Inventory reservation không bị áp dụng hai lần.
- Reference `productId` và `customerId` có scope hợp lệ.
- Tenant không nhìn thấy dữ liệu của tenant khác.
- Event/outbox không tái phát side effect trái phép.
- Dữ liệu nhạy cảm tuân thủ chính sách retention/xóa.

Checksum chỉ kiểm tra integrity ở một lớp; nó không chứng minh các invariant nghiệp vụ.

## 33. Các cấp độ kiểm thử backup

| Cấp | Kiểm tra | Điều chứng minh |
|---|---|---|
| 1 | Backup job chạy và có artifact | Có sản phẩm backup |
| 2 | Manifest/checksum hợp lệ | Artifact không hỏng theo cách kiểm tra |
| 3 | Giải mã và mở được backup | Key/công cụ còn dùng được |
| 4 | Database restore thành công | Engine có thể nhận dữ liệu |
| 5 | Index/schema/reference đúng | Cấu trúc đủ để chạy |
| 6 | Application smoke tests pass | Ứng dụng có thể hoạt động |
| 7 | Domain reconciliation pass | Trạng thái dữ liệu phù hợp nghiệp vụ |
| 8 | Full DR drill và cutover | Khả năng đạt RPO/RTO thực tế |

**Backup success không bằng restore success.** Một tổ chức chưa từng chạy restore có thể chưa biết thiếu key, tool không tương thích hoặc thời gian restore vượt mục tiêu.

## 34. Runbook khôi phục cần có gì?

Một runbook nên chứa:

1. **Khi nào kích hoạt:** lỗi node, lỗi logic, mất region, breach.
2. **Ai chịu trách nhiệm:** incident lead, DB operator, app owner, security.
3. **Chặn thiệt hại:** dừng script sai, khóa credential compromise, tắt consumer rủi ro.
4. **Tìm mốc sạch:** audit/event, thời điểm lỗi bắt đầu, restore point.
5. **Chọn artifact:** base backup, incremental, log và manifest.
6. **Khôi phục hạ tầng:** network, IAM, KMS, database version và topology.
7. **Restore dữ liệu:** theo cơ chế sản phẩm hỗ trợ.
8. **Kiểm tra:** type, index, schema, transaction, domain invariant, quyền.
9. **Đồng bộ/reconcile:** những thay đổi hợp lệ sau điểm phục hồi.
10. **Cutover:** định tuyến traffic và chặn split-brain.
11. **Giám sát:** lỗi API, queue, index lag, consistency.
12. **Postmortem:** nguyên nhân, gap và kế hoạch cải thiện.

Runbook phải có thể truy cập **ngay cả khi môi trường production chính gặp sự cố**, nhưng vẫn được bảo vệ khỏi truy cập trái phép.

## 35. Diễn tập restore và đo RPO/RTO

Ví dụ hợp đồng diễn tập:

~~~yaml
drill:
  scenario: "Restore tenant order data before logical deletion"
  objectives:
    rpoMinutes: 15
    rtoMinutes: 240
  target: "Isolated non-production environment"
  steps:
    - "Select valid restore point"
    - "Verify backup manifest and decryption keys"
    - "Provision isolated database"
    - "Restore base backup and required logs"
    - "Check indexes, schema and business invariants"
    - "Run application smoke tests"
    - "Measure data gap and recovery duration"
    - "Record findings and remediation"
  safety:
    overwriteProduction: false
    outboundPaymentsEnabled: false
    outboundNotificationsEnabled: false
~~~

Đây là **tài liệu mẫu**, không phải file cấu hình được database tự thực thi. Mục tiêu RPO/RTO viết trong YAML chưa chứng minh đã đạt; cần thời gian và điểm dữ liệu thực tế từ diễn tập.

Một báo cáo drill nên ghi:

- Backup/restore point được chọn.
- Actual recovery gap.
- Actual recovery duration.
- Những bước thủ công và quyền bị thiếu.
- Mất/khác biệt dữ liệu nào được phát hiện.
- Thời gian rebuild index.
- Những API/domain checks không đạt.
- Ai xử lý và khi nào diễn tập lại.

## 36. Monitoring replication khác monitoring backup

### Replication metrics

- Node/replica health.
- Replication lag.
- Leader election/failover.
- Write acknowledgment/quorum failures.
- Repair/compaction backlog theo engine.
- Disk/network apply rate.
- Trạng thái các zone/region.

### Backup metrics

- Latest successful backup.
- Latest **valid recoverable point**.
- Recovery window còn đủ không.
- Missing incremental/log segments.
- Checksum/manifest errors.
- Backup storage và retention status.
- Key access/decrypt readiness.
- Restore drill success rate.
- Actual RPO và RTO.
- Số document/collection drift khi đối soát.
- Khả năng restore khi source bị xóa hoàn toàn.

Một dashboard có replication lag = 0 **không nói gì** về việc backup tháng trước còn restore được hay không.

## 37. RPO/RTO có thể khác theo loại dữ liệu

| Dữ liệu | Hướng bảo vệ thường cân nhắc |
|---|---|
| Orders/payments | PITR/backup chặt, đối soát và idempotent replay |
| Inventory | Replication và recovery theo bất biến tồn kho |
| Customer profile | Backup, privacy, encryption và retention |
| Product catalog | Replication + backup, có thể phục hồi theo nhóm |
| Search index | Rebuild hoặc snapshot theo yêu cầu RTO |
| Cache | Rebuild nếu nguồn chính còn đầy đủ |
| Audit records | Integrity, quyền, immutability và retention rõ |
| Telemetry tạm | Theo chính sách lưu giữ và chi phí |

Đây là định hướng; một hệ thống cụ thể có thể đánh giá mức quan trọng khác. Không nên để các dữ liệu nghiệp vụ thiết yếu nhận chính sách backup giống cache chỉ vì cùng là NoSQL.

## 38. Chi phí của replication và backup

Replication tiêu tốn:

- Dung lượng các replica.
- CPU/network cho apply.
- Coordination/quorum.
- Multi-zone/multi-region traffic.
- Monitoring và vận hành failover.

Backup tiêu tốn:

- Full/incremental/log retention.
- Storage tách biệt, cross-region transfer.
- Object lock/immutable controls.
- Key management.
- Băng thông phục hồi.
- Temporary recovery environment.
- Nhân sự và thời gian restore drill.

Một hệ dùng RF=3 có thể tốn nhiều dung lượng replica, nhưng vẫn cần backup lịch sử. Ngược lại, backup rất rẻ trên object storage nhưng cần một ngày restore có thể không đạt RTO nghiệp vụ.

**Chi phí thật của backup bao gồm cả khả năng khôi phục đúng hạn**, không chỉ phí GB/tháng.

## 39. Failover và restore là hai quyết định khác nhau

~~~mermaid
flowchart TD
    A["Incident"] --> B{"Trạng thái dữ liệu hiện hành còn đúng?"}
    B -->|Có| C{"Replica/region khỏe?"}
    C -->|Có| D["Failover theo protocol"]
    C -->|Không| E["Restore backup + hạ tầng"]
    B -->|Không| F["Tìm mốc dữ liệu sạch"]
    F --> G["Chọn backup/PITR"]
    G --> H["Restore cô lập + kiểm chứng"]
    H --> I["Selective recovery hoặc cutover"]
~~~

Nếu chỉ một node chết, trạng thái dữ liệu đúng và có replica khỏe, failover có thể nhanh hơn restore. Nếu tất cả replica đều chứa dữ liệu bị lỗi logic, failover không giải quyết nguyên nhân.

Cần phân loại **availability incident** và **data integrity incident** trước khi chọn đường phục hồi.

## 40. Sai lầm thường gặp

**“Ba replica là ba backup.”** Chúng có thể cùng áp dụng một DELETE sai.

**“Có nhiều region là không thể mất dữ liệu.”** Lỗi logic và credential compromise có thể lan ra mọi region.

**“Write concern mạnh cho phép undo update.”** Nó giúp durability, không tạo lịch sử.

**“Oplog/AOF/WAL là PITR vô hạn.”** Chúng có mục đích và retention riêng.

**“Snapshot luôn là backup.”** Có thể thiếu isolation, consistency, log hoặc khả năng restore.

**“RPO là thời gian ứng dụng phục hồi.”** Đó là RTO; RPO đo khoảng dữ liệu bị lùi.

**“Backup chạy xanh nghĩa là phục hồi được.”** Chưa chứng minh key, version, index hay integrity.

**“Checksum đúng thì trạng thái nghiệp vụ đúng.”** Dữ liệu sai vẫn có thể có checksum tốt.

**“Mọi backup chụp từ nhiều shard cùng ngày đều nhất quán.”** Cần checkpoint/log và phối hợp phù hợp.

**“Delayed replica thay thế backup.”** Nó vẫn có cửa sổ cứu hạn chế và chịu lỗi chung.

**“Cassandra repair là khôi phục DELETE nhầm.”** Repair là đồng bộ replica theo trạng thái hiện hành.

**“DynamoDB Global Tables là PITR.”** Replication đa vùng và backup lịch sử khác nhau.

**“Redis AOF trên máy chính là DR backup.”** Có thể mất cùng máy và cùng credential.

**“Restore source xong chạy lại mọi event.”** Có thể gây thanh toán/email side effect trùng.

**“Muốn cứu một tenant thì ghi đè cả production bằng backup cũ.”** Có thể làm mất dữ liệu hợp lệ khác.

**“Backup immutable luôn phục hồi được.”** Key có thể mất, backup có thể chứa lỗi hoặc restore mất quá lâu.

## 41. Bài tập thực hành

### Bài A — Xóa nhầm trên ba replica

Cluster có ba replica. Một lệnh xóa 10.000 Order được xác nhận và nhân bản.

**Hỏi:** đổi leader có lấy lại dữ liệu không?

**Đáp án gợi ý:** không nếu replica đã áp dụng xóa. Cần backup/PITR hoặc nguồn lịch sử đáng tin.

### Bài B — Tính mức mất dữ liệu

Full backup chạy mỗi 6 giờ, không có log backup. Bản gần nhất 06:00, sự cố 11:59.

**Hỏi:** RPO 15 phút có được bảo vệ bằng lịch đó không?

**Đáp án:** không. Chênh lệch tới backup gần nhất gần 6 giờ.

### Bài C — Tính thời gian phục hồi

Phát hiện 20 phút, tải backup 30 phút, restore 120 phút, rebuild index 60 phút, xác minh/cutover 45 phút.

**Hỏi:** RTO 4 giờ có đạt không?

**Đáp án:** tổng 275 phút = 4 giờ 35 phút, vượt 240 phút.

### Bài D — Lỗi phát hiện muộn

Bug bắt đầu 01/11, phát hiện 20/11, backup retention 7 ngày.

**Hỏi:** có thể chắc chắn phục hồi trạng thái trước bug không?

**Đáp án:** không. Các điểm trước 01/11 có thể đã hết hạn; cần điều tra nguồn/audit khác.

### Bài E — Backup mất khóa

Backup còn đủ file và checksum, nhưng encryption key không còn.

**Hỏi:** đã có thể restore chưa?

**Đáp án:** chưa nếu không giải mã được. Key management là phần của DR.

### Bài F — Backup collection lệch nhau

Order CONFIRMED được chụp lúc 09:02, Payment PENDING được chụp lúc 09:00.

**Hỏi:** vấn đề là gì?

**Đáp án:** có thể restore một tổ hợp vi phạm quy tắc nghiệp vụ. Cần consistency/reconciliation.

### Bài G — Multi-region nhưng một quyền xóa

Ba region dùng cùng account admin có quyền xóa cluster và backup.

**Hỏi:** rủi ro chính còn lại?

**Đáp án:** control-plane compromise. Cần tách account/quyền và immutable retention.

### Bài H — Event replay

Sau restore, broker gửi lại event `ChargePayment` nhưng provider đã ghi nhận thanh toán.

**Hỏi:** làm sao tránh tính tiền hai lần?

**Đáp án:** kiểm tra external state, idempotency key, consumer checkpoint và replay mode.

### Bài I — Cassandra RF=3

Một DELETE sai đã được áp dụng. Có thể nhờ repair để phục hồi row cũ không?

**Đáp án:** không; repair không phải backup lịch sử.

### Bài J — DynamoDB Global Tables

Record bị xóa ở region A và delete đã lan sang B.

**Hỏi:** failover sang B có lấy lại row không?

**Đáp án:** không. Cần backup/PITR tới mốc trước lỗi nếu còn được hỗ trợ.

### Bài K — Redis AOF

Redis có AOF trên máy chính và một replica cùng rack. Cả rack hỏng.

**Hỏi:** bảo vệ DR đã đủ chưa?

**Đáp án:** chưa nếu không có backup độc lập hoặc nguồn khác đủ để rebuild.

### Bài L — Search index sau restore

Database nguồn phục hồi về 10:00, search index vẫn chứa dữ liệu lúc 11:00.

**Hỏi:** search index có thể tiếp tục làm nguồn sự thật không?

**Đáp án:** không mặc định. Phải rebuild/đối soát projection theo source và xử lý độ mới.

## 42. Checklist thiết kế một chương trình backup NoSQL

1. Phân loại dữ liệu nguồn, cache, projection, audit và các trường nhạy cảm.
2. Lập threat model: node, zone, region, bug, xóa nhầm, ransomware, credential.
3. Chọn RPO, RTO và recovery window cho từng loại dữ liệu.
4. Thiết kế replication theo fault model và consistency requirements.
5. Chọn full/incremental/log/PITR theo engine/topology.
6. Đảm bảo nhất quán trên collection, shard và metadata.
7. Lưu backup ngoài fault/control domain của production.
8. Thiết kế IAM, immutable retention, encryption và key recovery.
9. Bao gồm external blobs, config, schema, index và dependencies.
10. Xây restore runbook, phương án selective recovery/cutover.
11. Kiểm soát event replay và external side effects.
12. Diễn tập restore trong môi trường cô lập.
13. Đo latest recoverable point, actual RPO/RTO và integrity.
14. Cải thiện dựa trên kết quả drill, không chỉ trạng thái job.

Ví dụ hợp đồng:

~~~yaml
dataProtection:
  system: OrderNoSQL
  owner: OrderPlatform
  objectives:
    rpoMinutes: 15
    rtoMinutes: 240
    recoveryWindowDays: 30
  replication:
    purpose: highAvailability
    topology: multiAvailabilityZone
  backup:
    purpose: historicalRecovery
    baseSnapshot: scheduled
    changeCapture: continuousIfSupported
    pitr: required
    isolation:
      separateAccount: true
      immutableRetention: required
    encryptionKeyRecovery: documentedAndTested
  restore:
    target: isolatedEnvironmentFirst
    businessInvariantChecks: required
    externalSideEffects: disabledUntilReviewed
  drill:
    cadence: quarterly
    metrics:
      - latestValidRestorePoint
      - actualRecoveryDuration
      - consistencyResults
~~~

Đây là mẫu **tài liệu thiết kế**, không phải cấu hình tự được một hệ NoSQL thực thi. Mục tiêu trong file cần được chứng minh bằng thiết lập và diễn tập thật.

## 43. Kết luận

**Replication** giữ nhiều bản của **trạng thái hiện hành**, giúp hệ thống tiếp tục hoạt động qua nhiều sự cố node, zone hoặc region theo kiến trúc. **Backup** giữ năng lực phục hồi **trạng thái hợp lệ trong quá khứ**, giúp xử lý xóa nhầm, ghi sai, compromise và mất toàn bộ môi trường.

Một hệ thống có thể có replication rất tốt nhưng vẫn mất dữ liệu do DELETE sai; có backup dày đặc nhưng phục hồi quá chậm; có bản backup immutable nhưng không còn key; hoặc restore được byte nhưng ứng dụng phát lại side effect gây sai giao dịch.

Câu hỏi quyết định không phải **“đã có bao nhiêu bản dữ liệu?”** mà là:

> **Nếu một sự cố cụ thể xảy ra, đâu là trạng thái dữ liệu đúng gần nhất còn khôi phục được, bản đó có sống sót ngoài phạm vi lỗi không, và mất bao lâu để ứng dụng hoạt động đúng trở lại?**

Một chương trình độ bền dữ liệu NoSQL đáng tin cần **replication phù hợp + backup độc lập + retention/PITR có chủ đích + quy trình restore được kiểm thử + RPO/RTO đo được**. Chỉ khi restore thành công và dữ liệu sau phục hồi vượt qua kiểm tra nghiệp vụ, backup mới thực sự làm tròn nhiệm vụ.
