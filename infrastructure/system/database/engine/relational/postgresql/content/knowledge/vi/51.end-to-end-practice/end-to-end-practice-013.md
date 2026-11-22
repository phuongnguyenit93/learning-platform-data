# Sao lưu, phục hồi tới thời điểm xác định và đối soát dữ liệu

Sao lưu chỉ có giá trị khi có thể phục hồi thành công và xác minh được dữ liệu sau phục hồi. Với PostgreSQL, một quy trình bảo vệ dữ liệu thường kết hợp bản sao lưu nền (base backup), lưu trữ liên tục các WAL (Write-Ahead Log), kiểm tra tính toàn vẹn và diễn tập khôi phục. Khi xảy ra xóa nhầm, cập nhật sai hoặc lỗi triển khai, Point-in-Time Recovery (PITR) cho phép dựng lại một cụm PostgreSQL tới một thời điểm hoặc mốc đã xác định trong lịch sử.

Phục hồi tới thời điểm xác định thường khôi phục toàn bộ cụm database về một trạng thái trong quá khứ. Vì vậy, sau khi khôi phục, cần đối soát các số liệu nghiệp vụ, xác định những giao dịch nào đã bị loại bỏ và kiểm tra các tác động đã xảy ra bên ngoài PostgreSQL. Một bản phục hồi chạy được về mặt kỹ thuật chưa chắc đã đúng với trạng thái nghiệp vụ mong muốn.

Bài học này trình bày mô hình backup, cách lưu WAL, các phương pháp sao lưu logic và vật lý, quy trình PITR, kiểm chứng dữ liệu và tổ chức diễn tập phục hồi.

## 1. Mục tiêu phục hồi và mô hình bảo vệ dữ liệu

### RPO và RTO

Trước khi chọn công cụ hoặc lịch sao lưu, cần thống nhất hai mục tiêu:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa mà tổ chức chấp nhận mất, thường được biểu diễn bằng thời gian. RPO 5 phút có nghĩa là khi có sự cố, mục tiêu là chỉ mất tối đa khoảng 5 phút dữ liệu gần nhất.
- **RTO (Recovery Time Objective):** khoảng thời gian tối đa chấp nhận để đưa dịch vụ trở lại hoạt động. RTO 30 phút có nghĩa là quy trình phục hồi, kiểm tra và chuyển ứng dụng phải hoàn tất trong khoảng thời gian đó.

RPO và RTO là yêu cầu nghiệp vụ, không phải thuộc tính tự động được bảo đảm chỉ vì đã bật archive_mode hoặc tạo một bản dump.

| Nhu cầu | Cơ chế thường dùng | Giới hạn chính |
| --- | --- | --- |
| Khôi phục một database hoặc một nhóm đối tượng | Logical backup bằng pg_dump/pg_restore | Không tự cung cấp lịch sử WAL liên tục để PITR |
| Dựng lại toàn bộ cụm PostgreSQL | Physical base backup | Cần WAL tương ứng và môi trường tương thích |
| Khôi phục tới thời điểm trước thao tác lỗi | Base backup kết hợp WAL archive | Phải có đủ chuỗi WAL từ backup đến recovery target |
| Giảm thời gian gián đoạn khi máy chủ hỏng | Standby/replication kết hợp backup | Replica có thể sao chép cả thao tác xóa nhầm hoặc dữ liệu sai |
| Kiểm tra khả năng khôi phục | Restore drill định kỳ | Phải thử trên môi trường độc lập và đo thời gian thực tế |

### Ba thành phần của PITR

PITR dựa trên ba thành phần:

1. **Base backup:** bản sao nhất quán của dữ liệu PostgreSQL tại một thời điểm bắt đầu sao lưu.
2. **WAL archive:** chuỗi WAL liên tục cần thiết để phát lại mọi thay đổi sau khi base backup được tạo.
3. **Recovery target:** mốc dừng phát lại WAL, chẳng hạn thời điểm, tên restore point, LSN hoặc transaction ID.

Có thể hình dung quy trình:

~~~text
Base backup
    |
    v
WAL segment A -> WAL segment B -> WAL segment C -> WAL segment D
                                                  |
                                                  v
                                    Recovery target đã chọn
                                                  |
                                                  v
                                  PostgreSQL dừng phát lại WAL
                                                  |
                                                  v
                                    Kiểm tra và đối soát
                                                  |
                                                  v
                                         Promote/cutover
~~~

Base backup phải được tạo trước recovery target. WAL archive phải chứa đầy đủ các segment cần thiết để đưa bản backup tới target. Chỉ có base backup mà thiếu WAL thì không thể khôi phục tới một thời điểm bất kỳ sau backup.

### Backup không thay thế replication

Streaming replication giúp duy trì một máy chủ dự phòng và có thể giảm thời gian chuyển đổi khi máy chủ chính gặp sự cố. Tuy nhiên, replication thường truyền cả thay đổi hợp lệ lẫn thay đổi sai. Nếu ứng dụng chạy lệnh xóa nhầm và transaction được commit, standby cũng có thể nhận lệnh xóa đó.

Backup và WAL archive cung cấp khả năng quay về trạng thái trước sự cố. Replica hỗ trợ tính sẵn sàng. Một hệ thống cần cả hai khi yêu cầu nghiệp vụ đòi hỏi thời gian gián đoạn thấp và khả năng phục hồi dữ liệu.

## 2. Chọn phương pháp sao lưu

### Logical backup với pg_dump

Logical backup xuất cấu trúc và dữ liệu thành các lệnh SQL hoặc định dạng archive của PostgreSQL. Cách này phù hợp khi cần:

- Sao lưu một database.
- Chuyển dữ liệu giữa các phiên bản PostgreSQL có hỗ trợ tương thích.
- Phục hồi chọn lọc một schema, table hoặc nhóm đối tượng.
- Kiểm tra và di chuyển dữ liệu trong môi trường khác.

Ví dụ tạo bản dump ở định dạng custom:

~~~bash
pg_dump -Fc -f /backups/appdb.dump appdb
~~~

Định dạng custom cho phép pg_restore liệt kê nội dung, chọn đối tượng và điều khiển thứ tự phục hồi.

Liệt kê nội dung archive:

~~~bash
pg_restore --list /backups/appdb.dump
~~~

Tạo database đích rồi phục hồi:

~~~bash
createdb appdb_restore
pg_restore --exit-on-error --verbose -d appdb_restore /backups/appdb.dump
~~~

Nếu cần giữ role và quyền sở hữu, các role tương ứng phải tồn tại ở cụm đích. pg_dump không bao gồm các đối tượng toàn cụm như role và tablespace. Có thể sao lưu global objects riêng:

~~~bash
pg_dumpall --globals-only > /backups/globals.sql
~~~

Phục hồi globals trước khi phục hồi database nếu dump cần các role hoặc tablespace đó:

~~~bash
psql -X -d postgres -f /backups/globals.sql
~~~

Tệp globals có thể chứa thông tin xác thực role tùy cấu hình và quyền truy cập. Bảo vệ nó như dữ liệu nhạy cảm, giới hạn quyền đọc và mã hóa khi lưu trữ hoặc truyền tải.

Logical backup tạo một snapshot nhất quán cho quá trình dump, nhưng không tạo chuỗi WAL để khôi phục liên tục tới một thời điểm tùy ý. Muốn PITR toàn cụm, cần base backup vật lý và WAL archive.

### Physical backup với pg_basebackup

Physical backup sao chép các tệp dữ liệu của một cụm PostgreSQL theo cơ chế backup nhất quán do PostgreSQL cung cấp. Đây là nền tảng phổ biến cho PITR và dựng lại toàn bộ instance.

Ví dụ tạo base backup ở định dạng thư mục thông thường và stream WAL trong khi sao lưu:

~~~bash
pg_basebackup \
  -h db-primary.example.internal \
  -p 5432 \
  -U backup_user \
  -D /backups/base-2026-11-14 \
  -F plain \
  -X stream \
  -P
~~~

Ý nghĩa các tùy chọn:

- -h, -p: máy chủ và cổng PostgreSQL nguồn.
- -U: role được cấp quyền replication phù hợp.
- -D: thư mục đích; cần được chuẩn bị theo yêu cầu của pg_basebackup.
- -F plain: lưu dưới dạng cây thư mục dữ liệu.
- -X stream: lấy WAL cần thiết trong lúc base backup đang chạy.
- -P: hiển thị tiến độ.

Tên máy chủ, đường dẫn và role trong ví dụ chỉ mang tính minh họa. Khi chạy thực tế, dùng cơ chế xác thực an toàn như .pgpass có quyền truy cập hạn chế hoặc secret manager; tránh đặt mật khẩu trực tiếp trên command line hoặc lưu trong lịch sử shell.

pg_basebackup phải kết nối tới server có cấu hình và quyền phù hợp. Quản trị viên cần kiểm tra max_wal_senders, quyền REPLICATION của role và cấu hình pg_hba.conf. Không dùng tùy chọn -R nếu mục tiêu là tạo một bản backup độc lập để phục hồi PITR; -R tạo cấu hình cho standby.

Tùy chọn -X stream đưa WAL cần cho tính nhất quán của chính quá trình base backup vào thư mục backup. Nó không thay thế việc archive WAL liên tục sau khi backup hoàn tất. Muốn phục hồi tới thời điểm muộn hơn, vẫn phải có chuỗi WAL tiếp theo.

### Sao lưu bằng snapshot filesystem hoặc storage

Snapshot của volume có thể hữu ích khi hạ tầng hỗ trợ snapshot nhất quán. Tuy nhiên, không được tùy tiện sao chép thư mục dữ liệu đang hoạt động bằng một lệnh copy thông thường rồi xem đó là physical backup hợp lệ.

Một snapshot vật lý cần tuân thủ phương pháp backup nhất quán được PostgreSQL và nền tảng lưu trữ hỗ trợ. Với snapshot nhiều volume hoặc có tablespace nằm trên nhiều filesystem, phải bảo đảm các volume được chụp tại một trạng thái đồng bộ. Cần có WAL tương ứng để hoàn thiện recovery.

Nếu dùng công cụ backup chuyên dụng như pgBackRest hoặc WAL-G, hãy tuân theo hướng dẫn về stanza/repository, retention, mã hóa, archive-push, archive-get và kiểm tra backup của chính công cụ đó. Không trộn lẫn lệnh restore của các công cụ hoặc giả định file archive có định dạng giống nhau.

### Bảng so sánh

| Tiêu chí | Logical backup | Physical base backup + WAL |
| --- | --- | --- |
| Phạm vi | Database và đối tượng logic | Toàn bộ cụm PostgreSQL |
| Khôi phục một bảng | Có thể chọn đối tượng khi restore | Phải dựng cụm rồi trích xuất dữ liệu cần thiết |
| PITR liên tục | Không tự có | Có, khi WAL đầy đủ |
| Chuyển major version | Có thể, nếu phiên bản nguồn/đích được hỗ trợ | Thông thường cần cùng major version |
| Thời gian phục hồi | Có thể lâu khi dữ liệu lớn | Thường nhanh hơn cho toàn cụm, phụ thuộc kích thước backup và WAL |
| Phụ thuộc | pg_dump/pg_restore, role và extension | Base backup, WAL, cấu hình và môi trường tương thích |

Trong thực tế, có thể duy trì cả logical backup định kỳ cho nhu cầu phục hồi đối tượng và physical backup + WAL archive cho khả năng phục hồi toàn cụm.

## 3. Chuẩn bị WAL archiving

### WAL là gì?

PostgreSQL ghi các thay đổi cần thiết vào WAL trước khi các trang dữ liệu tương ứng được ghi xuống data files. Khi khởi động sau sự cố, PostgreSQL có thể phát lại WAL để đưa data files về trạng thái nhất quán.

WAL được chia thành các segment. Kích thước segment thường là 16 MB trong bản PostgreSQL mặc định, nhưng có thể khác tùy cách biên dịch. Khi bật archive mode, PostgreSQL gọi archive command hoặc tích hợp với công cụ archive để chuyển các segment đã hoàn tất sang kho lưu trữ.

WAL archive không phải bản sao của từng câu lệnh SQL. Nó là dữ liệu nhật ký nhị phân phục vụ recovery. Không chỉnh sửa nội dung WAL, không đổi tên tùy ý và không xóa segment chỉ vì thấy segment đó đã cũ.

### Cấu hình cơ bản

Các tham số thường cần kiểm tra:

~~~sql
SHOW wal_level;
SHOW archive_mode;
SHOW archive_command;
SHOW archive_timeout;
~~~

Để hỗ trợ physical backup và WAL archiving thông thường, wal_level cần ở mức replica hoặc logical; archive_mode phải được bật. Giá trị archive_command phải gọi một chương trình có khả năng chuyển WAL segment sang kho lưu trữ bền vững.

Ví dụ minh họa với một kho lưu trữ cục bộ không nén:

~~~conf
wal_level = replica
archive_mode = on
archive_command = 'cp %p /srv/pg_wal_archive/%f'
~~~

