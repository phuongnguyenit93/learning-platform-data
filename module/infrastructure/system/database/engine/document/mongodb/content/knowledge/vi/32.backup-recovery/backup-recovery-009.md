# Chính sách giữ bản sao, mã hóa và phân quyền truy cập trong MongoDB

## 1. Mục tiêu bài học và bối cảnh

Backup MongoDB không chỉ là chạy một lệnh xuất dữ liệu rồi lưu một file vào ổ đĩa. Một bản sao chỉ hữu ích khi tổ chức biết **giữ bao lâu, ai được phép đọc/xóa/khôi phục, được mã hóa bằng khóa nào, và có thực sự phục hồi được trong thời gian chấp nhận được hay không**.

Ví dụ, hệ thống đặt hàng gặp ba sự cố:

1. Một nhân viên vô tình xóa collection `orders` lúc 10:25.
2. Ransomware chiếm quyền máy backup và cố xóa mọi file dự phòng.
3. Khóa mã hóa backup bị thu hồi nhầm, khiến file backup còn nguyên nhưng không giải mã được.

Ba sự cố đòi hỏi các biện pháp khác nhau: **recovery point phù hợp**, **bản sao bất biến/độc lập**, và **quản lý vòng đời khóa mã hóa**. Chỉ có nhiều file backup không bảo đảm xử lý được cả ba.

Bài học thuộc chương **Sao lưu và phục hồi** của module **Database Engine Document MongoDB**, với đề bài **Chính sách giữ bản sao, mã hóa và phân quyền truy cập**.

Sau bài này, bạn có thể:

1. Phân biệt backup, snapshot, oplog-based point-in-time recovery, archive và replica set.
2. Xác định RPO/RTO rồi xây lịch backup, retention tiers và PIT restore window.
3. Thiết kế chính sách giữ bản sao theo ngày/tuần/tháng/năm có kiểm soát pháp lý và chi phí.
4. Áp dụng nguyên tắc **3-2-1-1-0**, offsite copies, immutable storage và chống ransomware.
5. Hiểu chính sách Cloud Backup/Continuous Cloud Backup và Backup Compliance Policy của MongoDB Atlas.
6. Chọn các lớp mã hóa TLS, encryption at rest, mã hóa file backup và KMS/CMK.
7. Quản lý khả năng giải mã khi xoay khóa, thay KMS hoặc phục hồi các bản sao lịch sử.
8. Phân quyền riêng giữa MongoDB backup user, restore operator, Atlas control plane, object storage và KMS.
9. Sử dụng `mongodump`/`mongorestore` đúng phạm vi và tránh nhầm tính nhất quán của replica set/sharded cluster.
10. Thiết kế xác minh checksum, restore drill, audit trail, alert và runbook.
11. Xử lý xung đột retention với xóa dữ liệu theo yêu cầu và legal hold.
12. Lập một policy MongoDB hoàn chỉnh có thể kiểm tra được bằng bài thực hành.

**Thông điệp xuyên suốt:** Một backup chưa từng được phục hồi thử, không thể giải mã khi cần, hoặc có thể bị người vận hành sai quyền xóa sạch thì chưa phải phương án recovery đáng tin cậy.

## 2. Từ dữ liệu production đến một recovery point dùng được

Một bản sao dữ liệu có thể tồn tại dưới nhiều hình thức:

| Hình thức | Bản chất | Dùng để làm gì |
|---|---|---|
| Logical dump | BSON documents và metadata từ công cụ `mongodump` | Di chuyển/khôi phục theo database/collection và một số kịch bản nhỏ/vừa |
| Physical snapshot | Ảnh lưu trữ nhất quán ở một thời điểm | Khôi phục nhanh hơn trên cấu hình phù hợp |
| Cloud Backup snapshot | Dịch vụ backup quản lý bởi Atlas | Khôi phục cluster theo restore point được giữ |
| Oplog/PIT data | Những thay đổi giữa các snapshot | Khôi phục tới mốc thời gian nằm trong restore window |
| Immutable/offsite copy | Bản sao có chính sách chống sửa/xóa | Giảm blast radius khi bị ransomware/credential compromise |
| Archive dài hạn | Dữ liệu lịch sử được giữ lâu | Đáp ứng yêu cầu pháp lý/kiểm toán, thường có RTO dài hơn |

### 2.1. Replica set không thay backup

Replica set đồng bộ dữ liệu giữa những nodes, tăng availability. Nhưng nếu lệnh xóa nhầm được ghi thành công và replicate, **cả replica set đều có thể mất dữ liệu đó**.

~~~text
            Lệnh xóa nhầm collection
                       |
                       v
              Replica set PRIMARY
                 /          \
                v            v
           SECONDARY 1   SECONDARY 2
                \            /
                 \          /
              Đều replicate thao tác xóa

        Backup/PIT snapshot giữ trạng thái trước sự cố
~~~

Sharding cũng không tự tạo lịch sử phục hồi. Replication và backup giải quyết những nhu cầu khác nhau.

### 2.2. Backup và restore phải được thiết kế cùng nhau

Một chính sách chỉ nêu “backup mỗi đêm” nhưng không nêu khôi phục ở đâu, mất bao lâu và ai có quyền giải mã là chưa đủ.

Cần định nghĩa cả:

~~~text
Source MongoDB -> Consistent backup -> Encrypted storage
                                      |
                                      v
                                  Retention
                                      |
                                      v
                                 Access control
                                      |
                                      v
                                 Restore drill
                                      |
                                      v
                            Recovery acceptance test
~~~

### 2.3. “Backup successful” khác “Recoverable”

Job trả exit code 0 chỉ chứng minh chương trình hoàn tất theo góc nhìn công cụ. Cần kiểm tra file thực tồn tại, đủ nội dung, có checksum, có khóa giải mã, restore thành công và dữ liệu ứng dụng hợp lý.

## 3. RPO và RTO: hai đầu vào của retention policy

**RPO — Recovery Point Objective:** mức mất dữ liệu theo thời gian tối đa mà doanh nghiệp chấp nhận.

**RTO — Recovery Time Objective:** thời gian tối đa để dịch vụ phục hồi khả năng hoạt động.

Ví dụ:

~~~text
Sự cố lúc 10:25
Backup gần nhất: 10:00
Service được phục hồi lúc 11:10

Mất tối đa theo snapshot: khoảng 25 phút
Thời gian khôi phục: 45 phút
~~~

Với ví dụ này, nếu không có PIT, RPO thực tế tại sự cố có thể lên đến 25 phút; RTO quan sát là 45 phút.

### 3.1. Hai mục tiêu không đồng nghĩa

Có snapshot mỗi 5 phút không bảo đảm RTO=5 phút: khôi phục một database nhiều TB có thể cần lâu.

Ngược lại, khôi phục snapshot trong 5 phút nhưng bản sao gần nhất từ đêm qua vẫn có RPO rất lớn.

### 3.2. Chọn mục tiêu theo phân loại dữ liệu

| Nhóm hệ thống | RPO ví dụ | RTO ví dụ | Chính sách gợi ý |
|---|---:|---:|---|
| Đặt hàng/thanh toán | 5 phút | 1 giờ | PIT/continuous backup, kiểm thử thường xuyên |
| Nội dung CMS quan trọng | 1 giờ | 4 giờ | Backup đủ dày, snapshot định kỳ |
| Dữ liệu báo cáo tái tạo được | 24 giờ | 24 giờ | Daily snapshot, restore đơn giản |
| Dữ liệu thử nghiệm | Có thể tái tạo | Tùy ưu tiên | Có thể không backup hoặc retention rất ngắn |

**Các con số chỉ là ví dụ thiết kế**, không phải RPO/RTO mặc định của MongoDB. Cần xác nhận với chủ sở hữu nghiệp vụ, pháp lý và đội vận hành.

### 3.3. RPO được tính từ recovery point có thể dùng được

Nếu backup chạy lúc 10:00 nhưng lỗi mã hóa/upload lúc 10:02, không có backup hợp lệ. Recovery point thật có thể vẫn là 09:00.

Dashboard phải hiển thị **last verified recoverable point**, không chỉ timestamp job được lên lịch.

## 4. Retention là chính sách, không phải số ngày tùy ý

Retention định nghĩa **bản sao nào được giữ và trong bao lâu**. Nó cần bao gồm:

- Loại bản sao: snapshot, PIT/oplog, archive.
- Tần suất tạo.
- Khoảng thời gian giữ.
- Vị trí lưu.
- Chính sách mã hóa.
- Chủ thể có quyền truy cập.
- Điều kiện xóa, legal hold và exception.
- Recovery mục tiêu.
- Ngày/chính sách thay đổi và owner.

### 4.1. Cơ chế phân tầng phổ biến

**Grandfather–Father–Son (GFS)**:

- **Son:** bản sao ngắn hạn theo giờ/ngày.
- **Father:** bản sao hằng tuần.
- **Grandfather:** bản sao hằng tháng/năm.

Ví dụ policy minh họa:

| Tầng | Tần suất | Giữ trong | Mục đích |
|---|---|---|---|
| Hourly | Mỗi 6 giờ | 7 ngày | Phục hồi gần hiện tại |
| Daily | Mỗi ngày | 14 ngày | Sửa lỗi được phát hiện vài ngày sau |
| Weekly | Mỗi tuần | 8 tuần | Về trạng thái trước thay đổi lớn |
| Monthly | Mỗi tháng | 12 tháng | Đối chiếu, kiểm toán |
| Yearly | Mỗi năm | 3 năm | Nhu cầu lưu trữ theo chính sách |
| PIT/oplog | Liên tục | 7 ngày | Khôi phục đến phút/giây cụ thể trong cửa sổ hỗ trợ |

Thời gian và tần suất cần được cấu hình trên dịch vụ phù hợp. **Không** coi ví dụ này là yêu cầu pháp luật chung hoặc cấu hình mặc định của Atlas.

