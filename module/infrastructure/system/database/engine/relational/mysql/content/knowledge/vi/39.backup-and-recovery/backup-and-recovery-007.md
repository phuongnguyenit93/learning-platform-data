# Physical backup, MySQL Enterprise Backup và lựa chọn công cụ theo điều kiện sử dụng

Physical backup (sao lưu vật lý) tạo bản sao từ các file dữ liệu và cấu trúc lưu trữ mà MySQL sử dụng, chẳng hạn tablespace InnoDB, redo log, undo tablespace và các file liên quan. Cách này phù hợp với cơ sở dữ liệu lớn vì không phải chuyển từng hàng thành câu lệnh SQL rồi nạp lại; khi phục hồi, công cụ có thể đưa các file về một trạng thái nhất quán để MySQL mở lại.

Tuy nhiên, sao chép file dữ liệu khi MySQL đang chạy không tự động tạo ra một bản backup hợp lệ. Trong lúc sao chép, InnoDB có thể ghi trang dữ liệu, tạo redo log, mở rộng tablespace hoặc thay đổi metadata. Một bản physical backup trực tuyến phải phối hợp việc đọc file, theo dõi thay đổi và áp dụng redo để các trang dữ liệu tương thích với cùng một mốc phục hồi. MySQL Enterprise Backup và Percona XtraBackup là hai lựa chọn phổ biến cho loại công việc này; snapshot của hệ thống lưu trữ và bản sao lạnh sau khi dừng MySQL cũng có thể phù hợp trong những điều kiện nhất định.

Chọn công cụ cần dựa trên phiên bản MySQL, storage engine, quy mô dữ liệu, thời gian gián đoạn cho phép, yêu cầu RPO/RTO, giấy phép, kỹ năng vận hành và khả năng kiểm thử phục hồi. Mục tiêu của bài này là giúp người vận hành hiểu các điều kiện đó và xây dựng một quy trình backup có thể phục hồi được.

## 1. Physical backup lưu những gì?

Một bản backup vật lý thường chứa các file dữ liệu và metadata cần để dựng lại instance. Phạm vi thực tế phụ thuộc công cụ, cấu hình server và cách tổ chức storage:

- File tablespace InnoDB, bao gồm system tablespace, file-per-table và các tablespace được cấu hình ở vị trí riêng.
- Redo log và thông tin cần thiết để đưa các trang dữ liệu về trạng thái nhất quán.
- Undo tablespace và các file hệ thống liên quan theo cách bố trí của phiên bản MySQL.
- Metadata về phiên bản, LSN, cấu hình backup, danh sách file và thông tin cần cho bước prepare/restore.
- Dữ liệu của các storage engine khác nếu công cụ và phương pháp backup hỗ trợ chúng theo cách nhất quán.

Không giả định toàn bộ dữ liệu đều nằm trong một thư mục `datadir`. Một instance có thể dùng đường dẫn riêng cho tablespace, redo/undo, binary log, relay log, keyring hoặc file cấu hình. Trước khi backup, hãy kiểm kê vị trí các file và xác định rõ công cụ có bao gồm từng vùng dữ liệu hay cần sao lưu bổ sung.

Physical backup thường gắn chặt với định dạng file và phiên bản MySQL. Khả năng restore sang phiên bản khác phụ thuộc ma trận tương thích của công cụ và MySQL; không nên xem file backup là định dạng trao đổi độc lập phiên bản. Hãy giữ thông tin phiên bản server, phiên bản công cụ, plugin, component và cấu hình tại thời điểm backup.

### Physical backup và logical backup

| Tiêu chí | Physical backup | Logical backup |
|---|---|---|
| Nội dung | File dữ liệu và metadata lưu trữ | Cấu trúc và dữ liệu được xuất thành câu lệnh hoặc định dạng logic |
| Tốc độ với database lớn | Thường nhanh hơn khi sao chép/khôi phục file theo khối | Có thể chậm hơn do đọc, chuyển đổi và thực thi từng đối tượng hoặc hàng |
| Tính linh hoạt | Phụ thuộc phiên bản, kiến trúc và công cụ tương thích | Dễ di chuyển hoặc chọn lọc schema/bảng hơn |
| Phục hồi | Chuẩn bị file, áp dụng redo rồi khởi động MySQL | Tạo schema và nạp lại dữ liệu bằng công cụ tương ứng |
| Phạm vi điển hình | Khôi phục instance lớn, phục hồi nhanh, tạo bản sao vật lý | Di chuyển dữ liệu, xuất một phần, kiểm tra hoặc lưu trữ độc lập định dạng |

