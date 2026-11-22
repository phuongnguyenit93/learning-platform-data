# Diễn tập phục hồi, failover và kiểm chứng yêu cầu nghiệp vụ

Một hệ thống PostgreSQL chỉ được xem là có khả năng phục hồi khi đội ngũ có thể khôi phục dữ liệu và đưa ứng dụng trở lại hoạt động trong giới hạn đã cam kết. Có backup hoặc standby chưa đủ để chứng minh điều đó. Cần thường xuyên diễn tập khôi phục, chuyển đổi máy chủ, kiểm tra dữ liệu sau sự cố và xác nhận các luồng nghiệp vụ quan trọng vẫn hoạt động đúng.

Trong chương Kiểm thử của Database Engine Relational PostgreSQL, nội dung này tập trung vào cách lập kế hoạch và thực hiện các bài diễn tập cho backup/restore, point-in-time recovery (PITR), failover và kiểm chứng yêu cầu nghiệp vụ. Mục tiêu là đo được thời gian phục hồi, lượng dữ liệu có thể mất, tính toàn vẹn của dữ liệu và khả năng tiếp tục phục vụ người dùng.

## 1. Các khái niệm phục hồi cần phân biệt

### 1.1. Backup, restore và PITR

**Backup** là bản lưu dữ liệu dùng để khôi phục khi dữ liệu hoặc máy chủ bị mất, hỏng hay thay đổi ngoài ý muốn. PostgreSQL hỗ trợ nhiều cách tạo backup, trong đó có backup vật lý bằng `pg_basebackup`, lưu trữ WAL liên tục và backup logic bằng `pg_dump`/`pg_dumpall`.

**Restore** là quá trình dùng backup để dựng lại database hoặc cluster. Một bản backup chỉ có giá trị vận hành khi đã thử khôi phục thành công trên môi trường độc lập và kiểm tra được dữ liệu sau khôi phục.

**Point-in-time recovery (PITR)** là khôi phục một PostgreSQL cluster về một thời điểm hoặc vị trí xác định bằng cách kết hợp base backup với chuỗi WAL cần thiết. PITR hữu ích khi một giao dịch hợp lệ về mặt SQL nhưng sai về nghiệp vụ, chẳng hạn người vận hành xóa nhầm dữ liệu hoặc một batch ghi đè giá trị sai. Có thể khôi phục tới thời điểm ngay trước thao tác gây lỗi, sau đó trích xuất hoặc chuyển dữ liệu cần thiết.

Backup vật lý và WAL archive thường được dùng để phục hồi toàn cluster về một thời điểm. Backup logic như `pg_dump` thích hợp cho việc khôi phục database, schema hoặc đối tượng được chọn, nhưng không thay thế trực tiếp cơ chế PITR vật lý ở mức cluster.

### 1.2. Replication và failover

Replication duy trì một bản sao của dữ liệu trên một máy chủ khác. Với physical streaming replication, standby nhận và replay WAL từ primary. Khi primary gặp sự cố, một standby đủ điều kiện có thể được promote thành primary mới.

**Failover** là chuyển dịch vụ sang một máy chủ dự phòng khi primary không còn phục vụ được. Failover thường xảy ra ngoài kế hoạch do lỗi máy chủ, lưu trữ, mạng hoặc vùng triển khai.

**Switchover** là chuyển vai trò primary/standby có kế hoạch, thường phục vụ bảo trì, nâng cấp hoặc kiểm thử. Vì primary hiện tại vẫn hoạt động, có thể kiểm soát việc dừng ghi và đồng bộ standby trước khi chuyển vai trò.

Replication không phải backup. Một lệnh `DELETE` nhầm, một batch cập nhật sai hoặc dữ liệu bị mã hóa bởi ứng dụng độc hại có thể được truyền sang standby. Backup độc lập và khả năng PITR vẫn cần thiết để quay lại trạng thái trước sự cố logic.

### 1.3. RPO và RTO

Hai chỉ số cơ bản để mô tả mục tiêu phục hồi:

- **RPO (Recovery Point Objective)**: lượng dữ liệu tối đa mà tổ chức chấp nhận mất, thường biểu diễn bằng thời gian. Ví dụ RPO 5 phút nghĩa là sau sự cố, phần dữ liệu đã xác nhận trước thời điểm mất có thể bị mất không vượt quá khoảng 5 phút.
- **RTO (Recovery Time Objective)**: thời gian tối đa chấp nhận để khôi phục dịch vụ về mức hoạt động được yêu cầu. Ví dụ RTO 30 phút nghĩa là các chức năng quan trọng phải phục hồi trong 30 phút kể từ mốc bắt đầu sự cố đã thống nhất.

RPO/RTO là yêu cầu nghiệp vụ và vận hành, không phải thuộc tính tự động được bảo đảm chỉ vì đã bật replication hoặc có backup. Phải đo trong diễn tập thực tế.

```text
Thời điểm giao dịch cuối cùng được xác nhận
                  |
                  v
           Sự cố xảy ra
                  |
                  |<------ khoảng dữ liệu có thể mất ------>|
                  |                                         |
                  v                                         v
           Phát hiện sự cố                         Điểm phục hồi
                  |                                         |
                  |<------------- RTO --------------------->|
                  v                                         v
           Bắt đầu xử lý                         Ứng dụng hoạt động
```

Khi đo RTO, cần thống nhất điểm bắt đầu. Có thể bắt đầu từ lúc sự cố thực tế xảy ra hoặc từ lúc hệ thống giám sát phát hiện sự cố. Nếu tổ chức chọn mốc phát hiện, phải ghi rõ thời gian phát hiện và thời gian xảy ra ước tính để không đánh giá thấp thời gian gián đoạn.

## 2. Xác định yêu cầu phục hồi từ nghiệp vụ

Trước khi chọn kỹ thuật PostgreSQL, cần xác định ứng dụng phải khôi phục điều gì. Một database có thể mở cổng và trả lời `SELECT 1` nhưng vẫn chưa đáp ứng yêu cầu kinh doanh nếu người dùng không đăng nhập được, đơn hàng không thể tạo hoặc số dư không còn nhất quán.

### 2.1. Lập danh mục dịch vụ và dữ liệu quan trọng

Với mỗi dịch vụ, ghi nhận:

| Thông tin | Câu hỏi cần trả lời |
|---|---|
| Quy trình nghiệp vụ | Người dùng cần hoàn thành thao tác nào? |
| Dữ liệu quan trọng | Bảng, schema, sequence, large object hoặc dữ liệu cấu hình nào cần phục hồi? |
| Mức độ ưu tiên | Chức năng nào phải hoạt động trước, chức năng nào có thể chờ? |
| RPO | Tổ chức chấp nhận mất tối đa bao nhiêu dữ liệu đã xác nhận? |
| RTO | Dịch vụ phải hoạt động lại trong bao lâu? |
| Phụ thuộc | Có cần DNS, secret, chứng chỉ, queue, object storage, API bên ngoài hoặc dịch vụ xác thực không? |
| Chủ sở hữu | Ai quyết định dữ liệu và quy trình đã phục hồi đúng? |

Ví dụ, hệ thống bán hàng có thể yêu cầu tra cứu sản phẩm hoạt động lại trong 15 phút, còn báo cáo lịch sử có thể chờ vài giờ. Dữ liệu đơn hàng đã xác nhận có thể có RPO gần bằng 0, trong khi dữ liệu cache có thể được tạo lại.

### 2.2. Chuyển RPO/RTO thành tiêu chí kiểm thử

Yêu cầu phải có cách đo cụ thể. Ví dụ:

| Yêu cầu | Tiêu chí đo |
|---|---|
| RPO không quá 5 phút | Xác định giao dịch cuối cùng đã được ứng dụng xác nhận trước sự cố và giao dịch cuối cùng còn tồn tại sau phục hồi; tính khoảng cách thời gian và đối chiếu ID giao dịch. |
| RTO không quá 30 phút | Đo từ mốc bắt đầu sự cố đã thống nhất tới khi kiểm thử giao dịch nghiệp vụ thành công và hệ thống đáp ứng ngưỡng hiệu năng tối thiểu. |
| Không mất đơn hàng đã xác nhận | Đối chiếu ID đơn hàng từ nhật ký xác nhận độc lập với dữ liệu sau phục hồi. |
| Không nhân đôi thanh toán | Đối chiếu mã idempotency, mã giao dịch cổng thanh toán và số lượng bản ghi ghi nhận thanh toán. |
| Báo cáo tài chính cân bằng | Tính lại tổng debit/credit hoặc số dư từ dữ liệu đã phục hồi và so sánh với kết quả kiểm soát. |

Nên lưu dấu giao dịch kiểm thử ở một nơi độc lập với database đang diễn tập, ví dụ hệ thống log hoặc bộ điều phối kiểm thử. Nếu chỉ dựa vào dữ liệu trong database bị sự cố, đội ngũ có thể không biết giao dịch nào đã được ứng dụng thông báo thành công trước khi máy chủ mất kết nối.

## 3. Chuẩn bị nền tảng phục hồi PostgreSQL

### 3.1. Chọn mô hình backup phù hợp

Các cơ chế thường dùng có phạm vi khác nhau:

| Cơ chế | Phạm vi | Mục đích thường gặp |
|---|---|---|
| `pg_dump` | Một database, định dạng logic | Di chuyển hoặc khôi phục database/schema/đối tượng được chọn. |
| `pg_dumpall` | Các database và đối tượng toàn cluster ở dạng SQL | Sao lưu role và các đối tượng cluster cùng database theo dạng logic. |
| `pg_basebackup` | Base backup vật lý của cluster | Dựng lại cluster hoặc tạo standby. |
| WAL archiving | Chuỗi WAL liên tục | PITR và phục hồi các thay đổi sau base backup. |
| Storage snapshot | Ảnh chụp volume hoặc filesystem | Backup nhanh khi được phối hợp nhất quán với PostgreSQL và hệ thống lưu trữ. |

Một chiến lược đầy đủ thường kết hợp base backup định kỳ với WAL archive liên tục, bản sao lưu ở vị trí độc lập và backup logic cho các nhu cầu khôi phục cấp đối tượng. Snapshot storage cần tuân thủ hướng dẫn nhất quán của PostgreSQL và nền tảng lưu trữ; không nên giả định rằng chụp một volume đang hoạt động tùy ý sẽ tạo ra backup hợp lệ.

### 3.2. Bật WAL archiving

Ví dụ cấu hình trong `postgresql.conf` cho một primary cần PITR:

```conf
wal_level = replica
archive_mode = on
archive_command = 'test ! -f /srv/pg_wal_archive/%f && cp %p /srv/pg_wal_archive/%f'
```

Đây là ví dụ minh họa cho môi trường thử nghiệm. Trong production, cần dùng cơ chế lưu trữ an toàn và đáng tin cậy, kiểm soát quyền truy cập, dung lượng, mã hóa, retry và cảnh báo khi archive thất bại. Không dùng một thư mục nằm cùng volume với data directory làm bản backup duy nhất.

`archive_command` phải trả về mã thành công chỉ khi WAL segment đã được lưu an toàn. Nếu lệnh báo thành công trước khi dữ liệu thực sự bền vững, PostgreSQL có thể tái sử dụng WAL mà hệ thống backup chưa lưu được. Nếu lệnh luôn thất bại, `pg_wal` có thể tăng dung lượng và làm đầy ổ đĩa.

Có thể kiểm tra trạng thái archive trên primary:

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
```

Chỉ số `failed_count` tăng là tín hiệu cần điều tra. Cần giám sát cả dung lượng filesystem, thời gian kể từ lần archive thành công gần nhất và khả năng đọc lại WAL từ nơi lưu trữ.

### 3.3. Tạo base backup vật lý

Ví dụ dùng `pg_basebackup` để tạo backup vào thư mục đích:

```bash
pg_basebackup \
  -h db-primary.example.net \
  -p 5432 \
  -U replication_user \
  -D /backup/pg/base_2026_11_14 \
  -Fp \
  -Xs \
  -P
```

Các tùy chọn quan trọng trong ví dụ:

- `-h`, `-p`, `-U`: máy chủ, cổng và role dùng để lấy backup.
- `-D`: thư mục đích phải được chuẩn bị theo yêu cầu của `pg_basebackup`.
- `-Fp`: xuất theo định dạng plain directory.
- `-Xs`: stream WAL cần thiết trong quá trình backup.
- `-P`: hiển thị tiến độ.

Role backup cần quyền replication và cấu hình kết nối phù hợp. Cần quản lý chứng thực và TLS theo chính sách bảo mật. Tùy chọn `-R` có thể tạo cấu hình để thư mục backup khởi động như standby; khi tạo bản phục hồi độc lập để kiểm tra, cần hiểu rõ các file cấu hình được tạo và không để máy chủ kiểm thử vô tình tham gia replication hoặc nhận traffic production.

Sau khi tạo backup ở định dạng có manifest, có thể dùng `pg_verifybackup` để kiểm tra nội dung backup theo manifest:

```bash
pg_verifybackup /backup/pg/base_2026_11_14
```

Lệnh này kiểm tra tính nhất quán của các file backup theo khả năng của công cụ. Nó không chứng minh rằng ứng dụng có thể khởi động, truy vấn đúng hoặc đáp ứng yêu cầu nghiệp vụ. Restore thực tế vẫn là bằng chứng quan trọng hơn.

### 3.4. Theo dõi standby và replication lag

Trên standby, có thể kiểm tra trạng thái recovery và WAL receiver:

```sql
SELECT pg_is_in_recovery();

SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_wal_receiver;
```

Trên primary, xem các standby đang kết nối:

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
```

Các trường lag có thể là `NULL`, nhất là khi không có hoạt động WAL gần đây; cần kết hợp LSN, timestamp và workload kiểm thử thay vì diễn giải một giá trị đơn lẻ. Có thể dùng `pg_wal_lsn_diff()` để tính khoảng cách LSN giữa các vị trí.

```sql
SELECT
    pg_wal_lsn_diff(sent_lsn, replay_lsn) AS bytes_not_replayed
FROM pg_stat_replication;
```

Khoảng cách LSN thể hiện lượng WAL chưa replay tại thời điểm lấy mẫu, không tự chuyển thành số phút mất dữ liệu. Muốn đo RPO, cần đối chiếu giao dịch nghiệp vụ đã commit và đã được xác nhận.

### 3.5. Bảo vệ backup

Backup phải có khả năng tồn tại khi primary hoặc tài khoản production bị xâm phạm. Các biện pháp thường gồm:

- Lưu bản backup ở hệ thống hoặc tài khoản lưu trữ tách biệt với máy chủ database.
- Giới hạn quyền xóa và sửa; dùng immutable/object lock nếu nền tảng hỗ trợ.
- Mã hóa khi truyền và khi lưu; quản lý khóa mã hóa độc lập và có quy trình khôi phục khóa.
- Lưu metadata về phiên bản PostgreSQL, extension, cấu hình, tablespace, checksum và thời điểm backup.
- Theo dõi thời hạn lưu giữ base backup và WAL để bảo đảm còn đủ chuỗi phục hồi.
- Thử khôi phục từ chính kho backup đã lưu, không chỉ từ bản sao tạm trên máy backup.

## 4. Diễn tập restore và point-in-time recovery

### 4.1. Lập kế hoạch trước khi khôi phục

Trước khi chạy restore, cần xác định:

1. Sự cố giả định và điểm cần khôi phục.
2. Base backup được chọn và chuỗi WAL cần thiết.
3. Phiên bản PostgreSQL và extension tương thích.
4. Vị trí data directory, tablespace, quyền filesystem và dung lượng đĩa.
5. Cách khôi phục cấu hình, chứng chỉ, secret và role.
6. Mạng cách ly để database phục hồi không nhận traffic hoặc kết nối tới hệ thống production ngoài ý muốn.
7. Người xác nhận kỹ thuật và người xác nhận nghiệp vụ.

Nên thực hiện lần đầu trên máy chủ hoặc container phục hồi độc lập. Nếu mục tiêu là kiểm tra backup, không ghi đè data directory production đang hoạt động.

### 4.2. Khôi phục từ base backup và WAL archive

Quy trình vật lý tổng quát:

1. Cấp máy chủ và volume đích có dung lượng phù hợp.
2. Khôi phục base backup vào data directory theo hướng dẫn của phiên bản PostgreSQL đang dùng.
3. Cấu hình quyền sở hữu file và quyền truy cập.
4. Cấu hình `restore_command` để lấy WAL segment từ kho archive.
5. Tạo file `recovery.signal` trong data directory để yêu cầu PostgreSQL vào chế độ recovery.
6. Khởi động PostgreSQL và theo dõi log cho tới khi recovery hoàn tất hoặc dừng tại recovery target.
7. Kiểm tra dữ liệu, cấu hình, quyền và ứng dụng trước khi đưa dịch vụ vào sử dụng.

Với PostgreSQL 12 trở lên, cấu hình recovery được đặt trong `postgresql.conf` hoặc file cấu hình được include; file `recovery.signal` kích hoạt archive recovery. Các phiên bản cũ hơn có cách cấu hình khác, vì vậy phải dùng tài liệu đúng major version.

Ví dụ cấu hình phục hồi từ WAL archive:

```conf
restore_command = 'cp /srv/pg_wal_archive/%f %p'
recovery_target_timeline = 'latest'
```

Lệnh `restore_command` là ví dụ với archive nằm trên filesystem cục bộ của máy phục hồi. Trong thực tế có thể dùng công cụ backup chuyên dụng hoặc lệnh tải từ object storage. Lệnh phải trả về mã lỗi phù hợp khi file không tồn tại và phải ghi file đích đúng cách.

### 4.3. Khôi phục tới một thời điểm cụ thể

PITR cho phép chọn thời điểm trước thao tác gây lỗi. Ví dụ, giả sử lệnh xóa nhầm xảy ra lúc 10:42 UTC. Có thể đặt target về một thời điểm ngay trước đó:

```conf
restore_command = 'cp /srv/pg_wal_archive/%f %p'
recovery_target_time = '2026-11-14 10:41:30+00'
recovery_target_inclusive = on
recovery_target_timeline = 'latest'
recovery_target_action = 'pause'
```

Sau đó tạo file tín hiệu:

```bash
touch /var/lib/postgresql/data/recovery.signal
```

Khi PostgreSQL dừng replay tại target với `recovery_target_action = 'pause'`, có thể kết nối kiểm tra dữ liệu trước khi quyết định tiếp tục. Nếu xác nhận muốn hoàn tất recovery và cho phép ghi, có thể gọi:

```sql
SELECT pg_wal_replay_resume();
```

Hoặc chọn `recovery_target_action = 'promote'` để PostgreSQL promote sau khi đạt target. Chọn `pause` thuận tiện cho diễn tập kiểm tra trước khi chốt điểm phục hồi; chọn `promote` khi quy trình đã xác định target và muốn máy chủ trở thành một primary mới.