### 4.2. Snapshot interval và thời gian giữ là hai khái niệm khác

Một snapshot chạy mỗi 6 giờ, giữ 7 ngày:

~~~text
frequency = mỗi 6 giờ
retention = 7 ngày
~~~

Trong điều kiện không có PIT, sự cố ngay trước snapshot kế tiếp có thể mất gần 6 giờ dữ liệu. Giữ snapshot 365 ngày không cải thiện RPO gần hiện tại nếu tần suất snapshot quá thưa.

### 4.3. Phân loại dữ liệu trước retention

- Data có thể tái tạo từ nguồn đáng tin cậy.
- Data giao dịch quan trọng.
- Data có thông tin cá nhân/nhạy cảm.
- Data thuộc nghĩa vụ lưu hồ sơ.
- Data không còn mục đích sử dụng hợp pháp.
- Data cần giữ theo legal hold.

Retention quá dài làm tăng chi phí và blast radius khi backup bị lộ; retention quá ngắn làm mất recovery points cần thiết.

## 5. Lựa chọn giữa Atlas Cloud Backup và tự quản lý

### 5.1. MongoDB Atlas Cloud Backup

Atlas cung cấp chính sách backup theo tần suất như **hourly, daily, weekly, monthly, yearly**, với retention tùy cấu hình/cluster tier. Các snapshot dùng phương thức backup quản lý bởi Atlas; theo tài liệu kiến trúc, hoạt động lưu trữ có tính chất incremental để tiết kiệm chi phí và hỗ trợ khôi phục.

Ưu điểm:

- Quản lý snapshot schedule và retention tập trung.
- Khôi phục cluster hoặc PIT khi Continuous Cloud Backup được hỗ trợ/bật.
- Quản lý restore jobs và audit qua Atlas.
- Có tùy chọn copy snapshot sang region khác.
- Có Backup Compliance Policy trên deployment đủ điều kiện.

**Cần kiểm tra tier và cấu hình:** Không nên khẳng định mọi Atlas Free/Flex/dedicated cluster đều có chính sách snapshot/PIT giống nhau. Dedicated M10+ có những khả năng Cloud Backup và compliance cụ thể, Flex có cơ chế backup riêng.

### 5.2. Continuous Cloud Backup / point-in-time restore

Với Continuous Cloud Backup được bật, Atlas giữ snapshot cùng oplog data cần thiết để khôi phục tới một mốc trong **restore window**.

Ví dụ:

~~~text
Snapshot 06:00 ---- oplog changes ---- 10:24:59 ---- 10:25 xóa nhầm
                                             |
                                             v
                               Khôi phục thời điểm trước xóa
~~~

PIT hữu ích để xử lý thao tác xóa/cập nhật sai. Tuy nhiên cần kiểm tra:

- Restore window có bao gồm mốc mong muốn?
- Snapshot nền có sẵn và hợp lệ?
- Oplog chain được giữ/đồng bộ đầy đủ?
- Cluster/region/target hỗ trợ khôi phục?
- RTO phát sinh từ việc restore snapshot + replay oplog là bao nhiêu?

### 5.3. Self-managed backup

Với MongoDB tự vận hành, có thể dùng:

- MongoDB Ops Manager/Cloud Manager hoặc giải pháp quản lý phù hợp.
- Filesystem/storage snapshots **nhất quán** theo hướng dẫn MongoDB.
- `mongodump`/`mongorestore` cho logical dumps.
- Chiến lược physical backup phối hợp topology/replication/oplog.

**Không** mặc nhiên dùng một bản copy thư mục data directory trong lúc server đang ghi là backup nhất quán. Phải tuân theo quy trình filesystem snapshot/backup tool của MongoDB.

### 5.4. Tránh chọn công cụ chỉ theo độ quen thuộc

| Nhu cầu | Công cụ nên đánh giá |
|---|---|
| Atlas managed cluster | Cloud Backup và PIT nếu hỗ trợ |
| Sharded cluster lớn, ghi liên tục | Coordinated cluster-consistent backup |
| Xuất collection nhỏ có chủ đích | `mongodump` và `mongorestore` |
| RPO vài phút | Continuous/PIT backup phù hợp |
| Archive kiểm toán dài hạn | Snapshot/archive retention riêng, kiểm soát compliance |
| Khôi phục nhanh trong region | Snapshot local/optimized restore khi hỗ trợ |
| Chống ransomware | Immutable/offsite copy và identity separation |

## 6. Đặc điểm retention trên MongoDB Atlas

Một Atlas backup policy thường có **frequency interval** và **retention duration** cho từng tầng.

Ví dụ minh họa:

~~~text
Hourly:  every 6 hours, keep 7 days
Daily:   every day, keep 14 days
Weekly:  every week, keep 8 weeks
Monthly: every month, keep 12 months
PIT:     restore window 7 days
~~~

### 6.1. Những ràng buộc quan trọng

Theo MongoDB Atlas docs:

- Retention phải **không ngắn hơn** đơn vị tần suất tương ứng.
- Tầng backup ít thường xuyên hơn cần có retention bằng hoặc dài hơn tầng thường xuyên hơn theo chính sách.
- PIT restore window **không được dài hơn** hourly snapshot retention.
- Nếu một snapshot trùng nhiều policy items, snapshot được gắn với policy có retention dài nhất.
- Việc giảm tần suất hoặc retention có ảnh hưởng tới snapshots hiện có và tương lai theo các quy tắc riêng; không suy diễn rằng thay một option sẽ tự xóa ngay mọi bản cũ.

### 6.2. Tránh nhầm snapshot age và PIT window

Giữ monthly snapshots 12 tháng **không** có nghĩa có thể PIT tới mọi giây trong 12 tháng. PIT phụ thuộc **restore window và oplog data**.

### 6.3. Đồng hồ và timezone

Atlas backup policy có mốc thời gian UTC. Một tổ chức dùng giờ Việt Nam cần chuyển đổi khi đặt lịch và khi đánh giá sự cố.

Ví dụ:

~~~text
18:00 UTC = 01:00 ngày tiếp theo tại Việt Nam (UTC+7)
~~~

Không cộng UTC+7 vào timestamp đã lưu rồi coi đó là UTC mới.

### 6.4. Đường dẫn tham khảo

- Atlas Backup: `https://www.mongodb.com/docs/atlas/backup-restore-cluster/`.
- Manage Backup Policies: `https://www.mongodb.com/docs/atlas/backup/cloud-backup/configure-backup-policy/`.
- Backup Architecture: `https://www.mongodb.com/docs/atlas/architecture/current/backups/`.

## 7. Backup Compliance Policy và retention chống sửa/xóa

Với yêu cầu kiểm toán nghiêm ngặt, Atlas có **Backup Compliance Policy** trên những deployment đủ điều kiện.

Policy áp yêu cầu tối thiểu cho những clusters trong project và ngăn các hành động có thể làm giảm khả năng giữ bản sao:

- Không tùy ý xóa protected snapshots.
- Không giảm retention sau khi snapshot đã được tạo trong phạm vi bảo vệ.
- Không tắt Cloud Backup tùy tiện.
- Không giảm PIT restore window dưới yêu cầu compliance.
- Không dễ dàng tắt compliance policy mà không có quy trình xác minh/hỗ trợ phù hợp.

### 7.1. Quan trọng: quyết định này khó đảo ngược

MongoDB yêu cầu quy trình qua MongoDB Support với đại diện pháp lý/an ninh được chỉ định để xem xét việc tắt hoặc giảm một số controls. Đây không phải toggle mà Project Owner có thể tùy ý bật/tắt như tính năng không quan trọng.

Trước khi bật, kiểm tra:

1. Nghĩa vụ retention hợp pháp.
2. Chi phí backup storage.
3. Quy trình giải quyết yêu cầu xóa dữ liệu.
4. Người đại diện bảo mật/pháp lý có thể xác minh.
5. Recovery procedures và quyền truy cập.
6. Cách quản lý terminated clusters có retained snapshots.

### 7.2. “Immutable” và “không thể xóa bởi mọi user” khác nhau

Một snapshot có thể bất biến theo nghĩa **không sửa được nội dung**, nhưng vẫn có người có quyền **xóa**. Compliance policy bổ sung lớp ngăn xóa/giảm retention. Cần xác định rõ mức bảo vệ nào đang được bật.

### 7.3. Extra snapshot retention

Atlas có thể giữ bản sao thêm sau giai đoạn compliance-protected. Trong phần retention bổ sung, một số bảo vệ chống xóa có thể không còn như thời gian được compliance policy bảo vệ. Không ghi chung “mọi snapshot bất biến vĩnh viễn” nếu cấu hình có các giai đoạn khác nhau.

### 7.4. Khả năng hỗ trợ theo tier/version

Backup Compliance Policy có điều kiện về loại cluster, điển hình dedicated M10+ theo docs Atlas; không dùng một runbook chung cho Free/Flex/Infinite mà không kiểm tra chi tiết deployment.

## 8. Nguyên tắc 3-2-1-1-0 và offsite backups

Một nguyên tắc thiết kế mạnh hơn “lưu thêm file”:

- **3**: có ít nhất ba bản sao dữ liệu, tính cả dữ liệu gốc.
- **2**: dùng ít nhất hai loại môi trường lưu trữ/hình thức sao lưu độc lập khi phù hợp.
- **1**: có ít nhất một bản sao offsite.
- **1**: ít nhất một bản immutable hoặc offline/air-gapped.
- **0**: không phát hiện lỗi sau kiểm tra backup và thử restore.

~~~text
                   Production MongoDB
                           |
                +----------+----------+
                |                     |
                v                     v
       Snapshot cùng region       Offsite encrypted copy
                |                     |
                v                     v
           Restore nhanh         Immutable retention
                |                     |
                +----------+----------+
                           |
                           v
                        Restore drill
~~~

### 8.1. Độc lập về quyền quan trọng như độc lập về vị trí