Hai loại backup bổ sung cho nhau. Một hệ thống quan trọng có thể dùng physical backup để phục hồi instance nhanh, binary log để phục hồi tới thời điểm cụ thể và logical export cho các nhu cầu di chuyển hoặc khôi phục một phần. Không nên kỳ vọng một bản physical backup đơn lẻ giải quyết mọi tình huống phục hồi ở cấp bảng hoặc schema.

## 2. Điều kiện để bản sao vật lý nhất quán

InnoDB sử dụng cơ chế write-ahead logging. Khi thay đổi dữ liệu, redo log ghi nhận thông tin cần thiết để phục hồi; các trang dữ liệu có thể được ghi xuống file dữ liệu ở thời điểm khác. Vì vậy, trong một backup trực tuyến, các trang được sao chép có thể phản ánh những thời điểm khác nhau. Công cụ backup cần ghi nhận mốc LSN và thu thập đủ redo để đưa bản backup về trạng thái nhất quán.

Quy trình vật lý trực tuyến thường gồm các bước khái quát:

1. Khởi tạo phiên backup và ghi lại metadata, mốc LSN hoặc thông tin tương đương.
2. Sao chép các file dữ liệu trong khi ứng dụng vẫn có thể đọc/ghi theo giới hạn của công cụ.
3. Thu thập redo log phát sinh trong thời gian sao chép để không mất các thay đổi cần thiết cho tính nhất quán.
4. Hoàn tất backup và lưu metadata về file, phiên bản, vị trí log cùng trạng thái công việc.
5. Khi restore, chạy bước prepare/apply-log để áp dụng redo và đưa các file về trạng thái có thể mở bởi MySQL.

Đây là lý do không nên dùng một lệnh `cp -r` trên `datadir` đang hoạt động rồi coi kết quả là backup nóng. Việc sao chép có thể bỏ sót trang, redo hoặc file mới; MySQL cũng có thể đang thay đổi cấu trúc file trong lúc thao tác.

### Ba phương pháp vật lý phổ biến

| Phương pháp | Cách thực hiện | Ưu điểm | Giới hạn chính |
|---|---|---|---|
| Cold backup | Dừng MySQL sạch sẽ, sau đó sao chép toàn bộ file cần thiết | Dễ hiểu; không có ghi đồng thời trong lúc copy | Cần downtime đủ dài; phải kiểm kê mọi file ngoài `datadir` |
| Hot backup bằng công cụ | Công cụ chuyên dụng sao chép file và theo dõi redo khi server hoạt động | Giảm downtime; phù hợp database lớn | Cần phiên bản công cụ tương thích, quyền phù hợp và quy trình prepare/restore |
| Storage snapshot | Tạo snapshot ở tầng filesystem, volume hoặc storage array theo quy trình nhất quán | Tạo điểm chụp nhanh, hữu ích khi storage hỗ trợ snapshot hiệu quả | Phải đồng bộ nhiều volume và phối hợp với MySQL; snapshot đơn lẻ có thể chỉ crash-consistent |

Với cold backup, phải dừng MySQL theo cách sạch, chờ server hoàn tất shutdown rồi mới sao chép. Cần lưu cả các tablespace ở vị trí riêng và những file cần để giải mã dữ liệu. Khi restore, kiểm tra quyền sở hữu file và cấu hình phù hợp với instance đích.

Với hot backup, dùng API hoặc cơ chế được công cụ hỗ trợ. Nếu tự điều phối snapshot, cần hiểu backup lock và yêu cầu của phiên bản MySQL. `LOCK INSTANCE FOR BACKUP` có thể ngăn một số thao tác DDL hoặc thay đổi file trong khi vẫn cho phép hoạt động DML theo quy định của MySQL; nó không tự sao chép dữ liệu và không thay thế quy trình snapshot nhất quán. Cú pháp, quyền `BACKUP_ADMIN` và giới hạn cụ thể cần kiểm tra theo phiên bản đang chạy.