`recovery_target_time` là thời điểm giao dịch được commit theo timestamp của PostgreSQL. `recovery_target_inclusive` quyết định có bao gồm giao dịch đúng target hay không. Khi kiểm tra thao tác sai, nên dùng một mốc có khoảng cách an toàn trước giao dịch lỗi, sau đó xác minh bằng ID giao dịch và dữ liệu nghiệp vụ. Không dựa duy nhất vào đồng hồ của máy ứng dụng nếu đồng hồ giữa các hệ thống chưa đồng bộ.

Các recovery target khác gồm `recovery_target_lsn`, `recovery_target_xid` và `recovery_target_name` (khi đã tạo named restore point). Chúng hữu ích khi quy trình có thể ghi lại vị trí WAL hoặc tên restore point rõ ràng. Cần đọc tài liệu phiên bản PostgreSQL đang vận hành để xác định cú pháp và hành vi chính xác.

### 4.4. Kiểm tra sau restore

Kiểm tra ở cấp PostgreSQL:

```sql
SELECT version();
SELECT pg_is_in_recovery();
SELECT pg_last_wal_replay_lsn();
SELECT pg_last_xact_replay_timestamp();
```

`pg_is_in_recovery()` cho biết máy chủ còn đang ở recovery hay đã được promote. `pg_last_wal_replay_lsn()` và `pg_last_xact_replay_timestamp()` giúp quan sát tiến độ replay; timestamp có thể `NULL` nếu chưa replay giao dịch phù hợp và không nên dùng đơn lẻ để xác nhận RPO.

Tiếp theo, kiểm tra:

- Database, schema, bảng, index, sequence, extension và tablespace cần thiết có tồn tại.
- Role, membership, quyền truy cập, default privileges và cấu hình xác thực đã được khôi phục.
- Các bảng quan trọng có thể đọc và các truy vấn nghiệp vụ đại diện chạy được.
- Constraint, quan hệ khóa ngoại và quy tắc dữ liệu còn thỏa mãn.
- Ứng dụng có thể kết nối bằng đúng role và secret dự kiến.
- Các job định kỳ, scheduler, queue consumer và integration không chạy nhầm trong môi trường restore.

Sau khi restore, có thể cần cập nhật thống kê bằng `ANALYZE` để planner có thông tin phù hợp. Không chạy `VACUUM FULL` hoặc các thao tác bảo trì nặng như một bước mặc định của mọi lần restore; chỉ thực hiện khi có lý do cụ thể.

### 4.5. Restore logic cho một database hoặc nhóm đối tượng

Khi cần khôi phục một database hoặc schema từ backup logic, có thể dùng `pg_restore` với archive do `pg_dump` tạo:

```bash
createdb -h restore-db.example.net -U restore_admin sales_restore

pg_restore \
  -h restore-db.example.net \
  -U restore_admin \
  -d sales_restore \
  --verbose \
  /backup/pg/sales_2026_11_14.dump
```

Nếu archive có nhiều database hoặc đối tượng cluster như role, cần có kế hoạch khôi phục tương ứng. `pg_dump` không tự chứa mọi cấu hình máy chủ, file cấu hình, chứng chỉ, cron của hệ điều hành hoặc các phụ thuộc bên ngoài. Cần lưu các thành phần này theo một quy trình riêng.

## 5. Diễn tập switchover và failover

### 5.1. Kiểm tra trạng thái trước khi chuyển vai trò

Trước khi promote standby, phải biết:

- Primary hiện tại còn hoạt động hay đã thực sự mất quyền ghi.
- Standby có phải ứng viên phù hợp và đang nhận WAL không.
- LSN đã nhận, flush và replay trên standby tới đâu.
- Replication đồng bộ hay bất đồng bộ và có giao dịch đã xác nhận nào chưa được standby nhận hay không.
- Ứng dụng kết nối qua endpoint nào, connection pool có thể làm mới kết nối ra sao.
- Ai có quyền quyết định promote và ai thực hiện việc cô lập primary cũ.

Không được promote một standby trong khi primary cũ vẫn có thể nhận ghi từ ứng dụng, trừ khi kiến trúc có cơ chế fencing và điều phối leader đã được thiết kế, kiểm thử rõ ràng. Nếu hai máy cùng nhận ghi độc lập, hệ thống có thể rơi vào split-brain và tạo hai lịch sử dữ liệu khác nhau.

### 5.2. Switchover có kế hoạch

Một quy trình switchover thủ công tổng quát có thể gồm:

1. Thông báo cửa sổ bảo trì và xác nhận người chịu trách nhiệm.
2. Tạm dừng hoặc chặn các luồng ghi nghiệp vụ theo cách ứng dụng hiểu được; hoàn tất hoặc hủy các giao dịch đang chạy theo chính sách.
3. Xác nhận standby nhận và replay tới vị trí WAL cuối cùng của primary. Nếu cần, dùng chế độ replication đồng bộ trong thời gian chuyển đổi hoặc chờ standby bắt kịp.
4. Dừng primary cũ một cách có kiểm soát để chắc chắn nó không tiếp tục nhận ghi.
5. Promote standby đã chọn.
6. Chuyển endpoint kết nối, VIP, DNS hoặc service discovery sang primary mới.
7. Làm mới connection pool và mở lại luồng ghi theo từng bước.
8. Kiểm thử giao dịch nghiệp vụ, kiểm tra log và giám sát tải.
9. Cấu hình primary cũ thành standby của primary mới sau khi đã xác minh dữ liệu và thực hiện quy trình rejoin phù hợp.

Trong một số kiến trúc, công cụ HA tự động thực hiện các bước dừng, promote và cập nhật endpoint. Quy trình thực tế phải theo công cụ điều phối đã triển khai, không trộn lẫn các lệnh thủ công với cơ chế tự động mà không hiểu trạng thái của cluster.

### 5.3. Failover khi primary mất đột ngột

Failover ngoài kế hoạch cần kiểm soát rủi ro split-brain. Trình tự ở mức khái niệm:

1. Phát hiện và xác nhận primary không còn phục vụ an toàn. Phân biệt database chết với lỗi mạng chỉ ảnh hưởng một phía.
2. Thực hiện fencing để ngăn primary cũ tiếp tục ghi. Có thể dùng cơ chế power fencing, cloud instance isolation, network isolation hoặc phương án tương đương phù hợp hạ tầng.
3. Đánh giá các standby còn khả dụng và chọn ứng viên có dữ liệu mới nhất theo chính sách RPO.
4. Promote đúng một standby.
5. Chuyển endpoint ứng dụng sang primary mới và xác nhận chỉ có một writer.
6. Chạy kiểm thử kỹ thuật và nghiệp vụ, ghi nhận dữ liệu có thể mất so với giao dịch đã được xác nhận.
7. Điều tra primary cũ và chỉ đưa trở lại topology sau khi đã đồng bộ theo quy trình an toàn.