Nếu production operator có quyền xóa cả source database và toàn bộ backup buckets/KMS keys, một tài khoản bị compromise có thể phá hủy mọi bản sao dù chúng ở hai regions.

Phải tách:

- Production administration.
- Backup writing.
- Backup deletion.
- Backup recovery.
- KMS administration.
- Compliance/retention override.

### 8.2. Cross-region chưa chắc đã đủ

Nếu cả hai regions cùng một IAM role có quyền delete, bản sao thứ hai vẫn có thể bị xóa đồng thời. Với rủi ro nghiêm trọng, cân nhắc **cross-account**, **separate credentials**, immutable retention và approval nhiều người.

### 8.3. Kiểm tra bản sao offsite thực sự có thể dùng

Bản sao cross-region chỉ có ý nghĩa khi:

- Metadata và dữ liệu cần thiết được copy đầy đủ.
- KMS keys sử dụng tại nơi restore có thể truy cập.
- Restore target được chuẩn bị.
- Network/IAM permissions phù hợp.
- Có rehearsal trên region/account khác.

## 9. Immutability: chống sửa và xóa trong cửa sổ giữ

Một bản sao immutable/WORM (*Write Once Read Many*) được bảo vệ khỏi thay đổi trong retention window, tùy công nghệ và chính sách.

Công nghệ có thể gồm:

- Atlas Backup Compliance Policy.
- Cloud object storage Object Lock/immutable bucket policy.
- Snapshot lock của hệ thống lưu trữ.
- Backup vault lock hoặc cơ chế tương đương.
- Offline copy không thường xuyên kết nối mạng.

### 9.1. Governance vs compliance mode

Một số cloud object stores có nhiều chế độ lock. Có thể tồn tại chế độ cho một principal đặc biệt bypass retention và chế độ bảo vệ nghiêm ngặt hơn. Cần xem chính sách cloud cụ thể, không gọi mọi cách đặt retention là bất biến tuyệt đối.

### 9.2. “Immutable” không sửa được secret/KMS đã hỏng

File backup không thể bị xóa nhưng key giải mã bị mất thì vẫn không thể restore.

~~~text
Immutable backup + destroyed key = dữ liệu có thể không phục hồi
~~~

Cần bảo vệ **khả năng giải mã** độc lập với khả năng giữ bytes.

### 9.3. Chỉ backup encryption không đủ chống ransomware

Một attacker có quyền xóa backup vẫn có thể xóa file mã hóa. Encryption và immutability bảo vệ những thuộc tính khác nhau.

### 9.4. Lock thử nghiệm cần xem chi phí

Bật retention lock nghiêm ngặt trên toàn bộ backup store có thể khiến không thể xóa thử nghiệm/dữ liệu dư, dẫn đến chi phí và mâu thuẫn pháp lý. Thử trên bucket/project test rồi mới áp dụng.

## 10. Các lớp mã hóa trong vòng đời backup

Có ít nhất bốn ranh giới:

~~~text
1. MongoDB storage (at rest)
          |
2. MongoDB -> backup worker (TLS)
          |
3. Backup worker -> object storage (TLS)
          |
4. Backup object at rest (KMS / client encryption)
          |
5. Object -> restore worker (TLS + decrypt)
~~~

### 10.1. TLS khi truyền dữ liệu

Nếu backup tool kết nối MongoDB, ưu tiên `tls=true` với xác minh server certificate/CA và hostname. Không tắt TLS validation chỉ để job backup chạy.

Upload từ backup worker tới cloud object store cũng phải dùng TLS, kèm kiểm tra endpoint và certificate chain.

### 10.2. Mã hóa database at rest không tự đồng nghĩa mã hóa export

Atlas có mã hóa dữ liệu at rest mặc định, nhưng **logical BSON dump khi xuất ra** có thể là dữ liệu có thể đọc được bởi ai có file.

Không suy luận rằng vì WiredTiger volume đã mã hóa, file `mongodump` tự động có encryption format cần key để giải mã. Bảo vệ file/export riêng.

### 10.3. Mã hóa backup tại kho lưu trữ

Với object storage, có thể dùng server-side encryption bằng KMS (SSE-KMS hoặc tương đương). Dữ liệu được mã hóa at rest tại provider, nhưng principal có quyền đọc object và quyền giải mã có thể lấy plaintext.

### 10.4. Mã hóa phía backup client

Nếu muốn giới hạn người đọc plaintext ngay cả trong storage service, có thể mã hóa file/stream **trước khi upload** bằng công cụ được tổ chức phê duyệt.

Ví dụ:

~~~text
mongodump BSON stream
        |
        v
    gzip compression
        |
        v
client-side encryption
        |
        v
private object storage
~~~

Dùng thuật toán mã hóa xác thực (*authenticated encryption*) hoặc giải pháp có cơ chế kiểm tra toàn vẹn rõ ràng. Không dùng cipher tự viết hoặc một password ZIP yếu.

### 10.5. Hai lớp mã hóa có thể cùng tồn tại

File backup được mã hóa ở client và storage bucket dùng SSE-KMS. Hai lớp giúp phân tách trách nhiệm, nhưng tăng phức tạp quản lý keys/restore. Cần biết khóa nào nằm ở đâu, ai được giải mã và có thể phục hồi khi KMS gián đoạn hay không.

## 11. KMS, CMK và envelope encryption

Một mô hình quản lý khóa:

~~~text
Backup BSON/archive
       |
       v
Data Encryption Key (DEK)
       |
       v
Encrypted archive
       |
       +--> DEK được bảo vệ bởi Customer-Managed Key (CMK)
                                      |
                                      v
                                   Cloud KMS
~~~

**Envelope encryption** thường dùng DEK để mã hóa dữ liệu; CMK/KMS bảo vệ DEK. Chỉ giữ CMK trong KMS giúp giảm việc phải phân phối raw master key.

### 11.1. KMS key lifecycle phải dài theo dependencies

Giả sử:

~~~text
Backup snapshot năm 2025
Encrypted using KMS key-version K1
Retention until năm 2030
~~~

Nếu K1 bị hủy trước 2030, backup có thể không khôi phục được dù object vẫn còn.

### 11.2. Rotation khác destruction

- **Rotate:** thêm phiên bản key mới cho dữ liệu/backup mới.
- **Disable:** tạm khóa khả năng dùng key, có thể ảnh hưởng restore.
- **Revoke permissions:** hạn chế principal nào có thể decrypt.
- **Destroy/delete key:** có thể khiến backup vĩnh viễn không đọc được.

Không gom mọi thao tác này vào một checkbox “rotate keys”.

### 11.3. Kiểm kê khóa theo thời điểm backup

Metadata ngoài nội dung bí mật có thể ghi:

~~~json
{
  "backupId": "orders-2026-11-14T00:00:00Z",
  "encryptionMethod": "client-envelope-plus-kms",
  "kmsKeyRef": "alias/backup-key-prod",
  "keyVersionRef": "version-at-backup-time",
  "restoreTested": true
}
~~~

Không ghi plaintext DEK/CMK vào manifest. Cần bảo vệ metadata nhạy cảm về topology/namespaces nếu nó có thể hỗ trợ tấn công.

### 11.4. Xác nhận decrypt trước khi xóa old key

Một key rotation nên có restore test trên một backup được mã hóa bằng **old key** và một backup bằng **new key**, nhất là khi chuyển account/region/KMS provider.

## 12. MongoDB Atlas mã hóa snapshots thế nào?

Theo tài liệu MongoDB Atlas:

- Backup snapshots được mã hóa at rest bằng cơ chế chuẩn của cloud provider.
- Khi bật **Encryption at Rest using Customer Key Management**, Atlas áp thêm lớp mã hóa phù hợp bằng KMS của khách hàng.
- Khi restore, dữ liệu snapshot được truyền bằng TLS.
- Snapshot và PIT oplog có dependencies với các keys dùng tại thời điểm tạo.
- Snapshot mã hóa với key không còn hợp lệ/không thể truy cập có thể không khôi phục được.

### 12.1. Đừng nhầm Atlas-managed encryption với file export ngoài Atlas

Backup do Atlas quản lý có cơ chế mã hóa của Atlas. Một file bạn xuất ra laptop hoặc server backup riêng phải có policy encryption/storage riêng.

### 12.2. KMS outage có thể ảnh hưởng restore

Nếu tổ chức revoke key hoặc thay IAM grant cho Atlas KMS integration, khả năng khôi phục có thể thất bại. Những hành động liên quan CMK cần được xem là **thay đổi disaster recovery**, không chỉ thay đổi bảo mật.

### 12.3. Recovery readiness phải gồm key readiness

Một báo cáo “snapshots available = 120” chưa chứng minh recoverability nếu KMS principals không được phép decrypt. Restore drill phải đi qua cùng KMS/trust path dự kiến dùng khi có sự cố.

## 13. Mã hóa không chỉ bảo mật, còn phải kiểm tra integrity

Ba thuộc tính cần phân biệt:

- **Confidentiality:** không đọc được nội dung nếu thiếu key.
- **Integrity:** phát hiện nội dung bị thay đổi/hỏng.
- **Availability:** backup/keys/hạ tầng có sẵn để restore.

Một SHA-256 checksum giúp phát hiện file khác với bản ban đầu nếu checksum được lưu/so sánh an toàn, nhưng **không** thay authentication của nội dung mã hóa. Attacker có thể sửa cả file và checksum nếu cả hai cùng nằm trong nơi họ kiểm soát.

### 13.1. Manifest bảo vệ được điều gì?

Manifest có thể lưu:

~~~json
{
  "backupId": "orders-2026-11-14T00:00:00Z",
  "sourceEnvironment": "production",
  "snapshotStartUtc": "2026-11-14T00:00:00Z",
  "backupType": "logical-full",
  "encryptedObject": "orders/2026/11/14/archive.gz.gpg",
  "checksumAlgorithm": "SHA-256",
  "status": "verified"
}
~~~