Với snapshot, nếu dữ liệu, redo và binary log nằm trên các volume khác nhau, các snapshot phải đại diện cho cùng một mốc nhất quán. Hãy phối hợp flush/lock theo hướng dẫn của MySQL và nhà cung cấp storage. Snapshot có thể được tạo rất nhanh, nhưng nó vẫn nằm trong cùng miền lỗi nếu cùng thiết bị, tài khoản cloud hoặc vùng lưu trữ với máy chủ chính. Cần sao chép snapshot ra miền lỗi độc lập và kiểm thử restore.

## 3. MySQL Enterprise Backup

MySQL Enterprise Backup (MEB) là công cụ backup vật lý thương mại thuộc hệ sinh thái MySQL Enterprise của Oracle. Công cụ được thiết kế để backup và restore MySQL, đặc biệt hữu ích khi tổ chức cần hỗ trợ thương mại của Oracle, quy trình backup online, backup tăng dần hoặc các tính năng doanh nghiệp đi kèm.

MEB sử dụng chương trình dòng lệnh `mysqlbackup`. Tùy phiên bản, giấy phép và cấu hình, công cụ hỗ trợ các khả năng như:

- Full backup và incremental backup dựa trên những thay đổi kể từ một mốc backup.
- Backup toàn instance hoặc chọn phạm vi dữ liệu theo khả năng được hỗ trợ.
- Backup nóng cho InnoDB với cơ chế thu thập redo để bảo đảm tính nhất quán.
- Nén và mã hóa backup theo các tùy chọn được phiên bản hỗ trợ.
- Streaming hoặc ghi backup tới loại storage mà phiên bản và cấu hình công cụ hỗ trợ.
- Kiểm tra, chuẩn bị và phục hồi backup bằng các thao tác riêng của công cụ.

Không phải mọi tính năng đều có cùng cú pháp hoặc điều kiện trên tất cả phiên bản. Trước khi triển khai, đối chiếu phiên bản MEB với phiên bản MySQL Server, hệ điều hành, storage engine và các plugin đang dùng. Kiểm tra yêu cầu giấy phép, quyền tài khoản backup, dung lượng tạm, băng thông và vị trí lưu backup.

### Ví dụ tạo full backup

Ví dụ minh họa trên Linux, giả sử cấu hình MySQL được đọc từ `/etc/my.cnf` và thư mục backup đã được tạo với quyền phù hợp:

```bash
mysqlbackup \
  --defaults-file=/etc/my.cnf \
  --user=backup_user \
  --password \
  --backup-dir=/backup/mysql/full-2026-11-19 \
  backup
```

`--password` yêu cầu nhập mật khẩu tương tác ở các môi trường hỗ trợ cách gọi này. Không ghi mật khẩu thật trong script, shell history hoặc log. Trong vận hành tự động, dùng cơ chế quản lý secret và phương thức xác thực mà phiên bản công cụ hỗ trợ.

Tài khoản backup phải có đúng các quyền mà phiên bản MEB yêu cầu. Tạo tài khoản riêng, chỉ cấp quyền tối thiểu theo tài liệu của phiên bản đó và giới hạn host nguồn. Không mặc định dùng tài khoản `root` hoặc tài khoản ứng dụng để chạy backup.

### Incremental backup và chuỗi backup

Incremental backup chỉ lưu những thay đổi được công cụ xác định kể từ một mốc backup trước đó. Cách này giảm dung lượng và thời gian truyền ở mỗi lần chạy, nhưng làm tăng độ phức tạp khi phục hồi: phải có full backup gốc và đầy đủ các incremental backup cần thiết theo đúng thứ tự.

Ví dụ lịch vận hành có thể là một full backup định kỳ, sau đó nhiều incremental backup trong khoảng giữa hai lần full. Đây chỉ là mẫu tổ chức; tần suất thực tế phải dựa trên RPO, tốc độ thay đổi dữ liệu, cửa sổ backup, dung lượng lưu trữ và thời gian restore đã đo được.

Khi chạy incremental bằng MEB, hãy dùng metadata/history của công cụ để chọn đúng mốc cơ sở, lưu từng incremental vào thư mục riêng và giữ lại toàn bộ chuỗi phụ thuộc. Không tự suy ra mốc từ tên thư mục hoặc chỉ dựa vào timestamp. Cú pháp lựa chọn incremental base và cách apply từng phần phụ thuộc phiên bản MEB; hãy dùng đúng hướng dẫn của phiên bản đã cài.