Trong đó %p là đường dẫn WAL segment nguồn và %f là tên file segment. Ví dụ cp chỉ phù hợp để minh họa cơ chế trên một môi trường thử nghiệm có filesystem được quản lý đúng. Production nên dùng archive manager có kiểm tra lỗi, tính bền vững, xử lý retry, quyền truy cập, mã hóa và giám sát.

Thư mục archive phải tồn tại, PostgreSQL phải có quyền ghi phù hợp và kho lưu trữ cần nằm trên vùng lưu trữ có khả năng chịu lỗi độc lập với data volume. Nếu database và WAL archive cùng nằm trên một volume duy nhất, hỏng volume có thể làm mất cả dữ liệu lẫn bản ghi cần để phục hồi.

archive_mode là tham số cần khởi động lại server để thay đổi có hiệu lực. Sau khi cấu hình, kiểm tra lại giá trị đang chạy và log PostgreSQL để xác nhận các segment được archive thành công.

### Kiểm tra hoạt động archiver

View pg_stat_archiver cung cấp số liệu về hoạt động archive:

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

Các trường cần theo dõi:

- archived_count: số WAL segment archive thành công kể từ lần reset thống kê.
- last_archived_wal và last_archived_time: segment và thời điểm archive thành công gần nhất.
- failed_count: số lần archive thất bại.
- last_failed_wal và last_failed_time: segment và thời điểm thất bại gần nhất.

Nếu failed_count tăng, hãy kiểm tra log server, quyền ghi, dung lượng kho lưu trữ, kết nối mạng và lỗi của archive manager. Một giá trị last_archived_time cũ bất thường có thể báo hiệu archive đang bị gián đoạn, nhưng cần đối chiếu với lượng WAL thực tế được tạo ra.

Các số liệu trong pg_stat_archiver là bộ đếm tích lũy từ stats_reset. Không chỉ xem một lần rồi kết luận. Nên thu thập theo chu kỳ và cảnh báo khi số lần thất bại tăng hoặc độ trễ archive vượt mục tiêu RPO.

### WAL archive phải liên tục và đầy đủ

Để phục hồi từ base backup tới target, cần mọi WAL segment cần thiết trong khoảng đó. Một segment bị mất, bị hỏng hoặc không thể đọc có thể khiến recovery dừng trước target.

Những nguyên nhân phổ biến làm đứt chuỗi WAL:

- Archive command thất bại kéo dài nhưng không được cảnh báo.
- Kho lưu trữ hết dung lượng.
- Chính sách retention xóa segment còn cần cho base backup cũ.
- Copy file bị gián đoạn hoặc kho lưu trữ chỉ nhận một phần nội dung.
- Thay đổi timeline sau failover nhưng không lưu timeline history file.
- Quy trình vận hành đổi tên hoặc di chuyển segment ngoài công cụ quản lý.

Không xóa WAL archive theo tuổi file một cách độc lập. Retention phải dựa trên backup còn được giữ, các recovery window cần hỗ trợ, trạng thái công cụ backup và những chuỗi WAL còn cần cho restore. Một base backup cũ có thể cần các segment WAL rất cũ để phục hồi tới target.

### Kiểm tra WAL archive sau base backup

Khi base backup hoàn tất, cần ghi lại:

- Thời điểm bắt đầu và kết thúc backup.
- Tên backup, vị trí lưu trữ và checksum/manifest.
- Major version của PostgreSQL.
- Các tablespace và vị trí dữ liệu liên quan.
- WAL segment và timeline cần để bắt đầu recovery.
- Trạng thái archive trong suốt quá trình backup và sau đó.

Hãy lưu metadata này cùng backup. Nếu sử dụng công cụ quản lý backup, dùng lệnh info/check của công cụ để xem backup nào còn hợp lệ và WAL nào đang được giữ.

## 4. Kiểm chứng bản backup trước khi cần dùng

### Kiểm tra backup manifest

Các phiên bản PostgreSQL hỗ trợ backup manifest tạo manifest mô tả các file và checksum trong base backup. Với thư mục backup do pg_basebackup tạo, có thể dùng pg_verifybackup:

~~~bash
pg_verifybackup /backups/base-2026-11-14
~~~

Lệnh này kiểm tra nội dung backup dựa trên manifest và các checksum liên quan. Nên dùng công cụ tương thích với major version tạo backup và xử lý mọi cảnh báo hoặc lỗi trước khi đưa backup vào danh sách có thể phục hồi.

Kiểm tra manifest không thay thế restore drill. Một bản backup có thể vượt qua kiểm tra file nhưng vẫn không phục hồi được nếu thiếu WAL, sai cấu hình, thiếu extension hoặc có lỗi ở bước triển khai.

### Kiểm tra khả năng đọc logical backup

Với dump định dạng custom, dùng pg_restore --list để xác nhận archive có thể được đọc và hiển thị danh mục. Sau đó nên restore thử vào database riêng:

~~~bash
createdb appdb_restore_test
pg_restore --exit-on-error -d appdb_restore_test /backups/appdb.dump
~~~

Kiểm tra các bảng, quyền, extension, view và dữ liệu sau restore. Nếu dump phụ thuộc role hoặc tablespace, chuẩn bị các đối tượng đó hoặc điều chỉnh có chủ đích trong môi trường thử nghiệm.

### Bảo vệ bản backup

Một bản backup tốt cần:

- Được lưu ở vị trí độc lập với máy chủ PostgreSQL nguồn.
- Có bản sao ở vùng hoặc tài khoản lưu trữ khác để giảm rủi ro mất đồng thời.
- Được mã hóa khi truyền và khi lưu nếu dữ liệu nhạy cảm.
- Có kiểm soát quyền đọc, ghi, xóa và audit truy cập.
- Có retention phù hợp với yêu cầu pháp lý và nghiệp vụ.
- Có checksum/manifest hoặc cơ chế kiểm tra tính toàn vẹn.
- Được kiểm tra khả năng phục hồi định kỳ.

Áp dụng nguyên tắc nhiều bản sao, nhiều loại phương tiện và ít nhất một bản ở vị trí độc lập. Nếu tài khoản vận hành database có thể xóa cả backup và WAL archive, sự cố bảo mật hoặc thao tác nhầm có thể phá hủy toàn bộ điểm phục hồi. Hãy tách quyền backup, quyền xóa và quyền quản trị database khi có thể.

## 5. Phục hồi tới thời điểm xác định (PITR)

### Khi nào cần PITR?

PITR phù hợp khi:

- Một transaction cập nhật hoặc xóa nhầm đã commit.
- Một bản phát hành ứng dụng ghi dữ liệu sai trong một khoảng thời gian.
- Một batch import tạo dữ liệu lỗi.
- Người vận hành cần quay về trước một thao tác thay đổi cấu trúc hoặc dữ liệu.
- Cần dựng môi trường điều tra từ trạng thái database trước sự cố.

PITR vật lý phục hồi toàn bộ cụm PostgreSQL. Nó không tự phục hồi riêng một table vào đúng database đang chạy. Nếu chỉ cần một bảng, hãy phục hồi cụm sang môi trường riêng, trích xuất bảng hoặc dữ liệu cần thiết bằng pg_dump/SQL rồi nhập có kiểm soát vào hệ thống hiện tại.

### Các kiểu recovery target

PostgreSQL hỗ trợ một số dạng recovery target:

- recovery_target_time: thời điểm cụ thể.
- recovery_target_name: tên restore point đã được ghi trước đó.
- recovery_target_lsn: vị trí WAL (Log Sequence Number).
- recovery_target_xid: transaction ID.

Mỗi lần recovery chỉ chọn một loại target phù hợp. Mốc phải tồn tại trong chuỗi WAL có thể đọc được. Nếu chọn thời điểm nằm trước thời điểm base backup hoặc sau đoạn WAL cuối cùng có sẵn, mục tiêu không thể đạt được.

### Ghi restore point trước một thay đổi lớn

Khi chuẩn bị triển khai hoặc chạy một batch quan trọng, có thể tạo restore point được đặt tên:

~~~sql
SELECT pg_create_restore_point('before_monthly_import');
~~~

PostgreSQL trả về LSN của restore point. Ghi lại tên, LSN, thời gian, phiên bản ứng dụng và người thực hiện vào nhật ký triển khai. WAL chứa restore point phải được archive thành công để có thể dùng tên đó trong recovery sau này.

Restore point tạo mốc trong WAL; nó không tạo một bản backup độc lập. Vẫn cần base backup phù hợp và toàn bộ WAL liên quan.

### Chuẩn bị môi trường phục hồi

Quy trình an toàn thường phục hồi vào một máy chủ hoặc thư mục dữ liệu riêng:

1. Chọn base backup có thời điểm phù hợp và xác minh manifest/checksum.
2. Xác nhận WAL archive có đầy đủ segment từ backup đến target.
3. Chuẩn bị máy chủ đích với major version tương thích, extension, thư viện và cấu hình cần thiết.
4. Đảm bảo data directory đích rỗng hoặc được tạo mới theo quy trình quản trị.
5. Khôi phục nội dung base backup vào data directory đích, giữ đúng owner và permission.
6. Cấu hình restore_command và recovery target.
7. Tạo recovery.signal trong data directory đối với PostgreSQL 12 trở lên.
8. Khởi động instance và theo dõi log cho tới khi đạt target.

Không ghi đè data directory của primary đang hoạt động để thử PITR. Phục hồi riêng giúp giữ nguyên nguồn hiện tại, cho phép kiểm tra dữ liệu trước khi quyết định cutover và giảm nguy cơ mất thêm dữ liệu.

### Cấu hình phục hồi tới một thời điểm

Ví dụ muốn phục hồi tới 10 giờ 15 phút ngày 14 tháng 11 năm 2026 theo múi giờ Việt Nam:

~~~conf
restore_command = 'cp /srv/pg_wal_archive/%f "%p"'
recovery_target_time = '2026-11-14 10:15:00+07'
recovery_target_inclusive = true
recovery_target_timeline = 'latest'
recovery_target_action = 'pause'
~~~

Đây là ví dụ dùng kho WAL không nén ở filesystem cục bộ. Trong production, thay restore_command bằng lệnh archive-get của công cụ đang quản lý WAL. Lệnh phải trả về thành công khi lấy được file và trả về khác 0 khi file không có hoặc không thể khôi phục. Không dùng lệnh cp mẫu nếu archive được nén, mã hóa hoặc quản lý bởi một công cụ khác.

Ý nghĩa:

- recovery_target_time: thời điểm dừng phát lại WAL.
- recovery_target_inclusive: quyết định có bao gồm transaction đúng tại target hay không; true là hành vi mặc định.
- recovery_target_timeline: latest cho phép chọn timeline mới nhất có thể theo chuỗi recovery.
- recovery_target_action: pause yêu cầu server tạm dừng khi đạt target để người vận hành kiểm tra trước.

Thời gian phải có múi giờ rõ ràng. Nếu bỏ múi giờ, cách diễn giải phụ thuộc cấu hình timezone của server. WAL lưu thời điểm commit của transaction; recovery target theo thời gian dựa trên các bản ghi commit, vì vậy không nên giả định có thể dừng chính xác tại mọi mili giây tùy ý. Hãy xác định target dựa trên thời điểm giao dịch đã biết và đối chiếu log ứng dụng, audit hoặc restore point.

Với target theo tên, cấu hình có dạng:

~~~conf
recovery_target_name = 'before_monthly_import'
recovery_target_timeline = 'latest'
recovery_target_action = 'pause'
~~~

Với target theo LSN, ví dụ:

~~~conf
recovery_target_lsn = '0/7A1200'
recovery_target_timeline = 'latest'
recovery_target_action = 'pause'
~~~

LSN trong ví dụ chỉ là giá trị minh họa. Khi vận hành, sử dụng đúng LSN đã ghi lại từ restore point hoặc sự kiện cần phục hồi.

Sau khi cấu hình, tạo file tín hiệu recovery:

~~~bash
touch /var/lib/postgresql/data/recovery.signal
~~~

Đường dẫn phải là PGDATA thực tế của instance đích. PostgreSQL 12 trở lên dùng recovery.signal để yêu cầu archive recovery; các phiên bản cũ dùng cơ chế recovery.conf khác. Không trộn cấu hình của các major version.

### Khởi động và theo dõi recovery

Khởi động instance đích theo cách quản lý service của môi trường. Theo dõi log PostgreSQL và xác nhận:

- Server đã nhận diện recovery.signal.
- restore_command tìm được các WAL segment cần thiết.
- Không có lỗi checksum, lỗi định dạng hoặc thiếu segment.
- PostgreSQL phát lại WAL theo đúng thứ tự.
- Recovery target đã đạt và server tạm dừng theo cấu hình.

Trong lúc recovery, có thể kiểm tra trạng thái bằng:

~~~sql
SELECT pg_is_in_recovery();
~~~

Khi đang ở recovery, kết quả là true. Nếu đã cấu hình pause và target đạt, có thể kết nối đọc dữ liệu để kiểm tra trước khi promote. Không cho ứng dụng ghi vào instance đang ở trạng thái phục hồi.