Nên ký hoặc bảo vệ manifest bằng cơ chế access/integrity riêng. Không đánh dấu `status:"verified"` chỉ vì job đã upload.

### 13.2. Compression và encryption thứ tự nào?

Thông thường **compress trước, encrypt sau**. Dữ liệu đã mã hóa thường khó nén hiệu quả. Khi stream backup phải kiểm tra exit status của toàn pipeline để không chấp nhận một file mã hóa bị cắt cụt.

### 13.3. Checksum không thay restore test

Bản backup có checksum đúng nhưng thiếu collection hoặc backup tool version không tương thích vẫn có thể không dùng được. Restore test là bằng chứng mạnh hơn.

## 14. Phân quyền theo bốn lớp: MongoDB, Atlas, backup store, KMS

Một người có quyền `readWrite` trong database không có nghĩa được tải snapshots; ngược lại người có quyền restore backup có thể đọc nhiều dữ liệu nhạy cảm.

### 14.1. Bốn lớp

~~~text
Application MongoDB RBAC
        |
        v
Backup control plane (Atlas/Ops Manager)
        |
        v
Backup object store IAM/ACL
        |
        v
KMS decrypt permissions
~~~

Một restore thành công có thể cần quyền ở **tất cả các lớp**, tùy phương án.

### 14.2. Ma trận tách nhiệm vụ

| Vai trò | Đọc DB phục vụ backup | Ghi backup | Xóa backup | Decrypt | Restore prod |
|---|---|---|---|---|---|
| Backup agent | Có, phạm vi cần thiết | Có | Không | Thường chỉ encrypt | Không |
| Backup auditor | Không | Không | Không | Không mặc định | Không |
| Restore operator staging | Tùy kịch bản | Không | Không | Có qua approval | Không |
| Disaster recovery lead | Theo approval | Có thể | Không mặc định | Qua KMS authorization | Có qua change approval |
| Retention administrator | Không | Quản policy | Có giới hạn/approval | Không mặc định | Không |
| KMS administrator | Không | Không | Không | Quản key/policy, không mặc định đọc backup | Không |
| Application developer | Theo app roles | Không | Không | Không | Không |

Đây là **ma trận mẫu**, không phải tên các built-in roles sẵn có trong MongoDB/Atlas.

### 14.3. Chống "quyền cộng dồn"

Nếu một principal vừa có quyền đọc object, decrypt KMS và network access tới hệ thống ngoài, nó có thể exfiltrate backup. Cần just-in-time access, audit, MFA, approval và giới hạn network.

### 14.4. Người có quyền restore có thể đọc nhiều dữ liệu hơn người dùng thường

Restore sang một cluster họ kiểm soát có thể cho họ khả năng đọc mọi collection, dù trong source DB người đó không có role `read`. Vì thế quyền restore là quyền nhạy cảm cao.

## 15. MongoDB built-in role backup và restore trên self-managed

MongoDB có các built-in roles:

- `backup` trong `admin`: quyền cần thiết để thực hiện các thao tác `mongodump` phổ biến trên dữ liệu tương ứng.
- `restore` trong `admin`: quyền để khôi phục dữ liệu theo các chức năng được hỗ trợ.

Tạo một backup principal mẫu trên self-managed lab:

~~~javascript
use admin

db.createUser({
  user: "backup_agent",
  pwd: passwordPrompt(),
  roles: [
    { role: "backup", db: "admin" }
  ],
  mechanisms: ["SCRAM-SHA-256"]
});
~~~

### 15.1. Không dùng root cho backup routine

`root` có thể sửa/xóa dữ liệu và users ngoài nhu cầu backup. Dùng account riêng, không tái sử dụng credential production application.

### 15.2. Restore có thể cần quyền bổ sung

Một số thao tác restore đặc biệt cần privileges ngoài role `restore`, ví dụ:

- Restore metadata liên quan `system.profile` có điều kiện riêng.
- `mongorestore --oplogReplay` có yêu cầu đặc biệt: MongoDB docs nêu cần user-defined role có `anyAction` trên `anyResource` đối với kịch bản đó.

**Đây là quyền rất rộng.** Không tự cấp để “cho chạy được”; chỉ thực hiện trên target cô lập với approval và runbook restore đầy đủ.

### 15.3. Tách backup và restore principal

Backup agent nên có quyền **đọc source** và **ghi object store**, không có quyền `mongorestore --drop` trên production. Restore operator cần quyền riêng, cấp có thời hạn khi xảy ra sự cố đã phê duyệt.

### 15.4. Atlas có cơ chế database users khác

Với MongoDB Atlas, quản lý database users/roles theo Atlas được hỗ trợ. Không chạy `db.createUser()` trực tiếp rồi kỳ vọng Atlas user management sẽ ghi nhận như self-managed.

## 16. Atlas backup roles và quyền thao tác

Tùy thao tác/đường dẫn API, Atlas phân biệt những project-level roles như:

- **Project Read Only**: xem nhiều thông tin backup/policy phù hợp.
- **Project Backup Creator**: thao tác tạo và một số quản lý snapshots theo docs.
- **Project Backup Manager**: quản lý các công việc backup/restore rộng hơn.
- **Project Backup Recovery Operator**: khởi chạy restore jobs ở kịch bản được hỗ trợ.
- **Project Owner**: quyền quản trị rộng.

Theo Atlas docs, để **bắt đầu restore job** cần role thích hợp như Project Backup Recovery Operator, Project Backup Manager hoặc Project Owner. Với cross-project/cross-organization restores, yêu cầu quyền ở cả source và target, thường ở mức Project Backup Manager/Project Owner theo kịch bản.

### 16.1. Không có một "backup admin" dùng chung cho mọi API

Một số endpoints (ví dụ tạo on-demand snapshots qua API) có yêu cầu role riêng. Đọc trang **Required Access** của thao tác cụ thể trước khi viết automation.

### 16.2. Tách người duyệt và người chạy restore

Restore vào cluster đích có thể **xóa toàn bộ dữ liệu hiện tại** trong cluster đó ở kịch bản cluster-level restore. Cần approval, review target và bảo đảm không phải production cluster nhầm.

### 16.3. Chính sách phân quyền Atlas

- Dùng project-specific roles, không mặc định Organization Owner.
- API/service accounts riêng cho automation.
- Hạn chế quyền delete snapshots nếu không cần.
- MFA/SSO và audit cho người vận hành.
- Just-in-time quyền recovery.
- Kiểm tra role assignments định kỳ.

## 17. Quyền kho lưu trữ: đọc, ghi, xóa và giữ bất biến

Với self-managed backups vào object storage, chia actions thành:

- **Write:** upload object mới.
- **Read/List:** liệt kê/tải bản sao.
- **Delete:** xóa objects/versions.
- **Change retention:** rút ngắn thời hạn hoặc bypass lock.
- **Manage encryption key:** cấp/revoke/disable CMK.

### 17.1. Backup writer không cần delete

Một account backup tự động thường chỉ cần tạo objects với đường dẫn định danh mới và quyền kiểm tra kết quả. Nếu account bị compromise, giới hạn delete giúp giảm khả năng xóa toàn bộ lịch sử.

### 17.2. Phân vùng theo application/environment

Ví dụ đường dẫn object:

~~~text
backups/
  production/
    orders/
      2026/11/14/...
    catalog/
      2026/11/14/...
  staging/
    orders/
      ...
~~~

Phân vùng giúp hạn chế access bằng prefix, nhưng chỉ là **đường dẫn**; enforce thực sự phải bằng bucket policy/IAM, không chỉ naming convention.

### 17.3. Tránh public ACL

Backup MongoDB có thể chứa toàn bộ PII, dữ liệu tài chính và secrets lưu sai trong DB. Không để object/bucket public hoặc cung cấp pre-signed URLs có thời hạn quá dài.

### 17.4. Delete cần approval và retention protection

Nếu business cần tự động xóa backup hết hạn, policy đó phải tương thích object lock/legal hold. Một lifecycle rule không được phép âm thầm xóa bản đang được bảo vệ bởi retention bắt buộc.

## 18. Ví dụ IAM policy minh họa cho object storage

Một backup writer dùng object storage nên chỉ có quyền cần thiết. Pseudocode:

~~~json
{
  "role": "mongo-backup-writer-prod",
  "resource": "backup-bucket/production/orders/*",
  "allow": [
    "ListAuthorizedPrefix",
    "WriteNewBackupObject",
    "ReadOwnWriteMetadata"
  ],
  "deny": [
    "DeleteBackupObject",
    "BypassObjectRetention",
    "ChangeBucketPolicy",
    "DisableKmsKey"
  ]
}
~~~

**Đây là mô hình quyền, không phải JSON IAM policy hợp lệ của AWS/GCP/Azure.** Khi triển khai phải chuyển sang action/resource/condition keys chính xác theo provider và kiểm tra effective permissions.

### 18.1. Vì sao có deny explícit?

Nếu một principal vô tình được gán thêm role rộng ở nơi khác, explicit deny có thể đóng vai trò guardrail trong những IAM systems hỗ trợ. Tuy vậy phải kiểm tra precedence và cách provider xử lý policies.

### 18.2. KMS grants phải tách

Một backup writer dùng client-side public-key encryption có thể mã hóa mà không cần private decryption key. Nếu dùng KMS envelope encryption, nó cần những operations tạo/bọc data key; **không** mặc định phải có quyền decrypt mọi backup lịch sử.

Restore operator có thể cần `Decrypt` của key phiên bản liên quan, theo phê duyệt và audit.

## 19. Kịch bản mongodump: logical backup trên self-managed MongoDB

### 19.1. Điều kiện trước khi chạy