### Chuẩn bị và phục hồi bằng MEB

Một quy trình restore tổng quát gồm:

1. Chọn full backup và mọi incremental backup cần thiết cho mốc phục hồi.
2. Chuẩn bị máy chủ đích với phiên bản MySQL và MEB tương thích; dừng `mysqld` trước khi thay dữ liệu.
3. Bảo đảm thư mục dữ liệu đích rỗng hoặc đã được di chuyển an toàn; xác định đúng `datadir` và các đường dẫn tablespace riêng.
4. Chạy thao tác prepare/apply-log và copy-back theo thứ tự mà MEB yêu cầu.
5. Khôi phục quyền sở hữu file, cấu hình, keyring và plugin cần thiết.
6. Khởi động MySQL, kiểm tra error log, trạng thái InnoDB, dữ liệu và quyền truy cập.
7. Nếu cần point-in-time recovery (PITR), áp dụng binary log sau mốc backup tới thời điểm mong muốn.

Ví dụ thao tác copy-back-and-apply-log cho một full backup đơn giản:

```bash
mysqlbackup \
  --defaults-file=/etc/my.cnf \
  --backup-dir=/backup/mysql/full-2026-11-19 \
  copy-back-and-apply-log
```

Đây là ví dụ quy trình, không phải lệnh có thể chạy nguyên trạng trên mọi máy. Cấu hình `datadir`, đường dẫn backup, cách xử lý incremental và các tùy chọn restore phải khớp môi trường thực tế. Dừng MySQL và xác minh thư mục đích trước khi copy-back để tránh ghi đè nhầm dữ liệu. Đọc log của MEB và xác nhận thao tác hoàn tất thành công trước khi khởi động server.

## 4. Percona XtraBackup

Percona XtraBackup là công cụ physical backup phổ biến trong hệ sinh thái Percona. Đây là lựa chọn thường được cân nhắc khi tổ chức muốn sử dụng công cụ mã nguồn mở cho backup nóng InnoDB và có khả năng tự vận hành hoặc sử dụng dịch vụ hỗ trợ phù hợp.

XtraBackup hỗ trợ các quy trình full/incremental backup, prepare và copy-back theo phiên bản. Công cụ sử dụng cơ chế đọc file dữ liệu và thu thập redo để tạo backup nhất quán cho các phiên bản MySQL mà nó hỗ trợ. Phạm vi hỗ trợ thay đổi theo phiên bản XtraBackup; cần kiểm tra ma trận tương thích trước khi nâng cấp MySQL hoặc công cụ. Không giả định một bản XtraBackup mới nhất sẽ hỗ trợ mọi phiên bản MySQL cũ, hay ngược lại.

Ví dụ full backup:

```bash
xtrabackup \
  --backup \
  --target-dir=/backup/mysql/full-2026-11-19 \
  --user=backup_user \
  --password
```

Sau khi backup, cần chạy bước prepare để áp dụng redo và hoàn thiện bản backup. Ví dụ:

```bash
xtrabackup \
  --prepare \
  --target-dir=/backup/mysql/full-2026-11-19
```

Khi phục hồi, dừng MySQL, bảo đảm `datadir` đích đã được xử lý an toàn rồi chạy copy-back:

```bash
xtrabackup \
  --copy-back \
  --target-dir=/backup/mysql/full-2026-11-19
```

Sau copy-back, kiểm tra và chỉnh quyền sở hữu file theo tài khoản hệ điều hành chạy MySQL, ví dụ:

```bash
chown -R mysql:mysql /var/lib/mysql
```

Đường dẫn `/var/lib/mysql` và user/group `mysql` chỉ là ví dụ; thay bằng giá trị thực tế. Nếu dùng incremental backup, phải prepare full backup và apply các incremental theo đúng thứ tự bằng tùy chọn tương ứng của phiên bản XtraBackup. Không khởi động MySQL với chuỗi incremental chưa được áp dụng đầy đủ.

XtraBackup có thể cần xử lý riêng các bảng hoặc storage engine không phải InnoDB. Với các đối tượng đó, mức độ khóa và tính nhất quán phụ thuộc engine, phiên bản và tùy chọn backup. Hãy kiểm tra log để biết công cụ đã backup những gì, các bảng nào cần khóa hoặc phương án bổ sung. Một lệnh backup trả về thành công không có nghĩa mọi loại dữ liệu trong instance đều đã được bảo vệ theo cùng một mức nhất quán.