Sau khi dữ liệu được đối soát và có quyết định chuyển đổi, có thể promote server:

~~~sql
SELECT pg_promote();
~~~

Hoặc dùng lệnh pg_ctl promote với data directory tương ứng. Sau khi promote, kiểm tra:

~~~sql
SELECT pg_is_in_recovery();
~~~

Kết quả false cho biết server đã rời recovery và trở thành primary có thể nhận ghi, tùy cấu hình quyền và kết nối. Nếu đặt recovery_target_action là promote, PostgreSQL sẽ tự promote khi đạt target; với quy trình cần kiểm tra trước, pause cho phép giữ server ở trạng thái chỉ đọc trong giai đoạn xác minh.

### Timeline sau failover

Khi một server được promote, PostgreSQL tạo timeline mới. Timeline history giúp xác định nhánh WAL mà server đã đi qua. Khi phục hồi qua nhiều lần failover, cần bảo đảm cả WAL segment và file timeline history đều có trong kho archive.

recovery_target_timeline = 'latest' thường phù hợp khi muốn theo timeline mới nhất có sẵn. Nếu cần phục hồi vào một nhánh cụ thể, phải xác minh timeline mong muốn và đặt target có chủ đích. Không suy đoán timeline chỉ từ tên file WAL.

### Những lỗi recovery thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không tìm thấy WAL segment | Archive thiếu file, restore_command sai hoặc quyền đọc không đủ | Log PostgreSQL, đường dẫn archive, quyền truy cập |
| Recovery dừng trước target | Thiếu WAL, archive chưa kịp nhận segment hoặc chọn target ngoài khoảng dữ liệu | Kiểm kê chuỗi WAL, thời điểm base backup và thời điểm archive cuối |
| Báo lỗi timeline | Thiếu timeline history hoặc chọn nhánh WAL sai | Kiểm tra file history và timeline của backup |
| Target time không như mong đợi | Sai timezone, target không khớp commit record hoặc inclusive setting không phù hợp | Đối chiếu thời gian commit, log ứng dụng và cấu hình timezone |
| Server không vào recovery | Thiếu recovery.signal, file đặt sai PGDATA hoặc cấu hình không được nạp | Kiểm tra data directory, startup log và major version |
| Server khởi động nhưng dữ liệu thiếu | Base backup không phù hợp, thiếu WAL hoặc target đặt quá sớm | Xác minh backup, WAL chain và target đã chọn |

Khi recovery thất bại, giữ lại log và bản phục hồi để điều tra. Không xóa WAL hoặc thay đổi target liên tục mà không ghi nhận trạng thái từng lần thử.

## 6. Phục hồi logical backup

PITR phù hợp cho toàn cụm, còn logical restore phù hợp khi chỉ cần một database hoặc một nhóm đối tượng.

### Phục hồi database từ dump custom

Trên cụm đích, trước tiên tạo role, extension và tablespace cần thiết. Sau đó tạo database và restore:

~~~bash
createdb -T template0 appdb_restore
pg_restore --exit-on-error --verbose \
  -d appdb_restore \
  /backups/appdb.dump
~~~

Nếu database dump chứa đối tượng phụ thuộc extension, cần cài extension tương ứng trên server đích. Kiểm tra owner, grants, default privileges, collation và locale. Không dùng --no-owner hoặc --no-privileges một cách máy móc nếu ứng dụng phụ thuộc vào quyền đã định nghĩa trong nguồn.

Có thể phục hồi riêng một schema hoặc table bằng các tùy chọn --schema, --table và danh sách đối tượng phù hợp. Khi chỉ phục hồi một table, cần kiểm tra phụ thuộc như sequence, type, function, trigger, foreign key và dữ liệu tham chiếu. Một table được nạp thành công chưa chắc đã hoạt động độc lập.

### Phục hồi từ plain SQL dump

Dump plain text có thể được nạp bằng psql:

~~~bash
psql -X -v ON_ERROR_STOP=1 -d appdb_restore -f /backups/appdb.sql
~~~

-X không đọc file psqlrc của người dùng, giúp lệnh phục hồi ít bị ảnh hưởng bởi cấu hình cá nhân.
-v ON_ERROR_STOP=1 yêu cầu psql dừng khi gặp lỗi SQL thay vì tiếp tục âm thầm.

Lưu log stdout/stderr của quá trình restore và ghi nhận exit code. Nếu restore thất bại giữa chừng, xác định đối tượng đã được tạo trước khi quyết định xóa database đích và chạy lại.

### So sánh logical restore với PITR

Logical restore cho phép chọn đối tượng nhưng không tái tạo toàn bộ trạng thái vật lý của cluster tại một thời điểm. PITR vật lý tái tạo trạng thái toàn cụm bằng WAL nhưng không có thao tác chọn một table để bỏ qua các thay đổi còn lại.

Nếu cần lấy lại một table đã bị xóa nhầm:

1. Dựng một cụm tạm từ base backup và WAL tới thời điểm ngay trước khi xóa.
2. Xác minh dữ liệu trong cụm tạm.
3. Dùng pg_dump hoặc COPY để xuất table và các dữ liệu phụ thuộc.
4. Kiểm tra khóa, sequence, constraint và quan hệ với dữ liệu hiện tại.
5. Nhập vào database hiện tại theo một giao dịch hoặc quy trình migration được kiểm soát.

Không thay thế nguyên cụm production bằng bản PITR cũ nếu nghiệp vụ chỉ yêu cầu lấy lại một phần dữ liệu; làm như vậy có thể loại bỏ các giao dịch hợp lệ phát sinh sau target.

## 7. Đối soát dữ liệu sau phục hồi

### Phân biệt kiểm tra kỹ thuật và kiểm tra nghiệp vụ

Kiểm tra kỹ thuật trả lời câu hỏi: PostgreSQL có khởi động được không, WAL có được phát lại không, các bảng có đọc được không và các extension có hoạt động không.

Đối soát nghiệp vụ trả lời câu hỏi: dữ liệu có đúng với trạng thái cần khôi phục không, giao dịch nào đã mất, tổng tiền có khớp không và ứng dụng có thể tiếp tục từ trạng thái này không.

Hai nhóm kiểm tra đều cần thiết. Một cụm database khởi động thành công vẫn có thể chứa dữ liệu không phù hợp với mục tiêu phục hồi.

### Xác định mốc dữ liệu cần đối soát

Trước khi so sánh, thống nhất:

- Recovery target cụ thể và timezone.
- Transaction hoặc batch cuối cùng được kỳ vọng có mặt.
- Transaction đầu tiên cần bị loại bỏ.
- Khoảng thời gian dữ liệu cần đối chiếu.
- Nguồn độc lập dùng để kiểm chứng, chẳng hạn audit log, sổ cái, hệ thống thanh toán hoặc event log.