- Sử dụng MongoDB Database Tools version tương thích.
- Có network/TLS/backup user đúng quyền.
- Đã xác định là standalone, replica set hay sharded.
- Có dung lượng và backup store đã bảo vệ.
- Có kế hoạch tránh plaintext backup tồn tại trên host.
- Có kiểm tra exit code và alert.
- Không dùng một command ví dụ để thay chiến lược backup cho sharded cluster lớn.

### 19.2. Dump cơ bản cho lab nhỏ

Ví dụ backup database `backup_lab` trên MongoDB self-managed; không mặc định nhất quán khi có ghi đồng thời:

~~~bash
mongodump \
  --host db1.example.test \
  --port 27017 \
  --tls \
  --username backup_agent \
  --authenticationDatabase admin \
  --db backup_lab \
  --archive=backup_lab.archive.gz \
  --gzip
~~~

Khi không đưa password vào command line, Database Tools có thể prompt tương tác theo cấu hình/version. Với automation, dùng secret delivery được công cụ hỗ trợ và tránh để password trong process arguments/logs.

**Cảnh báo:** File `backup_lab.archive.gz` là dump BSON đã nén, **không tự được mã hóa** chỉ vì có `--gzip`.

### 19.3. Nén không phải mã hóa

~~~text
--gzip   = compression
--archive = output format
--tls    = encryption in transit
~~~

Không tùy tiện gọi file `.gz` là “encrypted backup”.

### 19.4. Backup một database có thể không đủ

Dữ liệu ứng dụng có thể phụ thuộc users/roles, indexes, cluster config, external secrets, object store files và ứng dụng code/config. Logical dump không tự capture mọi dependency ngoài MongoDB.

## 20. Replica set nhất quán: --oplog và --oplogReplay

Đối với một **self-managed replica set member**, `mongodump --oplog` có thể ghi những oplog entries phát sinh trong quá trình dump để tạo một backup nhất quán tại một thời điểm, khi dùng đúng điều kiện.

Ví dụ **toàn bộ replica set**, không chỉ một database:

~~~bash
mongodump \
  --host rs-member.example.test \
  --port 27017 \
  --tls \
  --username backup_agent \
  --authenticationDatabase admin \
  --oplog \
  --archive=full-rs.archive.gz \
  --gzip
~~~

### 20.1. Điều kiện của --oplog

MongoDB docs yêu cầu khi dùng `--oplog`:

- Dump **đầy đủ** replica set member.
- Không kết hợp `--db`, `--collection`, `--query` hoặc các lựa chọn giới hạn dump khác.
- Không dùng để backup toàn sharded cluster qua `mongos`.
- Một số thay đổi DDL/users/roles/chính sách cluster diễn ra khi dump có thể làm dump thất bại.
- Cần tool/server compatibility phù hợp.

Đặc biệt, nếu upgrade feature compatibility version qua thay đổi định dạng time series trong lúc backup, `mongorestore --oplogReplay` có thể không khôi phục được đoạn oplog đó theo các cảnh báo version hiện hành.

### 20.2. Restore trong lab cô lập

~~~bash
mongorestore \
  --host restore-lab.example.test \
  --port 27017 \
  --tls \
  --username restore_agent \
  --authenticationDatabase admin \
  --archive=full-rs.archive.gz \
  --gzip \
  --oplogReplay
~~~

**Chỉ chạy trên target restore lab được chuẩn bị đúng.** `--oplogReplay` có yêu cầu privileges đặc biệt, và restore dữ liệu/users/roles có thể làm thay đổi authentication của target.

### 20.3. Không dùng --drop bừa bãi

`mongorestore --drop` xóa collections có trong dump ở target trước khi restore. Khi dump chứa database `admin`, việc restore/drop có thể ảnh hưởng users/roles và làm bạn mất khả năng xác thực.

Không dùng trực tiếp trên production chỉ để test. Trong restore drill nên có cluster đích riêng.

## 21. Sharded cluster: tính nhất quán phải xuyên shards

Một sharded MongoDB cluster có:

~~~text
mongos
  |
  +--> Shard A replica set
  +--> Shard B replica set
  +--> Config server replica set
~~~

Dump từng shard tại thời điểm ngẫu nhiên **không tự tạo** một global snapshot nhất quán khi các transactions/migrations đang diễn ra.

### 21.1. Vì sao --oplog chưa đủ?

MongoDB docs nêu `mongodump --oplog` **không dùng để backup cả sharded cluster qua mongos**. `mongorestore --oplogReplay` cũng không hỗ trợ sharded clusters theo cách áp dụng cho full replica-set dump.

### 21.2. Cách tiếp cận

- Ưu tiên Atlas/Cloud Manager/Ops Manager hoặc giải pháp coordinated backup phù hợp.
- Nếu tự quản lý sharded cluster, làm theo đúng hướng dẫn MongoDB về coordinated dumps, consistency, balancer/chunk migrations và transaction timing.
- Không tự gắn nhiều file dump riêng thành “point-in-time backup toàn cluster” nếu thiếu phối hợp.
- Restore test cần xác minh dữ liệu cross-shard, indexes và ứng dụng.

## 22. Mã hóa file mongodump bằng công cụ được phê duyệt

Một quy trình backup file tự quản có thể dùng stream → compression → encryption, tránh ghi plaintext archive vào disk trung gian.

**Ví dụ khái niệm** với GPG public-key encryption trên Linux/macOS, giả định đã nhập public key của backup recipient:

~~~bash
set -o pipefail

mongodump \
  --host rs-member.example.test \
  --port 27017 \
  --tls \
  --username backup_agent \
  --authenticationDatabase admin \
  --oplog \
  --archive \
  --gzip \
  | gpg --batch --encrypt \
      --recipient backup-archive-recipient \
      --output full-rs-2026-11-14.archive.gz.gpg
~~~

Lưu ý:

- `backup-archive-recipient` là định danh public key đã được cấp và kiểm tra, không phải password đặt trong code.
- `mongodump` vẫn cần auth secret từ kênh phù hợp.
- `set -o pipefail` giúp báo lỗi khi **một thành phần pipeline** thất bại trên Bash, thay vì chỉ nhìn exit code của GPG.
- GPG output phải được bảo vệ trong private storage và phải có integrity checks.
- Một pipeline còn có thể cần stdout/stderr redaction, kiểm tra disk quota và retry upload.

### 22.1. Có nên dùng GPG cho production?

Có thể, nếu tổ chức đã có key lifecycle, recovery procedure và tool hardening. Đây không phải lời khuyên “GPG luôn tốt nhất”; cloud KMS envelope encryption hoặc backup software tích hợp key management có thể hợp lý hơn.

### 22.2. Không dùng khóa riêng trên cùng host như bảo vệ duy nhất

Nếu private decryption key nằm cùng máy backup và attacker chiếm máy đó, encryption at rest không đủ làm ranh giới bảo mật.

### 22.3. Upload object qua TLS và khóa IAM riêng

Sau khi tạo file đã mã hóa, upload qua TLS tới private bucket bằng workload identity có quyền ghi mới và không có delete/bypass retention.

## 23. Verify backup đã mã hóa mà không cần restore vào production

Sau backup và upload:

1. Kiểm tra file/object size.
2. Kiểm tra job/pipeline exit codes.
3. Tính checksum của ciphertext.
4. Ghi manifest được bảo vệ.
5. Xác minh key/certificate decrypt được trong môi trường recovery.
6. Đọc archive headers/schema nếu phù hợp.
7. Restore vào cluster kiểm thử cô lập.
8. Chạy bài kiểm tra dữ liệu/ứng dụng.

### 23.1. Hash của file đã mã hóa

Ví dụ:

~~~bash
sha256sum full-rs-2026-11-14.archive.gz.gpg
~~~

Lưu checksum cùng backup ID trong manifest có integrity protection. Hash giống nhau xác nhận hai bản bytes giống nhau, nhưng không chứng minh dữ liệu business đúng.

### 23.2. Test giải mã với GPG

Trong recovery environment có private key hợp lệ:

~~~bash
gpg --decrypt \
  --output restored.archive.gz \
  full-rs-2026-11-14.archive.gz.gpg
~~~

Kết quả tạm thời có thể là **plaintext compressed BSON archive**; phải lưu ở thư mục bảo vệ và xóa theo quy trình an toàn sau restore. Nếu muốn tránh file trung gian, dùng streaming decryption với quyền và pipeline status được giám sát.

### 23.3. Restore drill vào isolated target

~~~bash
mongorestore \
  --host isolated-restore.example.test \
  --port 27017 \
  --tls \
  --username restore_agent \
  --authenticationDatabase admin \
  --archive=restored.archive.gz \
  --gzip
~~~

Với archive chứa oplog phù hợp, khôi phục đầy đủ qua `--oplogReplay` chỉ khi test topology và privileges đáp ứng yêu cầu. Không chuyển lệnh trên sang production khi chưa có restore plan.

### 23.4. Dùng --dryRun như một kiểm tra phụ

`mongorestore --dryRun` trên versions hỗ trợ có thể tóm tắt restore mà không thực sự ghi dữ liệu. Nhưng dry-run **không thay** kiểm chứng giải mã, dữ liệu và application-level consistency trong restore thực.

## 24. Chính sách phân quyền cho quy trình restore

Restore vào một cluster trống là workflow khác restore **đè lên** một cluster đang chứa dữ liệu.

### 24.1. Restore target phải được chọn tường minh

Trước khi restore:

- Target project/cluster/database.
- Nó có đang phục vụ user thật không?
- Có data nào sẽ bị xóa/ghi đè?
- Restore có kèm users/roles?
- Application endpoints có trỏ nhầm vào target không?
- Có namespace mapping từ backup sang staging không?
- Có KMS/trust/decrypt permissions không?
- Có restore verification và rollback plan không?

### 24.2. Atlas cluster-level restore có thể thay toàn bộ target

MongoDB Atlas docs nêu với cluster-level restore, target cluster có thể bị xóa dữ liệu hiện có trước khi restore và unavailable trong quá trình xử lý. Vì vậy thao tác này phải được xem là **change có tác động lớn**.