## 5. Snapshot ở tầng filesystem hoặc storage

Snapshot tạo ảnh chụp của volume hoặc filesystem tại một thời điểm. Đây là lựa chọn tốt khi nền tảng lưu trữ có snapshot hiệu quả, hỗ trợ clone nhanh hoặc cần tạo nhiều bản sao môi trường kiểm thử. Tuy nhiên, tính nhất quán của snapshot phụ thuộc cách phối hợp với MySQL.

Phân biệt hai mức:

- **Crash-consistent:** snapshot giống trạng thái volume sau một sự cố mất điện. InnoDB có thể dùng redo để crash recovery khi khởi động, nhưng cần bảo đảm mọi file cần thiết cùng thuộc một điểm chụp nhất quán.
- **Application-consistent:** snapshot được phối hợp với MySQL để hạn chế các thay đổi file/metadata trong khoảng chụp và ghi nhận trạng thái cần thiết. Mức độ bảo đảm phụ thuộc quy trình, backup lock, flush và nền tảng storage.

Một quy trình snapshot có thể bao gồm các bước sau, nhưng cần điều chỉnh theo hướng dẫn MySQL và storage cụ thể:

1. Xác định tất cả volume chứa `datadir`, tablespace riêng và các file liên quan cần giữ.
2. Xác nhận dung lượng, thời gian tạo snapshot và khả năng snapshot đồng thời của nền tảng.
3. Phối hợp với MySQL bằng cơ chế backup lock/flush phù hợp phiên bản; không tự ý khóa bảng hoặc dừng ghi mà không hiểu tác động.
4. Tạo snapshot nhất quán cho tất cả volume liên quan, ghi lại mốc thời gian, GTID hoặc binary log coordinate phù hợp.
5. Giải phóng lock ngay khi snapshot hoàn tất theo quy trình.
6. Tạo bản sao độc lập từ snapshot, kiểm tra metadata và thực hiện restore thử.

Nếu các volume được snapshot lệch thời điểm, file dữ liệu có thể không khớp với redo hoặc metadata. Nếu chỉ snapshot volume dữ liệu mà bỏ sót external tablespace hay keyring, bản restore có thể không mở được database. Snapshot cũng không phải backup độc lập nếu snapshot và dữ liệu gốc dùng chung thiết bị, tài khoản quản trị hoặc miền lỗi.

## 6. So sánh và chọn công cụ theo điều kiện sử dụng

| Lựa chọn | Khi nên cân nhắc | Điểm cần đánh giá |
|---|---|---|
| MySQL Enterprise Backup | Tổ chức dùng MySQL Enterprise, cần công cụ thuộc Oracle và hỗ trợ thương mại tương ứng | Chi phí/giấy phép, hỗ trợ phiên bản, quyền backup, tính năng restore, tích hợp quy trình hiện có |
| Percona XtraBackup | Tổ chức muốn công cụ mã nguồn mở, có năng lực vận hành và phiên bản được hỗ trợ | Ma trận tương thích, loại engine, tính năng MySQL đang dùng, hỗ trợ từ Percona hoặc cộng đồng |
| Cold filesystem copy | Database nhỏ hoặc môi trường có thể dừng MySQL trong cửa sổ bảo trì | Thời gian downtime, kiểm kê mọi file, quy trình shutdown sạch và restore |
| Storage snapshot | Hạ tầng có snapshot đáng tin cậy, cần tạo bản sao nhanh hoặc clone môi trường | Application consistency, nhiều volume, khả năng export ra miền lỗi độc lập, chi phí lưu giữ snapshot |
| Logical dump | Cần di chuyển giữa phiên bản/kiến trúc, xuất một phần schema/bảng hoặc lưu định dạng logic | Thời gian export/import, dung lượng, charset, routine/event/trigger và tính nhất quán của dump |

Có thể dùng cây quyết định đơn giản:

```text
Có cần backup online cho database InnoDB lớn?
  ├─ Có
  │   ├─ Cần Oracle MySQL Enterprise và hỗ trợ tương ứng?
  │   │    └─ Có -> Đánh giá MySQL Enterprise Backup
  │   └─ Không -> Kiểm tra XtraBackup có hỗ trợ chính xác phiên bản/tính năng
  │
  └─ Không
      ├─ Có cửa sổ dừng MySQL đủ dài?
      │    └─ Có -> Cân nhắc cold backup có shutdown sạch
      └─ Storage có snapshot nhất quán được kiểm chứng?
           └─ Có -> Cân nhắc snapshot, kèm bản sao độc lập và restore test
```