Không so sánh số liệu của hai hệ thống ở hai thời điểm khác nhau rồi kết luận rằng dữ liệu bị mất. Với dữ liệu phát sinh liên tục, phải cố định cùng một mốc thời gian hoặc cùng một business sequence.

### Kiểm tra tổng quan database

Sau khi phục hồi, kiểm tra database và các bảng quan trọng:

~~~sql
SELECT
    current_database() AS database_name,
    current_timestamp AS checked_at,
    pg_is_in_recovery() AS is_in_recovery;

SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables
ORDER BY schemaname, relname;
~~~

pg_stat_user_tables cung cấp số liệu thống kê ước lượng, không phải phép đếm chính xác. Dùng COUNT(*) cho các bảng hoặc phân vùng cần kiểm chứng chính xác, cân nhắc chi phí đọc khi bảng lớn.

Ví dụ kiểm tra số đơn hàng theo ngày:

~~~sql
SELECT
    created_at::date AS order_date,
    count(*) AS order_count,
    sum(total_amount) AS total_amount
FROM orders
WHERE created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-15 00:00:00'
GROUP BY created_at::date
ORDER BY order_date;
~~~

So sánh kết quả với báo cáo đã được xác nhận, bản ghi audit hoặc nguồn nghiệp vụ độc lập. Với dữ liệu tiền tệ, dùng kiểu numeric phù hợp và quy tắc làm tròn giống ứng dụng.

### Kiểm tra khóa và quan hệ

Kiểm tra các khóa chính, khóa duy nhất và foreign key đã được tạo và validate. Ví dụ tìm các bản ghi đơn hàng không có khách hàng tương ứng trong một hệ thống mà quan hệ này phải luôn tồn tại:

~~~sql
SELECT count(*) AS orphan_orders
FROM orders o
LEFT JOIN customers c
    ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
~~~

Nếu kết quả khác 0, cần xác định đó là dữ liệu hợp lệ theo mô hình hay lỗi phục hồi/nhập dữ liệu. Không tự động xóa hoặc sửa các bản ghi chỉ để làm cho con số bằng 0.

Với bảng lớn, có thể kiểm tra theo từng partition, khoảng khóa hoặc ngày nghiệp vụ để giới hạn chi phí. Ghi lại câu lệnh, thời điểm và kết quả để lần diễn tập sau có thể so sánh.

### Đối chiếu dữ liệu với hệ thống bên ngoài

Một database giao dịch thường liên kết với các hệ thống khác:

- Cổng thanh toán có thể đã thu tiền dù transaction ghi nhận đơn hàng bị rollback bởi PITR.
- Message broker có thể đã phát event trước thời điểm phục hồi.
- Email hoặc thông báo đã gửi không tự biến mất khi database quay về quá khứ.
- Kho dữ liệu hoặc hệ thống báo cáo có thể đã nhận bản ghi từ database trước khi PITR.
- Hệ thống kế toán có thể đã ghi nhận một bút toán không còn trong database phục hồi.

Do đó, cần đối chiếu database với các nguồn độc lập và lập danh sách sự kiện cần bù, phát lại hoặc hoàn tác theo nghiệp vụ. Không gửi lại thanh toán, email hoặc event chỉ dựa trên việc một hàng dữ liệu không còn tồn tại sau PITR; trước tiên phải kiểm tra idempotency key và trạng thái tại hệ thống nhận.

### Kiểm tra sequence và identity

Với physical PITR, trạng thái sequence được khôi phục cùng WAL. Với logical dump, sequence state thường được lưu trong dump, nhưng các thao tác nhập dữ liệu thủ công hoặc phục hồi chọn lọc có thể làm sequence lệch khỏi dữ liệu.

Kiểm tra sequence sau khi import một phần dữ liệu. Không đặt sequence về MAX(id) một cách máy móc khi hệ thống dùng sequence chung, ID được cấp trước hoặc có dữ liệu đồng thời. Nếu đã xác minh sequence thấp hơn ID lớn nhất trong bảng và không có writer, có thể đồng bộ theo chính sách của ứng dụng.

Ví dụ minh họa cho bảng có cột id dùng sequence riêng:

~~~sql
SELECT setval(
    pg_get_serial_sequence('public.orders', 'id'),
    COALESCE((SELECT max(id) FROM public.orders), 1),
    EXISTS (SELECT 1 FROM public.orders)
);
~~~

Lệnh này giả định sequence gắn với cột id và bảng đã ngừng ghi trong thời gian sửa. Nếu sequence được chia sẻ bởi nhiều bảng, hoặc ứng dụng cấp ID theo cách khác, cần xác định quy tắc cấp phát trước khi điều chỉnh. Việc đặt sequence có thể tạo khoảng trống ID; khoảng trống không phải lỗi dữ liệu.

### Lập biên bản đối soát

Mỗi lần phục hồi nên lưu một biên bản gồm:

| Nội dung | Bằng chứng cần lưu |
| --- | --- |
| Nguồn phục hồi | Tên base backup, checksum/manifest, vị trí WAL archive |
| Recovery target | Thời điểm có timezone, restore point/LSN nếu dùng, timeline |
| Kết quả kỹ thuật | Log recovery, trạng thái pg_is_in_recovery(), kết quả promote |
| Đối soát dữ liệu | COUNT, tổng tiền, min/max thời gian, khóa và quan hệ |
| Đối chiếu bên ngoài | Thanh toán, message, audit, event và hệ thống downstream |
| Sai lệch | Danh sách bản ghi/sự kiện cần xử lý tiếp |
| Phê duyệt | Người xác nhận nghiệp vụ, người vận hành và thời điểm cutover |

Biên bản giúp người vận hành khác hiểu rõ dữ liệu đã quay về mốc nào và những tác động còn cần xử lý.

## 8. Chuyển ứng dụng sang cụm đã phục hồi

### Giữ hệ thống ở chế độ cô lập trong khi xác minh

Trong quá trình recovery và đối soát:

- Chặn ứng dụng ghi vào instance phục hồi.
- Giữ primary cũ ở trạng thái fenced hoặc ngắt khỏi đường ghi để tránh hai primary cùng nhận giao dịch.
- Chỉ cho phép nhóm vận hành và ứng dụng kiểm tra được cấp quyền kết nối.
- Tạm dừng các job, scheduler và consumer có thể ghi dữ liệu hoặc phát event.
- Ghi lại các thay đổi cấu hình đã thực hiện.

Đây là điều kiện quan trọng để dữ liệu không thay đổi trong lúc đối soát và tránh split-brain sau promote.