### 24.3. Phê duyệt phân tách nhiệm vụ

Ví dụ:

~~~text
Incident Commander -> yêu cầu khôi phục
Security/DBA Lead  -> phê duyệt quyền truy cập
Recovery Operator  -> chạy restore job
Application Owner  -> xác minh nghiệp vụ
Auditor            -> ghi nhận chứng cứ
~~~

Đừng để một tài khoản duy nhất không có giám sát vừa đổi retention, xóa backups, lấy key, restore vào production và xóa audit logs.

### 24.4. Just-in-time restore access

Quyền decrypt/restore nên được cấp theo incident/time window khi phù hợp, tự hết hạn và có audit. Các yêu cầu break-glass phải có người trực và cách thu hồi sau sự cố.

## 25. Test restore: cái gì phải kiểm tra?

Restore thành công về mặt tool chưa đủ. Xây một **acceptance suite**.

### 25.1. Kiểm tra kỹ thuật

- Cluster đã online và members khỏe.
- Các collections mong đợi có mặt.
- Indexes được tạo đủ và build xong.
- Counts không thiếu bất thường.
- Các sample documents tồn tại.
- Các references giữa collections hợp lệ.
- Roles/users được xử lý theo chính sách.
- Không thiếu key khiến field-level ciphertext không đọc được.

### 25.2. Kiểm tra nghiệp vụ

Ví dụ với hệ thống đặt hàng:

- Một order và payment đi kèm có trạng thái hợp lệ.
- Không bị phục hồi order nhưng thiếu line items.
- Tồn tại product/SKU references.
- Timestamp và timezone đúng.
- Hệ thống có thể xử lý request đọc/ghi thử.
- Các external integrations không gửi event trùng ngoài kiểm soát.

### 25.3. Kiểm tra RTO/RPO đã đạt chưa

Một report:

~~~text
Recovery point available: 2026-11-14 10:24:30 UTC
Failure detected:         2026-11-14 10:25:00 UTC
Service available:        2026-11-14 11:02:00 UTC

Observed data gap: 30 seconds
Observed restore duration: 37 minutes
~~~

Đo theo thời điểm có bằng chứng. Nếu mục tiêu RPO 5 phút và RTO 60 phút, test này đạt về thời gian, nhưng vẫn cần acceptance data checks.

### 25.4. Lịch diễn tập

- Test một backup gần nhất theo lịch.
- Test một backup 30/90 ngày tuổi để xác minh key retention.
- Test PIT gần thời điểm xảy ra DDL/sự cố giả lập.
- Test restore cross-region/cross-account.
- Test khi một privileged backup credential bị khóa.
- Test khi KMS key version cũ được yêu cầu.

Không chỉ restore một file mới tạo trên chính host tạo file.

## 26. Retention và nghĩa vụ xóa dữ liệu

Backup retention có thể mâu thuẫn với yêu cầu xóa thông tin cá nhân. Một bản sao immutable giữ dữ liệu trước thời điểm xóa.

### 26.1. Không tuyên bố xóa khỏi production là xóa khỏi backup

~~~text
Ngày 1: Document chứa PII được backup
Ngày 3: Người dùng yêu cầu xóa, production đã xóa
Ngày 4: Backup ngày 1 vẫn chứa PII
~~~

Một chính sách phù hợp cần xác định rõ:

- Cơ sở pháp lý để giữ backup.
- Khoảng thời gian giữ tối thiểu/tối đa.
- Ai được dùng backup cho mục đích nào.
- Cách xử lý yêu cầu xóa với backup immutable.
- Quy trình **reapply deletions** nếu restore backup cũ.
- Thời điểm loại bỏ bản sao khi retention kết thúc.

### 26.2. Restore có thể tái xuất hiện dữ liệu đã xóa

Nếu backup từ ngày 1 được restore ngày 7, những documents đã xóa ở ngày 3 có thể quay lại. Cần có deletion ledger/tombstones hoặc quá trình đồng bộ xóa theo chính sách trước khi mở dữ liệu restored cho người dùng.

### 26.3. Legal hold

Legal hold có thể yêu cầu giữ dữ liệu lâu hơn retention thường. Nó phải được phê duyệt, có phạm vi/owner/expiry review và kiểm soát truy cập. Không tự giữ toàn bộ backups vô hạn “cho chắc”.

### 26.4. Không đưa ra nghĩa vụ thời gian mang tính pháp luật chung

Luật, ngành, quốc gia và hợp đồng có thể đặt các thời hạn khác nhau. Đây là bài kỹ thuật; khi lập retention compliance thực tế, cần đối chiếu chính sách của tổ chức và tư vấn pháp lý phù hợp.

## 27. Cross-region recovery và vùng sự cố

Region A bị unavailable kéo dài:

~~~text
Primary Atlas cluster (Region A)
          |
     Backup snapshots
          |
          v
     Copy Region B
          |
          v
   Target Cluster Region B
          |
          v
  Application traffic cutover
~~~

### 27.1. Bản sao khác region không tự khôi phục traffic

Cần:

- Cluster restore target.
- Network endpoints/VPC peering/private links.
- Secrets và database users.
- KMS grants tại region/account đích.
- DNS/service discovery cutover.
- Application compatibility.
- Runbook rollback hoặc forward recovery.

### 27.2. Đừng đặt mọi key vào một failure domain

Nếu region A ngừng hoạt động và KMS key chỉ có thể truy cập trong region A, backup ở region B có thể gặp khó khăn khi decrypt. Điều kiện KMS cross-region/cross-provider phải được test.

### 27.3. Copy retention có thể khác source

Atlas hỗ trợ snapshot distribution/copies tùy policy, và retention của copied snapshots có giới hạn/ràng buộc riêng. Không tự cho rằng một bản sao vùng khác sẽ giữ lâu hơn source nếu chưa cấu hình và xác minh.

## 28. Chi phí lưu trữ và tối ưu retention

Chi phí backup không chỉ là số snapshots:

- Dữ liệu gốc/thay đổi mỗi ngày.
- Incremental snapshot dependencies.
- Tần suất snapshot.
- PIT/oplog retention.
- Cross-region/cross-account copies.
- Egress/transfer và restore.
- KMS operations.
- Immutable long-term storage.
- Restore drill environments.
- Object versioning/storage classes.

### 28.1. Ước lượng sơ bộ cho logical full backups

Giả sử mỗi full archive đã mã hóa có 100 GB, mỗi ngày 1 bản, giữ 30 ngày:

~~~text
100 GB x 30 = 3.000 GB ~ 3 TB
~~~

Chưa tính index metadata, replication, cross-region copies, object versions hoặc thay đổi dữ liệu. Atlas snapshots thường incremental nên **không** tính chi phí Atlas bằng cách nhân thẳng toàn bộ kích thước cluster với số snapshots.

### 28.2. Retention dài hơn chưa chắc an toàn hơn

Giữ backup một năm nhưng không có khả năng restore, mất key, hoặc có thể bị xóa cùng production vẫn yếu. Tối ưu theo RPO/RTO, nghĩa vụ pháp lý và khả năng phục hồi đã được kiểm chứng.

### 28.3. Cold archive

Long-term archives có storage rẻ hơn nhưng retrieval/rehydration thường chậm và có phí. Nếu RTO là 1 giờ, đừng đặt **bản duy nhất** vào tầng lưu trữ mất nhiều giờ mới đọc được.

## 29. Automated backup pipeline: kiểm soát từ đầu đến cuối

Một pipeline hợp lý:

~~~text
Scheduler
   |
   v
Acquire workload identity
   |
   v
Read source / Snapshot
   |
   v
Compress -> Encrypt
   |
   v
Upload immutable destination
   |
   v
Verify checksum / manifest
   |
   v
Register backup catalog
   |
   v
Scheduled isolated restore test
   |
   v
Alert / Retention lifecycle
~~~

### 29.1. Trạng thái job

Tối thiểu:

~~~text
STARTED
CAPTURED
ENCRYPTED
UPLOADED
VERIFIED
RESTORE_TESTED
EXPIRED
FAILED
~~~

Không ghi `VERIFIED` khi mới xong `UPLOADED`.

### 29.2. Không ghi secrets vào command/logs

- Không in full MongoDB URI.
- Không in cloud storage access key.
- Không log plaintext backup.
- Không in KMS key material.
- Không đưa private-key PEM vào CI artifacts.
- Chặn core dumps hoặc hạn chế quyền xem khi có secrets trong memory.

### 29.3. Exit status của pipeline

Nếu dùng shell pipeline, phải phát hiện lỗi từ `mongodump` lẫn công cụ mã hóa/upload. Nếu chỉ quan sát last command, có thể tạo một file mã hóa chứa dữ liệu rỗng/truncated mà báo thành công.

### 29.4. Idempotency

Backup ID/filename nên duy nhất và có manifest; retry không được ghi đè bản tốt bằng file hỏng. Nếu cùng backup ID được tạo lần hai, cần policy rõ về checksum, upload conditions và object versioning.

## 30. Observability và cảnh báo

### 30.1. Metrics

- `last_successful_backup_timestamp`.
- `last_verified_recovery_point`.
- `backup_job_duration_seconds`.
- `backup_artifact_bytes`.
- `backup_upload_errors_total`.
- `restore_drill_last_success_timestamp`.
- `restore_drill_duration_seconds`.
- `backup_objects_without_manifest`.
- `unreadable_encryption_key_count`.
- `retention_policy_violations`.
- `snapshot_delete_attempts`.
- `failed_kms_decrypt_requests`.

Tên trên là **metrics minh họa do ứng dụng/observability tự định nghĩa**, không phải tên metrics MongoDB xuất sẵn.

### 30.2. Alert thiết thực