Một số nguyên tắc lựa chọn:

- Chọn theo phiên bản MySQL đang chạy, không chỉ theo phiên bản công cụ mới nhất. Kiểm tra plugin, component, encryption, tablespace riêng và engine không phải InnoDB.
- Nếu RTO thấp và dữ liệu lớn, đo thời gian full backup, incremental, prepare, copy-back và khởi động thật. Thời gian tạo backup ngắn không đảm bảo thời gian phục hồi ngắn.
- Nếu cần hỗ trợ từ Oracle, kiểm tra quyền sử dụng MySQL Enterprise Backup và phạm vi hợp đồng hỗ trợ.
- Nếu dùng XtraBackup, xác định ai theo dõi tương thích, nâng cấp, lỗi backup và quy trình phục hồi.
- Nếu dùng snapshot, kiểm chứng tính nhất quán xuyên volume và quy trình xuất snapshot ra vùng lưu trữ độc lập.
- Nếu cần phục hồi một bảng hoặc di chuyển chọn lọc, kết hợp logical export hoặc quy trình phục hồi tạm thời rồi export đối tượng cần thiết.

MySQL Clone Plugin có thể hữu ích để cấp phát một instance từ một nguồn khác trong các tình huống được hỗ trợ, nhưng không nên coi clone là hệ thống backup dài hạn. Clone phục vụ provisioning/replication; nó không tự cung cấp chính sách retention, bản sao offsite/immutable và khả năng phục hồi lịch sử như một hệ thống backup.

## 7. Kết hợp physical backup với binary log để PITR

Physical backup giúp khôi phục một mốc cơ sở. Binary log ghi nhận các thay đổi phát sinh sau đó. Kết hợp chúng cho phép phục hồi tới một thời điểm cụ thể, ví dụ ngay trước khi một câu lệnh `DELETE` nhầm được thực thi.

Quy trình point-in-time recovery (PITR) tổng quát:

1. Khôi phục full backup gần nhất có thể dùng được.
2. Áp dụng incremental backup liên quan nếu lịch backup có sử dụng incremental.
3. Xác định mốc log hoặc GTID mà backup đại diện.
4. Thu thập binary log liên tục từ mốc đó tới thời điểm cần phục hồi.
5. Dùng `mysqlbinlog` đọc và phát lại log theo thứ tự, dừng ngay trước giao dịch gây lỗi hoặc tại thời điểm mục tiêu.
6. Kiểm tra dữ liệu và ứng dụng trên instance phục hồi trước khi chuyển traffic.

Ví dụ xem nội dung binary log:

```bash
mysqlbinlog --base64-output=DECODE-ROWS -vv mysql-bin.000123
```

Ví dụ phát lại log trong một khoảng thời gian trên instance phục hồi:

```bash
mysqlbinlog \
  --start-datetime="2026-11-19 08:00:00" \
  --stop-datetime="2026-11-19 08:25:00" \
  mysql-bin.000123 mysql-bin.000124 \
  | mysql --user=recovery_user --password
```

Các timestamp trên chỉ là ví dụ. Cần xác định múi giờ, thứ tự file, vị trí bắt đầu và điểm dừng chính xác. Dừng theo timestamp có thể không đủ chính xác nếu nhiều giao dịch xảy ra sát nhau; với sự cố dữ liệu, cần đọc log và xác định transaction/position/GTID phù hợp trước khi phát lại. Không chạy pipeline phục hồi trên production đang phục vụ traffic.

Để PITR hoạt động, binary log phải được bật và lưu giữ đủ lâu. Cần sao chép log ra vùng lưu trữ độc lập liên tục, kiểm tra tính liên tục của file và bảo vệ chúng khỏi bị xóa cùng máy chủ. Ghi nhận GTID set hoặc binary log coordinate tại mốc backup theo cách công cụ cung cấp. Nếu backup từ replica, cần ghi nhận trạng thái replication và mốc nguồn tương ứng; không chỉ dựa vào chỉ số lag hiển thị.

## 8. Bảo vệ backup và quản lý vòng đời