### Checklist trước cutover

Trước khi đổi endpoint ứng dụng, xác nhận:

1. Recovery đã đạt đúng target và log không có lỗi WAL.
2. Đối soát kỹ thuật và nghiệp vụ đạt yêu cầu.
3. Role, quyền, extension, function, trigger và job cần thiết hoạt động.
4. Ứng dụng có thể kết nối và chạy các truy vấn kiểm tra an toàn.
5. Các tác động bên ngoài đã được đánh giá và có kế hoạch bù/replay.
6. Primary cũ đã bị ngăn nhận ghi.
7. Backup mới và WAL archive được cấu hình cho primary sau phục hồi.
8. Monitoring, alert và quy trình rollback/cutover đã sẵn sàng.

Sau khi promote, xác minh pg_is_in_recovery() trả về false, archive mới hoạt động và các standby được dựng lại hoặc đồng bộ theo timeline mới. Không cho standby tiếp tục dùng một nhánh WAL cũ nếu nó không thể theo timeline mới; thực hiện quy trình rebuild/reseed theo công cụ replication.

## 9. Thiết kế lịch backup và retention

### Chọn lịch theo RPO/RTO

Lịch base backup và WAL archive cần dựa trên kích thước dữ liệu, tốc độ thay đổi, thời gian phục hồi và dung lượng lưu trữ.

Ví dụ một hệ thống có RPO mục tiêu 5 phút có thể:

- Archive WAL liên tục với độ trễ được giám sát.
- Tạo physical base backup hằng ngày hoặc theo chu kỳ phù hợp.
- Giữ đủ backup và WAL để phục hồi trong khoảng thời gian yêu cầu.
- Duy trì logical dump định kỳ cho một số database hoặc đối tượng quan trọng.
- Diễn tập restore để đo thời gian thực tế.

Đây chỉ là lịch minh họa. RPO thực tế còn phụ thuộc vào thời điểm WAL được tạo, archive command, thời gian truyền đến kho lưu trữ và khả năng phát hiện archive bị lỗi. Không cam kết RPO chỉ từ cấu hình archive_timeout.

### Retention phải bảo đảm chuỗi WAL

Khi xóa backup cũ, phải kiểm tra WAL nào còn cần cho các backup được giữ lại. Công cụ backup chuyên dụng thường quản lý quan hệ này qua catalog và retention policy. Nếu dùng script tự quản lý, cần hiểu chính xác backup start/end, WAL start/end và các timeline.

Không chạy lệnh xóa file WAL theo mẫu như “xóa mọi file cũ hơn N ngày” nếu chưa xác minh các backup còn cần. Một WAL segment có thể là mắt xích duy nhất giúp phục hồi một base backup vẫn còn trong retention.

### Giám sát dung lượng và độ trễ archive

Theo dõi:

- Dung lượng WAL phát sinh theo giờ/ngày.
- Dung lượng còn lại trong archive repository.
- Thời điểm archive thành công gần nhất.
- Số lần archive thất bại.
- Độ trễ từ lúc WAL segment hoàn tất tới lúc lưu trữ bền vững.
- Số lượng backup hợp lệ và tuổi backup gần nhất.
- Kết quả verify và restore drill.

Đặt cảnh báo trước khi kho archive hoặc filesystem gần đầy. Khi archive ngừng hoạt động, thư mục pg_wal có thể giữ lại các segment chưa archive và tăng dung lượng, ảnh hưởng tới khả năng hoạt động của database.

## 10. Diễn tập phục hồi định kỳ

### Vì sao phải diễn tập?

Backup có thể bị hỏng, thiếu WAL, thiếu role hoặc thiếu cấu hình. Các vấn đề này thường chỉ xuất hiện khi restore thật. Diễn tập định kỳ chứng minh rằng tổ chức có thể:

- Tìm đúng backup.
- Lấy đủ WAL.
- Khởi động PostgreSQL ở môi trường đích.
- Phục hồi tới target được yêu cầu.
- Đối soát dữ liệu.
- Đưa ứng dụng trở lại hoạt động trong RTO.

### Quy trình diễn tập mẫu

~~~text
Chọn backup và recovery target
          |
          v
Kiểm tra manifest và WAL chain
          |
          v
Phục hồi vào môi trường cô lập
          |
          v
Theo dõi recovery tới target
          |
          v
Kiểm tra kỹ thuật và đối soát nghiệp vụ
          |
          v
Đo thời gian, ghi sai lệch và bài học
          |
          v
Hủy môi trường thử nghiệm theo quy trình
~~~

Một lần diễn tập nên dùng bản backup được lấy từ kho lưu trữ thực tế, không chỉ dùng một bản vừa tạo trên cùng máy chủ. Nếu có thể, thử cả tình huống mất máy chủ nguồn và phục hồi sang một host khác.

### Đo kết quả

Ghi lại:

- Thời gian tìm và tải backup.
- Thời gian giải nén hoặc khôi phục base backup.
- Thời gian phát lại WAL.
- Thời gian đối soát dữ liệu.
- Tổng thời gian tới khi ứng dụng sẵn sàng.
- Dung lượng lưu trữ cần thiết.
- Các lỗi hoặc thao tác thủ công phát sinh.

Nếu thời gian phục hồi vượt RTO, cần cải thiện quy trình, hạ tầng, tần suất backup hoặc cách tổ chức dữ liệu. Nếu target không đạt được do thiếu WAL, cần sửa archive/retention trước khi tuyên bố hệ thống đáp ứng RPO.

## 11. Ví dụ tình huống: khôi phục trước một lần import sai

Một batch import bắt đầu lúc 10:00. Đến 10:12, người vận hành phát hiện dữ liệu đơn hàng bị nhân đôi. Batch đã commit nhiều transaction và ứng dụng vẫn tiếp tục nhận đơn mới. Mục tiêu là dựng trạng thái trước batch để điều tra và lấy lại dữ liệu đúng.

### Thu thập mốc thời gian

Ghi lại:

- Thời điểm bắt đầu batch và transaction đầu tiên.
- Thời điểm batch kết thúc.
- Thời điểm phát hiện lỗi.
- Mã batch, request ID hoặc import ID.
- Các transaction hợp lệ khác đã phát sinh trong cùng khoảng thời gian.
- Các sự kiện đã gửi sang payment gateway hoặc message broker.

Nếu trước batch đã tạo restore point, dùng tên restore point để giảm khả năng chọn sai thời điểm. Nếu không, chọn recovery_target_time dựa trên log commit và audit, có timezone rõ ràng.

### Dựng cụm phục hồi