- Không có backup verified mới trong 2× lịch backup.
- PIT window ngắn hơn business RPO requirement.
- Restore test thất bại.
- Chứng chỉ/kho KMS có lỗi.
- Snapshot bị xóa bất thường.
- Access policy rộng hơn baseline.
- Immutable object lock không được áp cho artifact mới.
- Offsite copy lag vượt mức chấp nhận.
- Backup catalog không khớp số objects thực tế.

### 30.3. Audit trail

Ai đổi retention? Ai tải backup về? Ai yêu cầu KMS Decrypt? Ai bắt đầu restore? Ai xóa snapshot? Logs cần có identity, timestamp, resource, outcome và change/incident ID, không chứa secret material.

## 31. Runbook khôi phục sau sự cố xóa nhầm

Ví dụ lúc 10:25, người vận hành phát hiện database bị xóa dữ liệu.

1. **Contain:** dừng các writes làm hỏng thêm và bảo vệ audit.
2. **Identify:** xác định timestamp thao tác gây lỗi, phạm vi collections/tenants.
3. **Select point:** chọn PIT ngay trước thao tác nếu nằm trong window.
4. **Verify:** kiểm tra snapshot/oplog hợp lệ, KMS key truy cập được.
5. **Choose target:** ưu tiên isolated recovery cluster; tránh đè production nếu không cần.
6. **Authorize:** yêu cầu phê duyệt quyền restore/decrypt.
7. **Restore:** thực hiện theo runbook Atlas/Backup tool.
8. **Validate:** kiểm tra counts, indexes, application invariants.
9. **Reconcile:** tái áp dụng các cập nhật hợp lệ sau recovery point nếu cần.
10. **Cutover:** chuyển traffic có kiểm soát.
11. **Audit:** ghi RPO/RTO thực tế và root cause.
12. **Improve:** cập nhật policy, permissions và drills.

### 31.1. PIT trước lỗi không luôn là toàn bộ câu trả lời

Khôi phục tới 10:24 có thể làm mất những giao dịch hợp lệ sau 10:24. Cần kế hoạch reconcile các writes hợp lệ, nhất là hệ thống thanh toán và tích hợp ngoài.

### 31.2. Restore vào target riêng

Đối với phần lớn bài tập và điều tra, isolated restore giúp phân tích sai lệch trước khi đưa dữ liệu trở lại production. Nó cũng giảm rủi ro restore nhầm đè dữ liệu hiện tại.

## 32. Ransomware và compromised backup operator

Một tài khoản backup writer bị lộ có thể làm gì?

Nếu có quyền:

~~~text
read database + write backup + delete backup + disable KMS
~~~

thì attacker có thể đánh cắp dữ liệu rồi xóa khả năng phục hồi.

### 32.1. Kiến trúc phòng thủ

- Writer chỉ ghi new backups, không delete.
- Retention/immutability không cho writer bypass.
- KMS admin khác backup writer.
- Backup copies ở account/region độc lập.
- Audit/KMS logs đưa tới sink khác quyền.
- Restore operator có quyền tạm thời và cần phê duyệt.
- Backup catalog và manifest có integrity protection.

### 32.2. Khi phát hiện tài khoản bị compromise

1. Thu hồi credential/access token.
2. Đánh giá hoạt động đọc/xóa/khóa KMS.
3. Xác minh số bản immutable/offsite còn nguyên.
4. Đổi credentials liên quan.
5. Restore drill trên những bản có độ tin cậy cao.
6. Rà soát khả năng exfiltration PII.
7. Giữ evidence và điều tra theo incident policy.

Không chỉ chạy backup mới rồi coi sự cố đã xử lý xong.

## 33. Một policy mẫu dạng YAML

Đây là **tài liệu cấu hình chính sách minh họa của tổ chức**, không phải YAML trực tiếp áp dụng vào Atlas hoặc MongoDB.

~~~yaml
policyId: mongo-orders-prod-v1
owner: platform-backup-team
dataClassification: confidential
source:
  platform: mongodb-atlas
  project: orders-prod
  deployment: dedicated
objectives:
  rpoMinutes: 5
  rtoMinutes: 60
backup:
  continuousPIT: true
  pitRestoreWindowDays: 7
  schedules:
    - frequency: hourly
      intervalHours: 6
      retentionDays: 7
    - frequency: daily
      retentionDays: 14
    - frequency: weekly
      retentionWeeks: 8
    - frequency: monthly
      retentionMonths: 12
  immutableCopy: true
  offsiteRegion: secondary-region
encryption:
  inTransitTLS: required
  atRest: managed
  customerManagedKey: enabled
access:
  backupWriterCanDelete: false
  restoreRequiresApproval: true
  kmsDecryptJustInTime: true
validation:
  verifyEveryBackup: true
  restoreDrillEveryDays: 30
  testOldKeyRecovery: true
retentionExceptions:
  legalHoldRequiresApproval: true
  handleDeletionRequests: true
~~~

### 33.1. Điều chỉnh policy trước khi đưa vào công cụ

- Kiểm tra tính hợp lệ giữa frequency và retention theo Atlas.
- Xác nhận Continuous Cloud Backup có ở tier.
- Khảo sát RPO/RTO thực tế và chi phí.
- Tách role mappings sang IAM/Atlas/DB RBAC.
- Xác định cách enforce immutableCopy.
- Xác nhận vùng lưu và KMS grant tương thích.
- Có mapping từ policy trừu tượng sang API/terraform cụ thể.

### 33.2. Policy được review định kỳ

Khi database tăng từ 100 GB lên 5 TB, RTO có thể thay đổi dù backup schedule giữ nguyên. Định kỳ test và cập nhật mục tiêu/chi phí.

## 34. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “Replica set là backup” | Xóa nhầm được replicate; cần recovery point độc lập |
| “Giữ 365 ngày nghĩa RPO thấp” | RPO phụ thuộc tần suất/PIT và backup hợp lệ |
| “PIT window bằng monthly retention” | PIT phụ thuộc oplog/restore window |
| “Có backup file là restore được” | Cần integrity, key, quyền, compatibility, test |
| “Mongodump --gzip đã mã hóa” | gzip là nén |
| “TLS của DB mã hóa luôn file dump” | TLS chỉ bảo vệ đường truyền |
| “Atlas backup không mã hóa” | Atlas snapshots có encryption at rest |
| “CMK có thể xóa ngay sau rotation” | Snapshots cũ có thể cần old key |
| “Key bị revoke không ảnh hưởng backup” | Có thể làm restore không thể giải mã |
| “Snapshot immutable thì không ai xóa được” | Cần phân biệt immutability với delete/retention protection |
| “Offsite region luôn an toàn” | Cùng IAM/KMS vẫn là shared failure domain |
| “Backup writer nên có quyền delete để dọn dẹp” | Nên tách lifecycle/deletion |
| “DB readWrite đủ để tạo Atlas snapshot” | Atlas control plane roles là lớp riêng |
| “Có Atlas Project Owner thì decrypt KMS chắc được” | KMS grants/keys là lớp riêng |
| “Restore user có thể dùng mọi quyền” | Chỉ cấp quyền cần thiết, có approvals |
| “mongodump --oplog dùng được trên sharded cluster toàn bộ” | Có hạn chế; cần coordinated backup |
| “mongorestore --drop vô hại” | Có thể xóa data và user metadata ở target |
| “Job exit 0 chứng minh recoverable” | Cần kiểm tra file, key và restore drill |
| “Hash file chứng minh dữ liệu nghiệp vụ đúng” | Checksum không thay validation |
| “Xóa production nghĩa xóa cả backups” | Backup cũ có thể chứa PII |
| “Bản sao càng nhiều càng tốt” | Cần cân bằng retention, chi phí, privacy |
| “Restore luôn tự gắn ứng dụng hoạt động” | Còn network/DNS/secrets/app checks |
| “RPO 5 phút nghĩa RTO 5 phút” | Hai mục tiêu khác nhau |
| “Có thể test restore thẳng vào production” | Nên dùng isolated target |
| “Giữ backup không cần giữ keys” | Mất key có thể mất khả năng giải mã |
| “Một tài khoản quản lý tất cả đơn giản hơn” | Blast radius và rủi ro insider cao |

## 35. Bài tập thực hành

Các bài yêu cầu DDL hoặc restore phải chạy trong môi trường **lab cô lập**. Không sửa Atlas Backup Compliance Policy hoặc xóa backup thật để thử.

### Bài 1 — Phân biệt replica và backup

Vì sao replica set ba nodes không bảo vệ được lỗi `db.orders.drop()` được replicate thành công?

### Bài 2 — RPO/RTO

Snapshot lúc 10:00, sự cố lúc 10:25, dịch vụ khôi phục lúc 11:10. RPO/RTO quan sát khoảng bao nhiêu nếu không có PIT?

### Bài 3 — GFS retention

Thiết kế lịch hourly/daily/weekly/monthly cho hệ thống yêu cầu khôi phục lỗi trong 14 ngày và audit 12 tháng.

### Bài 4 — PIT window

Nếu monthly snapshot giữ 12 tháng nhưng PIT window 7 ngày, có thể khôi phục tới 11:59:59 của một ngày cách đây 8 tháng không?

### Bài 5 — Chọn tần suất

Với RPO 15 phút và không có PIT, backup mỗi 6 giờ có phù hợp không? Vì sao?

### Bài 6 — Atlas backup policy

Nêu các frequency tiers Atlas hỗ trợ. Khi snapshot trùng daily và weekly policy, retention nào áp dụng?

### Bài 7 — Compliance protection

Backup Compliance Policy giúp ngăn những thao tác nào? Vì sao cần đánh giá kỹ trước khi bật?

### Bài 8 — 3-2-1-1-0

Hãy áp dụng nguyên tắc này cho MongoDB production, object store offsite và restore drill.

### Bài 9 — Quyền độc lập

Hai backup copies ở khác region nhưng cùng IAM role có quyền delete. Đây có phải hai failure domains thực sự độc lập không?

### Bài 10 — TLS và file encryption