Với PostgreSQL, có thể promote standby bằng SQL:

```sql
SELECT pg_promote(wait => true, wait_seconds => 60);
```

Hoặc dùng công cụ dòng lệnh trên máy standby:

```bash
pg_ctl promote -D /var/lib/postgresql/data
```

Các lệnh trên chỉ thực hiện promotion. Chúng không tự xác minh primary cũ đã bị fencing, không tự cập nhật DNS, không tự chọn standby tốt nhất và không tự điều phối ứng dụng. Những việc đó thuộc quy trình HA và hạ tầng xung quanh PostgreSQL.

### 5.4. Synchronous và asynchronous replication ảnh hưởng RPO

Với asynchronous replication, primary có thể xác nhận commit trước khi standby nhận và flush WAL tương ứng. Nếu primary mất đột ngột, một số giao dịch vừa được xác nhận có thể chưa có trên standby được promote. Độ trễ thực tế phụ thuộc mạng, tải và trạng thái standby.

Với synchronous replication, primary có thể chờ xác nhận từ standby theo cấu hình `synchronous_standby_names` và `synchronous_commit`. Mức xác nhận có thể liên quan tới WAL được ghi, flush hoặc replay tùy chế độ. Cấu hình đồng bộ có thể giảm nguy cơ mất giao dịch đã xác nhận khi failover đúng theo giả định về standby được xác nhận, nhưng đổi lại tăng độ trễ commit và có thể làm ghi bị chặn nếu không còn standby đồng bộ đủ điều kiện.

Ví dụ cấu hình khái niệm:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
```

Không sao chép nguyên cấu hình này vào production mà chưa đánh giá topology, tên `application_name`, số standby và chính sách khi standby mất kết nối. `synchronous_commit = remote_apply` chờ standby replay giao dịch trước khi xác nhận commit, trong khi các mức khác có điểm xác nhận khác nhau. Cần chọn theo yêu cầu RPO và độ trễ.

## 6. Rejoin primary cũ sau failover

Sau khi promote standby, primary cũ có thể chứa WAL hoặc giao dịch không tồn tại trên primary mới. Không được chỉ khởi động lại primary cũ và cho phép nó nhận ghi như trước. Cần tái gia nhập topology bằng một trong các cách:

- Dựng lại primary cũ từ base backup mới của primary hiện tại.
- Dùng `pg_rewind` nếu hai data directory đáp ứng điều kiện của công cụ và có đủ WAL cần thiết.
- Dùng quy trình rebuild do nền tảng HA hoặc dịch vụ quản lý PostgreSQL cung cấp.

`pg_rewind` giúp đồng bộ một data directory cũ về nhánh timeline của primary mới sau khi hai node đã phân nhánh. Điều kiện quan trọng gồm data checksums được bật khi initdb hoặc `wal_log_hints` được bật, và WAL cần thiết phải còn sẵn có. Target server phải được dừng trước khi rewind. Cần kiểm tra tài liệu đúng phiên bản và chuẩn bị backup an toàn trước khi thao tác.

Ví dụ minh họa, chạy trên máy quản trị với target là data directory của primary cũ đã dừng:

```bash
pg_rewind \
  --target-pgdata=/var/lib/postgresql/old_primary \
  --source-server='host=new-primary.example.net port=5432 dbname=postgres user=rewind_user'
```

Sau khi rewind, cấu hình node cũ để follow primary mới và khởi động ở vai trò standby. Kiểm tra `pg_stat_wal_receiver`, trạng thái recovery và lag trước khi đưa node vào pool dự phòng. Nếu điều kiện rewind không thỏa mãn hoặc thiếu WAL, phải rebuild từ backup phù hợp.

## 7. Kiểm chứng yêu cầu nghiệp vụ sau phục hồi

### 7.1. Kiểm tra nhiều lớp

Không dừng ở việc PostgreSQL đã mở cổng. Nên kiểm tra theo các lớp:

| Lớp | Ví dụ kiểm tra | Điều cần chứng minh |
|---|---|---|
| Hạ tầng | Volume mount, dung lượng, network, DNS, TLS | Máy chủ có tài nguyên và đường kết nối đúng. |
| PostgreSQL | Process, log, recovery state, kết nối, role | Database hoạt động và ở đúng vai trò. |
| Cấu trúc | Schema, bảng, index, constraint, sequence, extension | Đối tượng cần thiết tồn tại và tương thích. |
| Dữ liệu | Số lượng, khóa, tổng tiền, trạng thái, mốc giao dịch | Dữ liệu đáp ứng các bất biến nghiệp vụ. |
| Ứng dụng | Đăng nhập, đọc, tạo, cập nhật, commit | Ứng dụng thực hiện được quy trình thực tế. |
| Tích hợp | Queue, payment gateway, email, object storage | Các hệ thống phụ thuộc hoạt động đúng và không xử lý trùng. |
| Vận hành | Backup mới, monitoring, alert, lịch job | Hệ thống có thể tiếp tục được vận hành an toàn. |

### 7.2. Kiểm tra bất biến dữ liệu

Mỗi miền nghiệp vụ nên xác định các bất biến có thể kiểm tra bằng truy vấn. Ví dụ:

**Đơn hàng phải có khách hàng hợp lệ:**

```sql
SELECT COUNT(*) AS orders_without_customer
FROM sales.orders o
LEFT JOIN sales.customers c
    ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
```

**Tổng tiền chi tiết phải khớp tổng tiền đơn hàng trong sai số đã quy định:**

```sql
SELECT
    o.order_id,
    o.total_amount,
    SUM(oi.quantity * oi.unit_price) AS calculated_amount
FROM sales.orders o
JOIN sales.order_items oi
    ON oi.order_id = o.order_id