Chọn base backup gần nhất nhưng trước target. Xác minh manifest và chuỗi WAL. Phục hồi sang một host hoặc data directory riêng, cấu hình restore_command và target, tạo recovery.signal rồi khởi động.

Đặt recovery_target_action = pause để giữ cụm ở trạng thái recovery khi target đạt. Đọc log để xác nhận server đã phát lại WAL đến đúng mốc. Sau đó kiểm tra số đơn hàng, tổng tiền và các bản ghi import liên quan.

### Đối soát và lấy dữ liệu

Nếu cụm phục hồi đúng trạng thái trước batch, so sánh với audit và hệ thống bên ngoài. Xác định đơn hàng nào đã tồn tại trước batch và giao dịch nào đã được thanh toán. Không đưa toàn bộ database cũ trở lại production nếu những đơn hàng hợp lệ phát sinh sau target cần được giữ lại.

Có thể xuất tập dữ liệu cần khôi phục từ cụm tạm, làm sạch trùng lặp theo khóa nghiệp vụ và nhập vào cụm hiện tại bằng quy trình idempotent. Nếu cần quay toàn bộ hệ thống về trước batch, phải có phê duyệt nghiệp vụ về việc mất các giao dịch hợp lệ phát sinh sau target và có kế hoạch bù các tác động bên ngoài.

### Chuyển đổi

Chỉ promote và chuyển ứng dụng sang cụm phục hồi nếu quyết định nghiệp vụ là thay thế toàn bộ trạng thái hiện tại. Nếu mục tiêu chỉ là lấy lại một phần dữ liệu, giữ cụm hiện tại và chỉ trích xuất dữ liệu cần thiết. Sau khi cutover, tạo base backup mới và xác nhận WAL archive trên timeline mới.

## 12. Những sai lầm cần tránh

| Sai lầm | Hậu quả | Cách làm phù hợp |
| --- | --- | --- |
| Chỉ có pg_dump nhưng kỳ vọng PITR | Không có chuỗi WAL liên tục để quay về mọi thời điểm | Dùng physical base backup và WAL archive cho PITR |
| Chỉ sao chép PGDATA khi server đang chạy | Bản sao có thể không nhất quán | Dùng pg_basebackup hoặc quy trình snapshot được PostgreSQL hỗ trợ |
| Không kiểm tra archive thất bại | WAL bị thiếu và recovery không tới target | Giám sát pg_stat_archiver, log và kho lưu trữ |
| Xóa WAL theo tuổi file | Có thể phá chuỗi WAL cần cho backup còn giữ | Dùng retention-aware backup manager |
| Restore đè lên primary đang hoạt động | Có nguy cơ mất dữ liệu và gây split-brain | Phục hồi vào môi trường cô lập rồi mới quyết định cutover |
| Chọn thời điểm mà không ghi timezone | Có thể phục hồi nhầm mốc | Dùng timestamp có offset hoặc UTC rõ ràng |
| Promote ngay khi recovery dừng | Bỏ qua đối soát dữ liệu | Pause, kiểm tra và chỉ promote sau khi xác nhận |
| Cho rằng replica là backup | Replica có thể sao chép thao tác sai | Duy trì backup độc lập và WAL archive |
| Chỉ kiểm tra server khởi động được | Có thể bỏ sót sai lệch nghiệp vụ | Đối soát số lượng, tổng tiền, quan hệ và hệ thống ngoài |
| Không diễn tập restore | Phát hiện thiếu backup/WAL khi sự cố thật xảy ra | Restore drill định kỳ và đo RTO/RPO thực tế |

## 13. Bộ lệnh tham khảo

Các lệnh dưới đây là điểm bắt đầu để kiểm tra. Điều chỉnh database, role, đường dẫn, phiên bản và quyền theo môi trường thực tế.

**Kiểm tra phiên bản và cấu hình WAL**

~~~sql
SELECT version();
SHOW wal_level;
SHOW archive_mode;
SHOW archive_command;
SHOW archive_timeout;
~~~

**Theo dõi archiver**

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

**Tạo restore point trước thay đổi**

~~~sql
SELECT pg_create_restore_point('before_release_2026_11_14');
~~~

**Tạo logical backup**

~~~bash
pg_dump -Fc -f /backups/appdb.dump appdb
pg_dumpall --globals-only > /backups/globals.sql
pg_restore --list /backups/appdb.dump
~~~

**Tạo physical base backup**

~~~bash
pg_basebackup \
  -h db-primary.example.internal \
  -p 5432 \
  -U backup_user \
  -D /backups/base-2026-11-14 \
  -F plain \
  -X stream \
  -P
~~~

**Kiểm tra physical backup**

~~~bash
pg_verifybackup /backups/base-2026-11-14
~~~

**Kiểm tra trạng thái sau recovery**

~~~sql
SELECT pg_is_in_recovery();
~~~

**Promote sau khi đối soát**

~~~sql
SELECT pg_promote();
~~~

Không chạy lệnh restore, promote hoặc thay đổi endpoint trên production chỉ vì các ví dụ này đã chạy thành công ở môi trường thử nghiệm. Hãy dùng đúng backup, target, host, quyền và quy trình cutover đã được xác minh.

## 14. Trình tự vận hành khuyến nghị

Khi thiết kế hoặc thực hiện phục hồi PostgreSQL, hãy theo trình tự:

1. Xác định RPO, RTO và phạm vi dữ liệu cần khôi phục.
2. Chọn logical backup, physical backup hoặc kết hợp cả hai.
3. Thiết lập WAL archiving và giám sát trạng thái archive.
4. Tạo base backup, kiểm tra manifest và lưu metadata.
5. Duy trì retention bảo đảm đủ backup và chuỗi WAL.
6. Khi có sự cố, chọn target có timezone/timeline rõ ràng và phục hồi sang môi trường cô lập.
7. Theo dõi recovery, xác nhận target và giữ server ở trạng thái pause trong lúc kiểm tra.
8. Đối soát kỹ thuật, dữ liệu nghiệp vụ và các tác động bên ngoài.
9. Quyết định phục hồi toàn cụm hay chỉ trích xuất dữ liệu cần thiết.
10. Promote/cutover theo kế hoạch, cấu hình backup và WAL archive cho primary mới.
11. Diễn tập định kỳ, đo RTO/RPO thực tế và cập nhật quy trình.

Một hệ thống chỉ thực sự có khả năng phục hồi khi tổ chức chứng minh được rằng bản backup đọc được, WAL đầy đủ, target có thể đạt, dữ liệu sau phục hồi được đối soát và ứng dụng có thể tiếp tục hoạt động trong thời gian mục tiêu.