Backup chứa dữ liệu thật của tổ chức, bao gồm thông tin khách hàng, dữ liệu nghiệp vụ và có thể cả thông tin xác thực trong các bảng hệ thống. Hãy áp dụng kiểm soát bảo mật tương đương hoặc nghiêm ngặt hơn dữ liệu production.

- **Mã hóa khi lưu:** dùng tính năng mã hóa của công cụ hoặc mã hóa ở tầng storage. Bảo vệ khóa mã hóa tách khỏi nơi lưu backup; không để khóa duy nhất nằm cùng miền lỗi với bản backup.
- **Phân quyền:** tài khoản ghi backup chỉ có quyền cần thiết; tài khoản restore và người đọc backup được kiểm soát riêng. Ghi log thao tác truy cập và xóa.
- **Bản sao độc lập:** lưu ít nhất một bản ở miền lỗi khác, chẳng hạn tài khoản lưu trữ hoặc vùng địa lý khác theo chính sách tổ chức.
- **Immutable/retention lock:** cân nhắc lưu trữ chống sửa/xóa trong khoảng thời gian quy định để giảm nguy cơ ransomware hoặc xóa nhầm.
- **Kiểm tra toàn vẹn:** kiểm tra mã băm, kích thước, metadata, log công cụ và khả năng đọc của backup sau khi truyền.
- **Quản lý khóa:** giữ keyring, khóa giải mã tablespace và cấu hình cần thiết trong kho bí mật được kiểm soát. Nếu mất khóa, backup mã hóa có thể không phục hồi được.
- **Bảo vệ cấu hình:** lưu bản cấu hình MySQL, plugin/component, chứng thư và thông tin môi trường cần cho restore; loại bỏ hoặc bảo vệ secret theo quy trình riêng.

Thiết kế retention theo mục tiêu phục hồi. Ví dụ, có thể giữ nhiều full backup theo chu kỳ, incremental giữa các full và binary log liên tục trong cửa sổ PITR. Khi xóa một full backup, phải đánh giá các incremental phụ thuộc vào nó. Đừng xóa log cần thiết cho PITR chỉ vì đã có một full backup mới hơn nếu vẫn cần phục hồi các mốc trong khoảng đó.

## 9. Quy trình kiểm thử phục hồi

Backup chỉ được xem là đáng tin khi có thể restore trong điều kiện gần với thực tế. Một quy trình kiểm thử nên diễn ra trên máy chủ cô lập, có đủ dung lượng và không kết nối nhầm tới hệ thống production.

### Các bước thực hành

1. Chọn một full backup và các incremental liên quan từ kho lưu trữ; xác minh checksum và metadata.
2. Chuẩn bị host phục hồi có phiên bản MySQL, plugin và công cụ tương thích. Cấp quyền truy cập khóa giải mã và cấu hình cần thiết.
3. Dừng MySQL trên host đích; chuẩn bị `datadir` sạch và các đường dẫn tablespace phù hợp.
4. Chạy prepare/apply-log theo công cụ; kiểm tra log và exit code.
5. Copy-back hoặc mount snapshot theo quy trình; khôi phục owner, permission và cấu hình.
6. Khởi động MySQL trong mạng cô lập. Kiểm tra error log, trạng thái InnoDB, plugin, tablespace và replication metadata.
7. Nếu cần PITR, phát lại binary log tới mốc đã chọn.
8. Kiểm tra số lượng bản ghi, tổng hợp nghiệp vụ, khóa ngoại, dữ liệu mẫu, user/grant và khả năng chạy truy vấn quan trọng.
9. Đo thời gian hoàn tất và ghi nhận các thao tác thủ công, lỗi, dung lượng cùng thời điểm dữ liệu cuối cùng được phục hồi.
10. Hủy hoặc bảo vệ môi trường kiểm thử theo chính sách, tránh để bản sao dữ liệu nhạy cảm tồn tại không kiểm soát.

Kiểm thử cần xác nhận ít nhất ba điều: bản backup đọc được; MySQL khởi động và phục vụ truy vấn; dữ liệu đáp ứng mốc phục hồi dự kiến. Kiểm tra checksum của file chỉ xác nhận file không bị thay đổi ngoài dự kiến, không chứng minh backup có thể khởi động thành một database hợp lệ.