GROUP BY o.order_id, o.total_amount
HAVING ABS(
    o.total_amount - SUM(oi.quantity * oi.unit_price)
) > 0.01;
```

**Mã giao dịch thanh toán không bị ghi nhận nhiều lần:**

```sql
SELECT provider_transaction_id, COUNT(*) AS occurrences
FROM payments.transactions
GROUP BY provider_transaction_id
HAVING COUNT(*) > 1;
```

Các truy vấn trên chỉ là ví dụ. Điều kiện đúng phải theo mô hình dữ liệu, quy tắc làm tròn, hoàn tiền, hủy đơn và nghiệp vụ thực tế. Một truy vấn trả về 0 dòng cũng chưa chứng minh mọi dữ liệu đúng; cần chọn tập dữ liệu kiểm thử và đối chiếu với nguồn kiểm soát độc lập.

### 7.3. Kiểm tra giao dịch đã xác nhận

Để đo RPO, ứng dụng kiểm thử có thể ghi một mã giao dịch tăng dần hoặc UUID và ghi nhận kết quả commit ở một hệ thống quan sát độc lập. Sau khi failover hoặc restore, đối chiếu:

- Giao dịch cuối cùng ứng dụng đã nhận phản hồi thành công.
- Giao dịch cuối cùng còn tồn tại trên database phục hồi.
- Giao dịch được ứng dụng gửi nhưng không nhận được phản hồi.
- Giao dịch nào cần retry và có thể bị gửi trùng.

Giao dịch không nhận được phản hồi có trạng thái không chắc chắn: nó có thể đã commit trước khi kết nối đứt. Ứng dụng cần idempotency key hoặc cơ chế tra cứu trạng thái để retry an toàn. Chỉ dựa trên việc client timeout không thể kết luận giao dịch chưa commit.

Ví dụ bảng dấu kiểm thử:

```sql
CREATE TABLE ops.recovery_probe (
    probe_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    probe_token uuid NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    scenario text NOT NULL
);
```

Một tiến trình bên ngoài có thể gửi probe theo chu kỳ, ghi nhận token và thời điểm ứng dụng nhận xác nhận commit. Sau diễn tập, đối chiếu tập token ở kho quan sát với các token còn lại trong database. Bảng probe cần được giới hạn quyền và không thay thế log giao dịch nghiệp vụ thực.

### 7.4. Kiểm tra sequence và định danh

Các cơ chế replication không phải lúc nào cũng đồng bộ trạng thái sequence giống như dữ liệu bảng. Logical replication chẳng hạn không tự đồng bộ giá trị sequence. Khi khôi phục hoặc chuyển đổi vai trò, cần kiểm tra sequence so với dữ liệu hiện có để tránh cấp ID đã dùng.

Có thể xem trạng thái sequence bằng `pg_sequences`:

```sql
SELECT schemaname, sequencename, last_value
FROM pg_sequences
WHERE schemaname IN ('sales', 'payments')
ORDER BY schemaname, sequencename;
```

Với sequence cụ thể, có thể dùng `pg_get_serial_sequence()` để tìm sequence gắn với cột. Việc điều chỉnh sequence cần được thực hiện theo đúng kiểu sinh ID, cache, increment và quyền ghi; không chạy `setval()` đại trà nếu chưa xác định giá trị an toàn. Với UUID sinh từ ứng dụng, cần kiểm tra nguồn tạo ID và khả năng trùng giữa các node.

### 7.5. Kiểm tra ứng dụng end-to-end

Một bộ smoke test sau phục hồi có thể thực hiện:

1. Đăng nhập bằng tài khoản thử nghiệm.
2. Tra cứu một bản ghi đã tồn tại trước sự cố.
3. Tạo một giao dịch thử với idempotency key duy nhất.
4. Đọc lại giao dịch và kiểm tra trạng thái, tổng tiền, quan hệ dữ liệu.
5. Gửi một yêu cầu lặp với cùng idempotency key và xác nhận không tạo giao dịch thứ hai.
6. Kiểm tra một luồng tích hợp như phát sự kiện outbox hoặc xử lý queue.
7. Xác nhận log, metric và trace được ghi nhận sau khi dịch vụ hoạt động lại.

Smoke test nên chạy qua endpoint và credential mà ứng dụng production sẽ dùng, nhưng dữ liệu kiểm thử cần được cô lập hoặc đánh dấu rõ để không gây tác động tới khách hàng thật.

## 8. Thiết kế bộ kịch bản diễn tập

Một chương trình diễn tập tốt có nhiều kịch bản, từ đơn giản tới phức tạp. Không nên chỉ diễn tập một lần restore thành công từ bản backup mới nhất.

| Kịch bản | Mục tiêu | Kết quả cần ghi nhận |
|---|---|---|
| Restore full backup | Chứng minh base backup có thể dựng lại cluster | Thời gian restore, lỗi, trạng thái database và kết quả kiểm tra nghiệp vụ. |
| PITR trước thao tác xóa nhầm | Chứng minh có thể quay lại điểm trước sự cố logic | Target đã chọn, WAL được replay, bản ghi cần khôi phục và dữ liệu sau target. |
| Mất primary | Kiểm tra failover sang standby | Thời gian phát hiện, fencing, promote, endpoint và RPO thực tế. |
| Standby bị lag | Xác nhận chính sách chọn standby và RPO | LSN, giao dịch mất có thể có, lý do lag và quyết định promote. |
| Mất kết nối tới archive | Kiểm tra cảnh báo và khả năng tiếp tục backup | Thời gian phát hiện, dung lượng WAL tăng, cách khôi phục archive. |
| DNS hoặc connection pool giữ endpoint cũ | Kiểm tra khả năng chuyển ứng dụng | Thời gian hội tụ kết nối, lỗi client và cách làm mới pool. |
| Khôi phục sang máy chủ/vùng mới | Kiểm tra phụ thuộc hạ tầng và tài liệu | Thời gian cấp máy, volume, secret, network, TLS và cấu hình. |
| Khôi phục dữ liệu nghiệp vụ | Kiểm tra bất biến và quy trình của chủ sở hữu dữ liệu | Kết quả đối soát, giao dịch thiếu/trùng và xác nhận nghiệp vụ. |

### 8.1. Mẫu trình tự diễn tập PITR

Một buổi diễn tập có thể theo trình tự:

1. Ghi lại mốc bắt đầu và tạo một số giao dịch kiểm thử đã được xác nhận.
2. Tạo một sự kiện mô phỏng lỗi, chẳng hạn xóa một nhóm bản ghi trong môi trường diễn tập.
3. Ghi nhận thời điểm hoặc restore point trước sự kiện.
4. Cô lập database nguồn và chuẩn bị máy phục hồi.
5. Chọn base backup và WAL archive, cấu hình PITR.
6. Khởi động recovery tới target và dừng ở trạng thái pause.
7. Kiểm tra các giao dịch trước target còn tồn tại và thao tác sai chưa xuất hiện.
8. Xác nhận dữ liệu với chủ sở hữu nghiệp vụ.
9. Promote hoặc hoàn tất recovery theo kịch bản, chạy smoke test và đo RTO.
10. Ghi nhận kết quả, bài học và hành động khắc phục.

### 8.2. Mẫu trình tự diễn tập failover

1. Xác nhận topology primary/standby và tình trạng replication.
2. Ghi nhận probe giao dịch đã commit và LSN ở primary.
3. Mô phỏng primary mất khả năng phục vụ theo phương án đã phê duyệt trong môi trường diễn tập.
4. Thực hiện fencing hoặc chứng minh cơ chế fencing đã ngăn writer cũ.
5. Chọn standby theo chính sách và promote đúng một node.
6. Chuyển endpoint và làm mới kết nối ứng dụng.
7. Chạy smoke test đọc/ghi và kiểm chứng bất biến nghiệp vụ.
8. Đối chiếu probe để đo RPO, đo thời gian khôi phục để tính RTO.
9. Rejoin primary cũ bằng quy trình đã định.
10. Xác nhận topology ổn định, backup mới hoạt động và cảnh báo được khôi phục.

## 9. Đo lường và tiêu chí hoàn thành

### 9.1. Ghi mốc thời gian

Nên ghi các mốc sau cho mỗi kịch bản:

| Mốc | Ý nghĩa |
|---|---|
| `T0` | Sự cố xảy ra hoặc thời điểm bắt đầu diễn tập đã thống nhất. |
| `T_detect` | Hệ thống hoặc người vận hành phát hiện sự cố. |
| `T_decide` | Quyết định restore/failover được đưa ra. |
| `T_fence` | Primary cũ được xác nhận không còn khả năng ghi. |
| `T_promote` | Standby được promote hoặc restore hoàn tất recovery. |
| `T_endpoint` | Endpoint và kết nối ứng dụng đã chuyển sang máy mới. |
| `T_business` | Smoke test nghiệp vụ đầu tiên thành công. |
| `T_stable` | Các chỉ số hiệu năng và lỗi đạt ngưỡng ổn định đã định. |

RTO có thể được đo tới `T_business` hoặc `T_stable` tùy cam kết dịch vụ. Cần báo cáo cả hai nếu việc đưa chức năng tối thiểu hoạt động và khôi phục đầy đủ có thời điểm khác nhau.

### 9.2. Tiêu chí pass/fail

Một diễn tập chỉ được đánh dấu đạt khi có đủ bằng chứng cho các tiêu chí đã đặt trước. Ví dụ:

- Restore hoàn tất mà không có lỗi WAL hoặc thiếu file cần thiết.
- Database ở đúng trạng thái primary/standby dự kiến.
- RPO thực tế không vượt giới hạn đã cam kết.
- RTO thực tế không vượt giới hạn đã cam kết.
- Các bất biến dữ liệu trọng yếu được thỏa mãn.
- Giao dịch đã xác nhận không bị mất vượt ngưỡng; giao dịch retry không bị nhân đôi.
- Ứng dụng và các tích hợp quan trọng hoạt động qua endpoint mới.
- Không tồn tại hai writer cùng hoạt động.
- Backup, WAL archive, monitoring và cảnh báo hoạt động trở lại sau diễn tập.
- Có log, mốc thời gian, truy vấn đối soát và xác nhận của chủ sở hữu nghiệp vụ.

Nếu một tiêu chí không đạt, ghi rõ tác động và hành động khắc phục, ví dụ tăng tần suất base backup, sửa archive, cải thiện fencing, giảm thời gian DNS TTL, thay đổi connection pool hoặc tối ưu quy trình kiểm tra dữ liệu. Không nên thay đổi RPO/RTO sau diễn tập chỉ để làm kết quả có vẻ đạt; mọi thay đổi mục tiêu cần được chủ sở hữu dịch vụ phê duyệt.

### 9.3. Báo cáo sau diễn tập

Một báo cáo nên bao gồm:

```text
Tên kịch bản:
Môi trường / phiên bản PostgreSQL:
Ngày và người tham gia:
Mục tiêu RPO / RTO:
Base backup / timeline / recovery target:
Thời điểm bắt đầu sự cố:
Thời điểm dịch vụ phục hồi:
RTO đo được:
Giao dịch cuối cùng được xác nhận trước sự cố:
Giao dịch cuối cùng có sau phục hồi:
RPO đo được:
Kết quả kiểm tra kỹ thuật:
Kết quả kiểm tra nghiệp vụ:
Sự cố hoặc sai lệch phát hiện:
Hành động khắc phục / người phụ trách / hạn hoàn thành:
Quyết định của chủ sở hữu dịch vụ:
```

Giữ lại báo cáo và bằng chứng đủ để lần diễn tập sau so sánh được. Không lưu mật khẩu, private key hoặc dữ liệu cá nhân không cần thiết trong báo cáo.

## 10. An toàn khi diễn tập và các lỗi thường gặp

Diễn tập restore/failover có thể ảnh hưởng dịch vụ nếu chạy nhầm lệnh trên production hoặc để máy phục hồi tham gia mạng thật. Cần có phạm vi, môi trường, người điều phối và điểm dừng rõ ràng. Với diễn tập trên production, phải dùng quy trình thay đổi đã phê duyệt và phương án quay lui.

| Lỗi thường gặp | Hậu quả | Cách phòng tránh |
|---|---|---|
| Chỉ kiểm tra backup bằng cách xem file tồn tại | Backup có thể hỏng hoặc thiếu WAL cần thiết | Thực hiện restore định kỳ từ kho backup thực tế. |
| Lưu backup cùng ổ đĩa với primary | Một sự cố lưu trữ có thể làm mất cả dữ liệu và backup | Lưu bản sao độc lập, tách miền lỗi và kiểm tra quyền xóa. |
| Không giám sát archive failure | WAL không được lưu, `pg_wal` có thể đầy | Theo dõi `pg_stat_archiver`, dung lượng và thời điểm archive gần nhất. |
| Promote standby khi primary cũ vẫn ghi | Split-brain và phân nhánh dữ liệu | Fencing trước promote, chỉ cho phép một writer. |
| Chọn standby chỉ dựa trên việc node đang online | Có thể chọn bản sao bị lag nhiều hơn | So sánh trạng thái nhận/flush/replay WAL và chính sách RPO. |
| Coi replication là backup | Xóa nhầm hoặc hỏng logic lan sang standby | Duy trì backup độc lập và diễn tập PITR. |
| Không kiểm tra ứng dụng sau khi database mở cổng | Người dùng vẫn không hoàn thành được nghiệp vụ | Chạy smoke test end-to-end và kiểm chứng bất biến. |
| Không kiểm tra sequence sau restore hoặc logical replication | ID mới có thể trùng hoặc sequence không đúng | Kiểm tra và điều chỉnh sequence theo từng bảng trước khi mở ghi. |
| DNS đổi nhưng connection pool giữ kết nối cũ | Một phần ứng dụng tiếp tục gọi primary cũ | Kiểm tra TTL, pool lifetime, retry và cơ chế refresh endpoint. |
| Retry giao dịch sau timeout mà không có idempotency | Có thể tạo đơn hoặc thanh toán trùng | Dùng idempotency key và tra cứu trạng thái giao dịch không chắc chắn. |
| Rejoin primary cũ bằng cách khởi động trực tiếp | Node có thể tiếp tục lịch sử WAL cũ | Dùng `pg_rewind` khi đủ điều kiện hoặc rebuild từ backup. |
| Chỉ đo thời gian chạy lệnh promote | Bỏ qua thời gian phát hiện, chuyển endpoint và xác nhận nghiệp vụ | Ghi toàn bộ timeline từ sự cố tới khi dịch vụ ổn định. |
| Không diễn tập khi archive hoặc standby bị lỗi | Runbook có thể chỉ hoạt động trong điều kiện lý tưởng | Bổ sung kịch bản lỗi mạng, lag, dung lượng và thiếu WAL. |

## 11. Lịch diễn tập và cải tiến liên tục

Tần suất diễn tập phụ thuộc mức độ quan trọng của dịch vụ, tốc độ thay đổi kiến trúc và yêu cầu kiểm toán. Một lịch tham khảo:

| Hoạt động | Tần suất tham khảo | Bằng chứng |
|---|---|---|
| Kiểm tra backup job và WAL archive | Hàng ngày hoặc tự động liên tục | Metric, alert, log và thời điểm archive gần nhất. |
| Restore thử một backup vào môi trường cách ly | Hàng tháng hoặc theo chính sách | Báo cáo restore, thời gian và kết quả truy vấn. |
| Diễn tập PITR | Hàng quý hoặc sau thay đổi lớn | Recovery target, kiểm tra dữ liệu trước/sau target. |
| Diễn tập failover/switchover | Hàng quý hoặc theo cam kết dịch vụ | Timeline, RPO/RTO và kết quả smoke test. |
| Diễn tập phục hồi vùng hoặc hạ tầng | Theo mức rủi ro, thường ít nhất hằng năm | Bằng chứng cấp hạ tầng, restore, DNS, secret và nghiệp vụ. |
| Kiểm tra runbook sau thay đổi PostgreSQL/extension/HA | Sau mỗi thay đổi quan trọng | Phiên bản tài liệu, người phê duyệt và kết quả thử. |

Đây là lịch tham khảo; tổ chức cần điều chỉnh theo RPO/RTO, quy định, quy mô dữ liệu và khả năng thực hiện. Mỗi thay đổi lớn như nâng major version, đổi storage, đổi công cụ HA, chuyển vùng hoặc thay đổi quy trình backup đều có thể làm runbook cũ mất hiệu lực và cần diễn tập lại.

## 12. Checklist vận hành cho một lần diễn tập

### Trước diễn tập

- [ ] Mục tiêu RPO/RTO và tiêu chí pass/fail được chủ sở hữu dịch vụ xác nhận.
- [ ] Kịch bản, phạm vi, thời gian và người chịu trách nhiệm được ghi rõ.
- [ ] Backup, WAL archive, secret và cấu hình cần thiết sẵn sàng.
- [ ] Máy phục hồi hoặc standby đủ tài nguyên và phiên bản tương thích.
- [ ] Có cơ chế cách ly mạng và ngăn môi trường thử kết nối nhầm production.
- [ ] Có bộ probe hoặc nguồn dữ liệu độc lập để đối chiếu giao dịch.

### Trong diễn tập

- [ ] Ghi mốc thời gian và trạng thái PostgreSQL ở từng bước.
- [ ] Xác nhận đúng backup, timeline và recovery target.
- [ ] Với failover, fencing primary cũ trước khi promote.
- [ ] Chỉ có một primary nhận ghi.
- [ ] Theo dõi log, WAL replay, kết nối và lỗi ứng dụng.
- [ ] Chạy kiểm tra kỹ thuật và các giao dịch nghiệp vụ đã định.

### Sau diễn tập

- [ ] Tính RPO/RTO thực tế và so sánh với mục tiêu.
- [ ] Đối chiếu giao dịch, bất biến dữ liệu và trạng thái tích hợp.
- [ ] Rejoin hoặc dọn môi trường theo runbook.
- [ ] Xác nhận backup/WAL archive và cảnh báo hoạt động bình thường.
- [ ] Ghi lỗi, hành động khắc phục, người phụ trách và thời hạn.
- [ ] Chủ sở hữu nghiệp vụ xác nhận kết quả phục hồi.

## 13. Kết luận

Diễn tập phục hồi PostgreSQL cần chứng minh ba điều: có thể dựng lại dữ liệu từ backup/WAL, có thể chuyển dịch vụ sang node phù hợp mà không tạo split-brain, và ứng dụng vẫn đáp ứng các yêu cầu nghiệp vụ sau khi phục hồi. RPO/RTO phải được đo bằng giao dịch và mốc thời gian thực tế; việc database khởi động thành công chỉ là một phần của kết quả.

Một quy trình đáng tin cậy kết hợp backup độc lập, WAL archiving, restore/PITR định kỳ, replication phù hợp, fencing khi failover, kiểm tra dữ liệu và smoke test end-to-end. Báo cáo sau mỗi lần diễn tập giúp phát hiện khoảng cách giữa mục tiêu và năng lực hiện tại, từ đó cải tiến runbook, kiến trúc và quy trình vận hành.

## Tài liệu tham khảo

- [PostgreSQL — Backup and Restore](https://www.postgresql.org/docs/current/backup.html)
- [PostgreSQL — Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html)
- [PostgreSQL — Warm Standby and Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html)
- [PostgreSQL — pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html)
- [PostgreSQL — pg_verifybackup](https://www.postgresql.org/docs/current/app-pgverifybackup.html)
- [PostgreSQL — pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html)
- [PostgreSQL — Recovery Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html#RUNTIME-CONFIG-WAL-RECOVERY-TARGET)
- [PostgreSQL — System Administration Functions](https://www.postgresql.org/docs/current/functions-admin.html)