Phân biệt TLS connection, MongoDB at-rest encryption và encryption của exported BSON archive.

### Bài 11 — gzip

`mongodump --archive --gzip` có mã hóa file output không? Cần lớp bảo vệ nào nếu file lưu ngoài Atlas?

### Bài 12 — KMS

Một backup cũ cần CMK key version K1. Nếu K1 bị hủy, điều gì xảy ra?

### Bài 13 — Integrity

Hash ciphertext giúp phát hiện gì? Tại sao checksum cùng nơi bị attacker sửa không đủ?

### Bài 14 — Least privilege

Phân biệt quyền backup writer, backup restore operator, retention admin và KMS admin.

### Bài 15 — MongoDB roles

Role `backup` và `restore` trong `admin` có giống Atlas Project Backup Manager không?

### Bài 16 — Oplog replay

Vì sao `mongorestore --oplogReplay` có requirements privilege cao và chỉ nên chạy trong runbook được phê duyệt?

### Bài 17 — Sharded cluster

Vì sao dump mỗi shard vào một thời điểm ngẫu nhiên không tạo backup nhất quán toàn cluster?

### Bài 18 — mongodump --oplog

`mongodump --oplog` có kết hợp `--db` hoặc dump qua mongos toàn sharded cluster không? Giải thích.

### Bài 19 — Restore target

Nêu ít nhất 5 checks trước khi chạy `mongorestore --drop` hoặc Atlas cluster-level restore.

### Bài 20 — Cross-region và KMS

Offsite snapshot ở region B nhưng CMK chỉ phục vụ được region A. Rủi ro nào cần kiểm thử?

### Bài 21 — Permission matrix

Thiết kế ma trận “create/list/read/delete/restore/decrypt” cho backup writer, auditor, restore operator, retention admin.

### Bài 22 — Restore drill

Thiết kế bài kiểm tra khôi phục backup 90 ngày tuổi, có chứng thực KMS và kiểm tra application invariants.

### Bài 23 — Alerting

Định nghĩa cảnh báo khi `last_verified_recovery_point` đã cũ quá RPO. Tại sao alert “job chạy” chưa đủ?

### Bài 24 — Dữ liệu cá nhân

Một người dùng bị xóa khỏi production nhưng có trong backup một tháng trước. Khi restore backup đó cần làm gì trước khi mở dịch vụ?

### Bài 25 — Legal hold

Khi nào legal hold cho phép giữ lâu hơn retention thông thường? Ai phê duyệt và rà soát?

### Bài 26 — Object lock

Một object encrypted bị ransomware cố xóa. Những quyền và controls nào phải chặn thao tác?

### Bài 27 — Chi phí

30 full logical backups, mỗi bản 100 GB đã nén/mã hóa, tổng dữ liệu số thô là bao nhiêu, chưa tính replication/copies?

### Bài 28 — Incident response

Backup writer credential bị lộ. Lập các bước thu hồi, xác minh bản immutable, KMS, restore và audit.

### Bài 29 — Atlas restore access

Những project roles nào có thể bắt đầu restore job? Vì sao quyền khôi phục liên project đòi kiểm tra cả source và target?

### Bài 30 — Policy end-to-end

Thiết kế một policy có RPO 5 phút, RTO 1 giờ, PIT 7 ngày, snapshot tiers, một immutable offsite copy, KMS key lifecycle, tách RBAC và monthly restore drill. Nêu những thành phần phải benchmark trước production.

## 36. Checklist sẵn sàng production

### Recovery objectives và retention

- [ ] RPO/RTO được chủ sở hữu nghiệp vụ phê duyệt.
- [ ] Đã chọn backup mechanism theo topology Atlas/self-managed.
- [ ] Có retention tiers theo giờ/ngày/tuần/tháng/năm phù hợp.
- [ ] PIT restore window đáp ứng mục tiêu.
- [ ] Phân biệt PIT window với archival retention.
- [ ] Có owner, review date và exemption process.
- [ ] Có legal hold/deletion request handling.
- [ ] Đã đánh giá chi phí retention và cross-region copies.

### Bản sao và khả năng tồn tại

- [ ] Không dùng replication thay cho backup.
- [ ] Có offsite copy và failure-domain separation.
- [ ] Có immutable/offline copy phù hợp.
- [ ] Backup writer không xóa được toàn lịch sử.
- [ ] Retention lifecycle không bypass lock trái phép.
- [ ] Có manifest và integrity checks.
- [ ] Theo dõi last verified recoverable point.

### Mã hóa và khóa

- [ ] TLS cho backup/restore traffic.
- [ ] Không nhầm gzip với encryption.
- [ ] Backup archives ngoài Atlas được mã hóa.
- [ ] Có key manager/KMS được phân quyền.
- [ ] Khóa cũ được giữ đủ để đọc historical backups.
- [ ] Có recovery plan khi KMS unavailable.
- [ ] Có test decrypt bản mới và bản cũ.
- [ ] Không log plaintext/password/private key.

### Phân quyền

- [ ] Database backup role và restore role tách biệt.
- [ ] Atlas roles theo từng thao tác được kiểm tra.
- [ ] Object writer/list/read/delete permissions được tách.
- [ ] KMS decrypt không tự cấp cho mọi backup operators.
- [ ] Restore production yêu cầu approval.
- [ ] Có MFA/JIT/break-glass theo policy.
- [ ] Audit log các lần đọc/decrypt/delete/restore.
- [ ] Không có tài khoản chung kiểm soát toàn backup chain.

### Khôi phục và diễn tập

- [ ] Restore test được tự động hóa hoặc lên lịch.
- [ ] Có isolated target và verification suite.
- [ ] Test RTO/RPO trên dữ liệu đủ lớn.
- [ ] Kiểm tra indexes, users/roles và application invariants.
- [ ] Có restore thử historical backup và cross-region.
- [ ] Không dùng `--drop` trên production test.
- [ ] Đã xử lý tính nhất quán của replica set/sharded cluster.
- [ ] Có runbook cho ransomware, xóa nhầm, KMS failure.
- [ ] Có post-incident evidence và cải tiến policy.

## 37. Tổng kết

Chính sách MongoDB backup đáng tin cậy cần kết hợp **giữ bản sao, mã hóa, phân quyền và khả năng kiểm chứng**:

- **Retention:** chọn tần suất và thời hạn theo RPO/RTO, nhu cầu audit, pháp lý và chi phí; cần phân biệt snapshot tiers với PIT restore window.
- **Atlas:** Cloud Backup, Continuous Cloud Backup và Backup Compliance Policy cung cấp những controls quản lý snapshots, recovery windows và chống xóa trong các tier phù hợp.
- **Self-managed:** `mongodump`/`mongorestore` hữu ích nhưng có giới hạn tính nhất quán, đặc biệt với sharded clusters; production cần quy trình phối hợp phù hợp.
- **Bất biến:** offsite/immutable copies giảm rủi ro ransomware, nhưng không giải quyết việc key bị hủy hoặc IAM quá rộng.
- **Mã hóa:** TLS, database at rest, encrypted backup object và client-side encryption là các lớp khác nhau; KMS keys phải tồn tại đủ lâu để giải mã backup lịch sử.
- **Phân quyền:** tách quyền backup writer, restore, delete/retention và KMS decrypt; giữ audit và phê duyệt cho thao tác rủi ro.
- **Restore drill:** một backup chỉ thật sự đáng tin khi có thể giải mã, phục hồi dữ liệu/ứng dụng và đạt thời gian mục tiêu.

Một thiết kế tốt không chỉ trả lời **“chúng ta giữ bao nhiêu bản sao?”** mà còn trả lời được **“bản nào còn dùng được, ai được phép lấy nó, giải mã bằng khóa nào, và bao lâu có thể phục hồi đúng dữ liệu?”**

## Tài liệu tham khảo chính thức

- [MongoDB Atlas — Guidance for Atlas Backups](https://www.mongodb.com/docs/atlas/architecture/current/backups/)
- [MongoDB Atlas — Back Up, Restore, and Archive Data](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)
- [MongoDB Atlas — Manage Backup Policies](https://www.mongodb.com/docs/atlas/backup/cloud-backup/configure-backup-policy/)
- [MongoDB Atlas — Backup Scheduling, Retention, and On-Demand Snapshots](https://www.mongodb.com/docs/atlas/backup/cloud-backup/scheduling/)
- [MongoDB Atlas — Configure a Backup Compliance Policy](https://www.mongodb.com/docs/atlas/backup/cloud-backup/backup-compliance-policy/)
- [MongoDB Atlas — Snapshot Management](https://www.mongodb.com/docs/atlas/backup/cloud-backup/snapshot-management/)
- [MongoDB Atlas — Continuous Cloud Backup/PIT Restore](https://www.mongodb.com/docs/atlas/recover-pit-continuous-cloud-backup/)
- [MongoDB Atlas — Storage Engine and Cloud Backup Encryption](https://www.mongodb.com/docs/atlas/backup/cloud-backup/cloud-backup-encryption/)
- [MongoDB Atlas — Encryption at Rest using Customer Key Management](https://www.mongodb.com/docs/atlas/security-kms-encryption/)
- [MongoDB Atlas — Restore from a Snapshot](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-from-snapshot/)
- [MongoDB Atlas — Snapshot Distribution](https://www.mongodb.com/docs/atlas/backup/cloud-backup/snapshot-distribution/)
- [MongoDB Database Tools — mongodump](https://www.mongodb.com/docs/database-tools/mongodump/)
- [MongoDB Database Tools — mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [MongoDB Database Tools — mongorestore Access and Usage](https://www.mongodb.com/docs/database-tools/mongorestore/mongorestore-behavior-access-usage/)
- [MongoDB Manual — Built-In Roles](https://www.mongodb.com/docs/manual/reference/built-in-roles/)
- [MongoDB Manual — Back Up and Restore Self-Managed Deployments](https://www.mongodb.com/docs/manual/core/backups/)