### RPO và RTO

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa tổ chức chấp nhận mất, thường đo bằng thời gian từ giao dịch cuối cùng có thể phục hồi tới lúc xảy ra sự cố.
- **RTO (Recovery Time Objective):** thời gian tối đa tổ chức chấp nhận để đưa dịch vụ trở lại hoạt động.

Lịch full/incremental và tần suất lưu binary log ảnh hưởng tới RPO. Kích thước dữ liệu, tốc độ đọc/ghi storage, băng thông, số incremental phải áp dụng, thời gian prepare và kiểm tra ứng dụng ảnh hưởng tới RTO. Hãy đo bằng restore drill thay vì ước tính chỉ từ tốc độ backup.

## 10. Tình huống chọn công cụ

Một hệ thống bán hàng chạy MySQL 8.x, dữ liệu InnoDB tăng nhanh, ứng dụng hoạt động liên tục và nhóm vận hành cần phục hồi instance lớn trong thời gian ngắn. Tổ chức đã sử dụng MySQL Enterprise và có quy trình hỗ trợ của Oracle.

Trong trường hợp này, MEB là ứng viên hợp lý để đánh giá trước vì phù hợp với hệ sinh thái và yêu cầu hỗ trợ hiện có. Nhóm cần thử full backup, incremental, mã hóa, chuyển backup sang kho lưu trữ độc lập và restore trên máy chủ tương đương production. Nếu MEB không phù hợp về chi phí hoặc yêu cầu kỹ thuật, nhóm có thể đánh giá XtraBackup sau khi xác nhận hỗ trợ chính xác phiên bản MySQL, engine và các tính năng đang dùng.

Một hệ thống khác có thể chạy MySQL trên storage array hỗ trợ snapshot nhất quán đa volume. Nhóm có thể dùng snapshot để tạo điểm chụp nhanh, nhưng cần chứng minh snapshot bao phủ cả data và redo, phối hợp với MySQL, sao chép snapshot ra vùng độc lập và thực hiện restore test. Nếu không chứng minh được tính nhất quán, snapshot không nên là phương án bảo vệ duy nhất.

Với một môi trường staging nhỏ có thể dừng MySQL mỗi đêm, cold backup sau shutdown sạch có thể đủ đơn giản và tiết kiệm. Nếu cần xuất một schema để chuyển sang phiên bản khác, logical dump có thể phù hợp hơn physical backup. Mỗi lựa chọn phải gắn với mục tiêu phục hồi và khả năng kiểm chứng cụ thể.

## 11. Checklist trước khi đưa vào production

- [ ] Đã xác định RPO, RTO, retention và các mốc PITR cần giữ.
- [ ] Đã kiểm tra phiên bản MySQL, storage engine, plugin, component và ma trận tương thích của công cụ.
- [ ] Đã kiểm kê `datadir`, external tablespace, redo/undo, binary log, keyring và các file cấu hình cần thiết.
- [ ] Quy trình backup bảo đảm tính nhất quán; không sao chép tùy tiện `datadir` đang hoạt động.
- [ ] Tài khoản backup có quyền tối thiểu và thông tin xác thực được quản lý an toàn.
- [ ] Backup được mã hóa, kiểm tra toàn vẹn và chuyển tới ít nhất một miền lỗi độc lập.
- [ ] Full/incremental được quản lý theo chuỗi phụ thuộc; binary log được lưu đủ lâu cho PITR.
- [ ] Có cảnh báo khi backup thất bại, quá hạn, thiếu dung lượng hoặc thiếu binary log.
- [ ] Đã thử restore trên host cô lập, gồm prepare/apply-log, copy-back, quyền file và khởi động MySQL.
- [ ] Đã xác minh dữ liệu nghiệp vụ, quyền truy cập và thời gian restore thực tế.
- [ ] Đã kiểm thử quy trình mất khóa mã hóa, thay host và khôi phục ở miền lỗi khác.

Một quy trình physical backup tốt phải tạo ra bản sao nhất quán, giữ đủ metadata và khóa cần thiết, bảo vệ bản sao khỏi sự cố tại máy chủ nguồn, đồng thời chứng minh được khả năng phục hồi bằng các bài kiểm thử định kỳ. Chọn MEB, XtraBackup, snapshot hay cold backup là quyết định dựa trên phiên bản, tính năng, downtime, hỗ trợ và RPO/RTO mà hệ thống cần đáp ứng.
