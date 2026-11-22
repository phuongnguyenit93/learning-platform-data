# Phân biệt hỏng dữ liệu với lỗi ứng dụng và giới hạn innodb_force_recovery

Khi ứng dụng báo “mất dữ liệu”, “đọc sai bản ghi” hoặc “database bị lỗi”, chưa thể kết luận InnoDB đã hỏng. Nguyên nhân có thể nằm ở truy vấn, transaction, cache, replica lag, mapping ORM, timezone, quyền truy cập hoặc dữ liệu đã bị ghi sai bởi một thao tác hợp lệ. Hỏng vật lý của tablespace, page hoặc index là một nhóm sự cố khác và cần quy trình bảo toàn dữ liệu riêng. Chẩn đoán nhầm có thể khiến người vận hành bật `innodb_force_recovery` không cần thiết, ghi đè dữ liệu còn cứu được hoặc làm mất cơ hội phục hồi từ backup.

Bài học này thuộc chương **Xử lý sự cố** của module **DATABASE_MYSQL**. Trong lộ trình làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành, khả năng phân biệt lỗi ứng dụng với hỏng dữ liệu giúp chọn đúng hướng xử lý. Trọng tâm là thu thập bằng chứng, xác minh phạm vi, bảo toàn bản sao, phục hồi từ backup và hiểu giới hạn của từng mức `innodb_force_recovery`.

## 1. Phân biệt ba nhóm sự cố

Không gom mọi vấn đề dữ liệu vào một khái niệm “corruption”. Trong thực tế cần tách ít nhất ba nhóm:

| Nhóm | Bản chất | Ví dụ |
|---|---|---|
| Lỗi ứng dụng hoặc truy vấn | Database hoạt động nhưng ứng dụng đọc/ghi sai hoặc diễn giải sai | Sai JOIN, thiếu tenant filter, cache cũ, mapping entity sai, transaction rollback |
| Hỏng dữ liệu logic | Cấu trúc vật lý có thể vẫn tốt nhưng giá trị đã bị ghi sai hoặc thiếu | UPDATE nhầm, import sai, duplicate nghiệp vụ, xóa nhầm, migration lỗi |
| Hỏng vật lý/ cấu trúc InnoDB | Page, index, tablespace hoặc metadata lưu trữ bị hỏng/không nhất quán | Checksum mismatch, page corruption, tablespace missing, lỗi đọc/ghi storage |

Ba nhóm có thể cùng tồn tại. Ví dụ một ứng dụng có bug ghi sai giá trị, sau đó replica đồng bộ thay đổi đó. Cả source và replica có thể nhất quán về mặt replication nhưng dữ liệu nghiệp vụ vẫn sai. Ngược lại, một page trên ổ đĩa của replica có thể hỏng vật lý trong khi source vẫn khỏe.

**Không dùng `innodb_force_recovery` để sửa lỗi truy vấn, dữ liệu nghiệp vụ bị ghi sai hoặc replica lag.** Tham số này chỉ phục vụ tình huống InnoDB không thể khởi động hoặc không thể đọc dữ liệu bình thường và cần cứu dữ liệu trong điều kiện khẩn cấp.

## 2. Dấu hiệu gợi ý lỗi ứng dụng

Các dấu hiệu sau thường cần kiểm tra code, SQL, transaction hoặc đường đọc trước khi nghi ngờ hỏng vật lý:

- Một endpoint trả kết quả sai nhưng truy vấn SQL trực tiếp trên primary cho kết quả đúng.
- Chỉ một tenant, user hoặc loại request gặp lỗi.
- Dữ liệu đúng trên primary nhưng cũ trên replica hoặc cache.
- Giá trị hiển thị lệch giờ do timezone hoặc chuyển đổi TIMESTAMP/DATETIME.
- ORM đọc sai cột do mapping, projection hoặc lazy loading.
- Truy vấn JOIN tạo bản ghi trùng hoặc lọc thiếu do điều kiện sai.
- Dữ liệu biến mất sau request lỗi vì transaction rollback.
- Lỗi chỉ xảy ra ở một phiên bản ứng dụng sau deploy hoặc migration.
- Một số request bị lỗi quyền, SQL mode hoặc kiểu chuyển đổi nhưng các truy vấn khác vẫn bình thường.

Hãy chạy một truy vấn đọc độc lập, có khóa chính và schema được xác định rõ, trên đúng instance mà ứng dụng đang dùng. So sánh kết quả raw SQL với log ứng dụng, request parameters, transaction boundary và dữ liệu cache. Nếu SQL trả đúng nhưng API trả sai, hướng điều tra nằm nhiều hơn ở ứng dụng hoặc tầng trung gian.

### Kiểm tra ứng dụng có đang đọc đúng instance không

~~~sql
SELECT
  @@hostname AS hostname,
  @@port AS port,
  @@server_uuid AS server_uuid,
  DATABASE() AS current_database,
  CONNECTION_ID() AS connection_id,
  VERSION() AS mysql_version;
~~~

Lấy kết quả trên chính connection mà request sử dụng nếu có thể. Ứng dụng có thể kết nối nhầm database, đọc replica, dùng endpoint Router khác hoặc chạy trên môi trường không đúng. Một truy vấn từ máy DBA tới primary không chứng minh request lỗi cũng đã đọc primary.

Kiểm tra connection pool, routing datasource, read/write splitting, transaction propagation và cấu hình replica. Với dữ liệu vừa ghi, nếu ứng dụng đọc ngay từ replica bất đồng bộ, có thể gặp read-after-write inconsistency dù dữ liệu không hỏng.

## 3. Dấu hiệu gợi ý dữ liệu logic bị ghi sai

Dữ liệu logic sai thường vẫn đọc được và các page/index vẫn hợp lệ. Ví dụ:

- Tổng đơn hàng không khớp tổng các dòng chi tiết.
- Một khách hàng có trạng thái nghiệp vụ không hợp lệ.
- Nhiều bản ghi có cùng external key dù nghiệp vụ yêu cầu duy nhất.
- Bản ghi tham chiếu tới entity không tồn tại do import bỏ qua foreign key checks.
- Một batch cập nhật sai phạm vi thời gian hoặc tenant.
- Dữ liệu bị xóa hoặc ghi đè bởi tài khoản hợp lệ.
- Migration chuyển kiểu dữ liệu làm tròn hoặc cắt giá trị.

Những lỗi này thường cần khôi phục logic từ audit log, backup, binary log/PITR hoặc dữ liệu nguồn. `innodb_force_recovery` không biết giá trị nào đúng theo nghiệp vụ và không thể tự hoàn tác một UPDATE hợp lệ về mặt SQL.

### Kiểm tra tính nhất quán nghiệp vụ

Ví dụ tìm đơn hàng có khách hàng không tồn tại:

~~~sql
SELECT o.id, o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
  ON c.id = o.customer_id
WHERE c.id IS NULL
LIMIT 100;
~~~

Đối chiếu tổng đơn hàng với chi tiết:

~~~sql
SELECT
  o.id,
  o.total_amount,
  SUM(oi.quantity * oi.unit_price) AS calculated_total
FROM orders AS o
JOIN order_items AS oi
  ON oi.order_id = o.id
GROUP BY o.id, o.total_amount
HAVING o.total_amount <> SUM(oi.quantity * oi.unit_price)
LIMIT 100;
~~~

Các truy vấn phải được điều chỉnh theo quy tắc làm tròn, thuế, phí vận chuyển, chiết khấu và trạng thái nghiệp vụ thực tế. Kết quả lệch là bằng chứng về vi phạm quy tắc cần điều tra, không tự động chứng minh page corruption.

## 4. Dấu hiệu gợi ý hỏng vật lý InnoDB

Nghi ngờ corruption vật lý khi có bằng chứng từ storage engine hoặc file hệ thống, chẳng hạn:

- Error log ghi nhận InnoDB page corruption, checksum mismatch hoặc page không đọc được.
- InnoDB báo lỗi khi truy cập một page/table cụ thể và lỗi lặp lại theo cùng page/space ID.
- Server crash hoặc assertion failure khi đọc một bảng/index cụ thể.
- Tablespace không tồn tại, không mở được hoặc metadata không khớp file.
- Lỗi I/O, filesystem, disk controller hoặc storage volume trùng thời điểm MySQL báo lỗi.
- Một bảng hoặc một phạm vi dữ liệu không thể đọc dù truy vấn và quyền đã được xác minh.
- InnoDB crash recovery liên tục thất bại khi khởi động.

Thông báo lỗi thường có chi tiết page number, space ID, index hoặc tablespace. Giữ nguyên các chi tiết đó để đối chiếu với log và file. Không kết luận chỉ từ một thông báo chung như “Got error from storage engine”; cần lấy error log đầy đủ và trạng thái InnoDB.

### Lấy bằng chứng từ MySQL

~~~sql
SHOW ENGINE INNODB STATUS\G
~~~

Lưu toàn bộ output, đặc biệt phần TRANSACTIONS, FILE I/O, LOG, BUFFER POOL và LATEST DETECTED DEADLOCK nếu có. Đây là snapshot tại thời điểm truy vấn; nó không thay thế error log hoặc lịch sử crash.

Lấy vị trí và cấu hình error log:

~~~sql
SHOW VARIABLES LIKE 'log_error';
SHOW VARIABLES LIKE 'innodb_page_size';
SHOW VARIABLES LIKE 'innodb_checksum_algorithm';
SHOW VARIABLES LIKE 'datadir';
~~~

Tên/khả năng đọc một số biến và đường dẫn phụ thuộc phiên bản, quyền và nền tảng triển khai. Dịch vụ managed MySQL có thể cung cấp error log qua console hoặc hệ thống log thay vì filesystem trực tiếp.

Đối chiếu error log với log hệ điều hành: lỗi I/O, reset thiết bị, filesystem remount read-only, hết dung lượng, lỗi volume, kernel error hoặc sự kiện bảo trì storage. Một lỗi page có thể bắt nguồn từ tầng lưu trữ, nên chỉ kiểm tra SQL là chưa đủ.

## 5. Bảo toàn bằng chứng trước khi sửa

Khi nghi ngờ hỏng vật lý, ưu tiên giữ lại trạng thái có thể điều tra và phục hồi.

- Ghi thời điểm, MySQL version, host, server_uuid, datadir và topology.
- Lưu error log, SHOW ENGINE INNODB STATUS, processlist và các truy vấn lỗi.
- Ghi rõ schema/table/index, page number, space ID và lần đầu xuất hiện.
- Kiểm tra backup, binary log, replica và snapshot storage có sẵn.
- Dừng hoặc hạn chế các workload ghi nếu tiếp tục ghi có thể làm tình trạng nặng hơn; phối hợp owner ứng dụng để xác định chế độ read-only hoặc dừng ghi.
- Nếu cần tạo bản sao vật lý, dùng snapshot nhất quán hoặc công cụ backup phù hợp. Không copy datadir đang hoạt động bằng thao tác file thông thường rồi coi đó là backup hợp lệ.
- Giữ nguyên bản gốc và làm việc trên bản sao khi thử các thao tác cứu dữ liệu.

**Không xóa hoặc tự thay thế** `ibdata1`, redo log, undo tablespace, file `.ibd`, file system tablespace hoặc metadata InnoDB. Không chạy `REPAIR TABLE` để sửa bảng InnoDB; lệnh này không phải cơ chế repair corruption của InnoDB. Không dùng công cụ dành cho MyISAM như `myisamchk` lên file InnoDB.

Không khởi động lại lặp đi lặp lại nếu mỗi lần startup đều làm tình trạng nặng hơn hoặc không có bản sao để thử. Trước restart, cần hiểu cấu hình, log và kế hoạch phục hồi.

## 6. Xác minh backup và replica trước khi dùng chúng

Backup là đường phục hồi ưu tiên khi có corruption. Kiểm tra:

- Thời điểm backup và phạm vi database/table.
- Backup có hoàn tất thành công và có checksum/manifest hợp lệ không.
- Có đủ binary log từ thời điểm backup đến điểm cần phục hồi không.
- Bản backup đã từng được restore thử chưa.
- Phiên bản MySQL, cấu hình encryption/keyring và plugin cần thiết có tương thích không.
- Có thể phục hồi vào instance sạch mà không ghi đè nguồn đang điều tra không.

Replica không mặc nhiên là backup. Nếu lỗi là câu lệnh DELETE/UPDATE sai hoặc dữ liệu logic bị ghi nhầm, replication có thể đã truyền thay đổi đó sang replica. Nếu corruption là lỗi vật lý riêng của một node, replica khác có thể còn tốt, nhưng phải xác minh log, khả năng đọc và tính nhất quán nghiệp vụ trước khi promote hoặc dump.

Với topology Group Replication/InnoDB Cluster, một thành viên ONLINE không phải bằng chứng tuyệt đối rằng mọi dữ liệu đều hợp lệ. Kiểm tra trạng thái thành viên, error log, replication apply, checksum/logical comparison và backup độc lập.

Nếu có backup tốt, ưu tiên restore vào instance sạch rồi áp dụng binary log đến điểm ngay trước sự cố bằng PITR. Chỉ chuyển traffic sau khi xác minh dữ liệu và ứng dụng.

## 7. Kiểm tra bảng một cách thận trọng

Nếu server vẫn chạy bình thường và không có dấu hiệu corruption nghiêm trọng, có thể kiểm tra metadata, schema và tính toàn vẹn logic trước:

~~~sql
SHOW CREATE TABLE customers;
SHOW INDEX FROM customers;

SELECT COUNT(*) FROM customers;
SELECT MIN(id), MAX(id) FROM customers;
~~~

Đối với InnoDB, `CHECK TABLE` có thể phát hiện một số vấn đề, nhưng không phải công cụ sửa chữa và không đảm bảo phát hiện mọi corruption. Trên bảng đã hỏng nặng, thao tác kiểm tra có thể tạo thêm tải hoặc làm server gặp lỗi khi đọc page. Chỉ chạy sau khi đã cân nhắc tác động, có backup/bản sao và dùng đúng phạm vi cần kiểm tra.

~~~sql
CHECK TABLE customers;
~~~

Nếu server đang crash, có lỗi I/O hoặc page corruption lặp lại, không chạy CHECK TABLE hàng loạt trên production như bước đầu tiên. Ưu tiên log, snapshot và thử nghiệm trên bản sao.

### innochecksum

`innochecksum` là tiện ích kiểm tra checksum page của file tablespace InnoDB. Nó được dùng trên file offline; không chạy kiểm tra/ghi sửa trên tablespace đang được MySQL mở và sử dụng. Dừng server hoặc làm việc trên một bản sao offline nhất quán theo quy trình phù hợp trước khi kiểm tra.

Ví dụ kiểm tra file bản sao:

~~~bash
innochecksum --strict-check /recovery-copy/appdb/orders.ibd
~~~

Đường dẫn chỉ là ví dụ; tham số có thể khác theo phiên bản MySQL. `innochecksum` giúp kiểm tra checksum/page ở cấp file, không xác minh quy tắc nghiệp vụ, không chứng minh toàn bộ index và quan hệ logic đúng, và không thay thế restore test. Không dùng tùy chọn ghi lại checksum để “sửa” một page chưa hiểu nguyên nhân.

## 8. innodb_force_recovery dùng để làm gì?

`innodb_force_recovery` là tham số khởi động InnoDB nhằm cho phép server khởi động trong một số tình trạng hỏng để người vận hành có thể đọc và xuất dữ liệu. Nó **không phải công cụ repair**, không tái tạo page bị hỏng và không bảo đảm database sau khi khởi động có thể tiếp tục phục vụ production.

Giá trị mặc định là 0, nghĩa là không ép recovery. Các mức từ 1 đến 6 bỏ qua hoặc vô hiệu hóa dần các bước xử lý InnoDB bình thường. Mức càng cao thì càng nhiều cơ chế recovery bị bỏ qua và nguy cơ dữ liệu không nhất quán càng lớn.

Chỉ cân nhắc tham số này khi:

- MySQL không thể khởi động bình thường do lỗi InnoDB đã được xác nhận.
- Không thể lấy dữ liệu cần thiết từ backup/replica tốt hơn.
- Mục tiêu là khởi động tạm để dump/export dữ liệu có thể đọc.
- Có kế hoạch tạo instance sạch và import dữ liệu đã cứu.

Không bật tham số này chỉ vì một truy vấn trả sai kết quả, một bảng có orphan row hoặc ứng dụng gặp timeout.

## 9. Sáu mức innodb_force_recovery

| Mức | Tên cơ chế thường dùng trong mã nguồn | Tác động chính | Rủi ro/giới hạn |
|---:|---|---|---|
| 0 | Normal | InnoDB chạy recovery bình thường | Chế độ vận hành chuẩn |
| 1 | IGNORE_CORRUPT | Cố gắng bỏ qua một số page/index record bị hỏng để cho phép đọc phần dữ liệu còn truy cập được | Kết quả dump có thể thiếu hàng hoặc bỏ qua phần hỏng |
| 2 | NO_BACKGROUND | Ngăn master thread và purge thread chạy | Không thực hiện các công việc nền bình thường; chỉ dùng để cứu dữ liệu |
| 3 | NO_TRX_UNDO | Không thực hiện rollback transaction sau crash recovery | Có thể để lại thay đổi chưa commit trong dữ liệu nhìn thấy |
| 4 | NO_IBUF_MERGE | Ngăn insert buffer/change buffer merge và không tính toán thống kê bảng theo cách bình thường | Có nguy cơ làm hỏng dữ liệu lâu dài; InnoDB chuyển sang read-only |
| 5 | NO_UNDO_LOG_SCAN | Không quét undo log khi khởi động; transaction chưa hoàn tất được xem như đã commit | Dữ liệu có thể không nhất quán; InnoDB read-only |
| 6 | NO_LOG_REDO | Không áp dụng redo log roll-forward | Page có thể lỗi thời hoặc cấu trúc chưa hoàn tất; nguy cơ hỏng thêm rất cao; InnoDB read-only |

Các mức 4, 5 và 6 đặt InnoDB ở chế độ chỉ đọc. Ở các mức thấp hơn, một số thao tác ghi có thể vẫn được cho phép theo hành vi phiên bản, nhưng **không được sử dụng điều đó để tiếp tục vận hành hoặc sửa dữ liệu trên instance cứu hộ**. Mục tiêu là đọc và trích xuất dữ liệu tối đa có thể, sau đó dựng lại instance sạch.

### Cách tăng mức

Bắt đầu ở mức thấp nhất có thể, thường là 1 nếu recovery bình thường không thể khởi động. Nếu server vẫn không khởi động hoặc không thể đọc dữ liệu cần cứu, tăng từng mức một và đánh giá log sau mỗi lần.

Không nhảy thẳng lên 6. Mức cao có thể bỏ qua undo hoặc redo cần thiết để đưa dữ liệu về trạng thái nhất quán. Khi đã dùng mức 3 trở lên, đặc biệt 5/6, dữ liệu đọc được không nhất thiết phản ánh một trạng thái transaction hợp lệ như trước crash.

`innodb_force_recovery` là biến cấu hình khởi động; cách thay đổi và restart phụ thuộc cách triển khai MySQL. Thực hiện trên bản sao datadir hoặc môi trường phục hồi riêng khi có thể. Tham khảo tài liệu đúng phiên bản server vì các giới hạn và hành vi có thể thay đổi giữa các nhánh.

## 10. Quy trình cứu dữ liệu bằng innodb_force_recovery

### Bước 1 — Ưu tiên backup và bản sao tốt

Xác minh backup, replica và snapshot trước. Nếu có bản backup hợp lệ, restore trên instance sạch và dùng PITR nếu cần. Chỉ dùng force recovery khi đường phục hồi bình thường không cung cấp dữ liệu cần thiết.

### Bước 2 — Bảo toàn datadir gốc

Dừng MySQL theo quy trình nếu cần tạo bản sao vật lý. Dùng snapshot storage nhất quán hoặc công cụ backup phù hợp; giữ nguyên bản gốc và metadata cần thiết như file cấu hình, keyring, redo/undo, system tablespace và file tablespace. Không di chuyển riêng một vài file InnoDB rồi khởi động bằng một tổ hợp file không nhất quán.

### Bước 3 — Khởi động bản sao với mức thấp nhất cần thiết

Đặt `innodb_force_recovery=1` trong cấu hình phục hồi hoặc tham số khởi động phù hợp. Theo dõi error log. Nếu server khởi động, không bật ứng dụng production vào instance này và không cho workload ghi.

Nếu không khởi động được, xem log để xác định bước recovery tiếp theo. Chỉ tăng lên 2, rồi 3, 4, 5 hoặc 6 khi mức trước không đủ và có lý do cụ thể. Mỗi lần tăng phải ghi lại mức, lỗi startup và kết quả đọc dữ liệu.

### Bước 4 — Dump các bảng còn đọc được

Ưu tiên dump từng database hoặc từng bảng cần thiết. Ví dụ:

~~~bash
mysqldump --host=recovery-db --user=salvage_user \
  --quick --skip-lock-tables appdb customers > customers.sql
~~~

Đây là ví dụ lệnh; điều chỉnh quyền, socket/TLS, tên database/table và tùy chọn theo môi trường. Dùng tài khoản chỉ có quyền đọc cần thiết. Không đưa mật khẩu vào command line hoặc shell history; dùng cơ chế xác thực an toàn phù hợp.

Nếu một bảng lỗi khi dump toàn bộ, thử chia dữ liệu theo primary key thành các khoảng nhỏ để xác định phần có thể đọc. Lưu ý một page hỏng có thể làm mọi truy vấn đi qua page đó thất bại. Không tự ý bỏ qua các hàng lỗi mà không ghi nhận phạm vi và tác động nghiệp vụ.

Không dùng `--force` như cách che lỗi. Tùy chọn đó có thể tiếp tục dump sau một số lỗi SQL, nhưng file xuất ra có thể thiếu đối tượng hoặc dữ liệu. Nếu dùng để cứu phần đọc được, phải ghi log đầy đủ các lỗi và lập danh sách phần không dump được.

### Bước 5 — Dựng instance sạch

Khởi tạo một datadir mới với phiên bản MySQL tương thích, cấu hình chuẩn và keyring/encryption material cần thiết. Không dùng datadir đang ở force recovery làm instance production. Tạo schema bằng migration đã được kiểm chứng hoặc backup logic, rồi import dữ liệu dump.

Kiểm tra charset/collation, SQL mode, timezone, engine, index, constraint, user/role, stored program và quyền. Không giả định dump logic chứa mọi cấu hình server hoặc mọi metadata vận hành cần thiết.

### Bước 6 — Xác minh trước khi chuyển traffic

Đối chiếu số hàng, min/max khóa, aggregate, quan hệ foreign key và các quy tắc nghiệp vụ. Chạy test ứng dụng, query plan quan trọng, kiểm tra error log và replication/backup trên instance sạch. Nếu một số page hoặc hàng không thể cứu, ghi rõ khoảng dữ liệu bị thiếu và quyết định nghiệp vụ trước khi mở traffic.

## 11. Vì sao không tiếp tục chạy production ở force recovery?

Force recovery thay đổi các bước InnoDB thực hiện để phục hồi transaction và page. Khi bỏ qua undo, purge, change buffer merge hoặc redo, trạng thái nhìn thấy có thể không còn phản ánh một database đã recovery đầy đủ.

Các rủi ro gồm:

- Dữ liệu chưa commit có thể xuất hiện như thể đã commit ở một số mức recovery.
- Redo chưa được áp dụng có thể khiến page cũ hoặc cấu trúc chưa hoàn tất.
- Một số thao tác ghi bị cấm ở các mức cao; ở mức thấp, ghi vẫn có thể làm tình trạng tệ hơn.
- Index hoặc page bị bỏ qua có thể làm truy vấn trả thiếu hàng.
- Một lần dump thành công không chứng minh mọi bảng và mọi hàng đều đã được cứu.
- Các thay đổi mới trên instance cứu hộ sẽ không có đường phục hồi đáng tin cậy.

Vì vậy, coi instance force recovery là nguồn đọc tạm thời để cứu dữ liệu. Không đưa nó trở lại luồng ghi, không chạy migration và không dùng nó làm primary mới.

## 12. Các thao tác không nên làm

| Thao tác | Vì sao nguy hiểm | Hướng đúng |
|---|---|---|
| Bật force recovery 6 ngay lập tức | Bỏ qua redo, có thể để page lỗi thời và tăng rủi ro | Bắt đầu mức thấp, tăng từng bước trên bản sao |
| Ghi dữ liệu lên instance force recovery | Có thể tạo trạng thái không nhất quán hoặc không được hỗ trợ | Chỉ đọc/dump, dựng instance sạch để ghi |
| Xóa ibdata1 hoặc redo/undo file | Có thể phá cấu trúc InnoDB và làm mất dữ liệu | Giữ nguyên datadir, phục hồi từ backup/snapshot |
| Chạy REPAIR TABLE trên InnoDB | Không phải cơ chế repair InnoDB | Restore hoặc salvage rồi rebuild |
| Dùng myisamchk cho .ibd | Công cụ sai storage engine | Dùng công cụ phù hợp với InnoDB và chỉ trên bản sao/offline |
| Chạy CHECK TABLE hàng loạt trên server đang lỗi | Tăng tải và có thể kích hoạt lỗi đọc page | Bảo toàn log/snapshot, thử trên bản sao |
| Promote replica chưa xác minh | Có thể promote dữ liệu đã bị lỗi logic hoặc vật lý | Kiểm tra log, checksum và nghiệp vụ trước |
| Dùng dump một phần như backup hoàn chỉnh | Có thể thiếu hàng/bảng mà không nhận ra | Ghi rõ lỗi và đối chiếu phạm vi dump |

## 13. Xác minh dữ liệu sau khi cứu

Sau khi import vào instance sạch, cần xác minh cả cấu trúc và nội dung.

### Kiểm tra số lượng và phạm vi khóa

~~~sql
SELECT
  COUNT(*) AS row_count,
  MIN(id) AS min_id,
  MAX(id) AS max_id
FROM orders;
~~~

Đối chiếu với backup, nguồn dữ liệu khác hoặc snapshot trước sự cố. Số lượng bằng nhau chưa chứng minh cùng tập bản ghi; nếu có khóa nghiệp vụ, so sánh theo key hoặc checksum theo batch.

### Kiểm tra constraint

~~~sql
SELECT
  TABLE_NAME,
  CONSTRAINT_NAME,
  CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
~~~

Kiểm tra foreign key orphan, unique duplicate và các cột bắt buộc. Nếu constraint bị bỏ trong quá trình salvage/import, phải xác minh dữ liệu trước khi tạo lại.

### Kiểm tra aggregate nghiệp vụ

~~~sql
SELECT
  status,
  COUNT(*) AS order_count,
  SUM(total_amount) AS total_amount
FROM orders
GROUP BY status
ORDER BY status;
~~~

Đối chiếu với báo cáo trước sự cố, backup hoặc nguồn nghiệp vụ. Với số tiền, dùng DECIMAL và quy tắc làm tròn giống ứng dụng. Với thời gian, thống nhất timezone và phạm vi snapshot.

### Kiểm tra ứng dụng

Chạy smoke test trên instance sạch với tài khoản và quyền gần production. Kiểm tra đọc/ghi, transaction rollback, generated keys, stored procedures, trigger, event và các truy vấn quan trọng. Chỉ mở traffic sau khi owner nghiệp vụ xác nhận dữ liệu trong phạm vi chấp nhận được.

## 14. Khi dữ liệu sai nhưng InnoDB vẫn khỏe

Nếu server chạy ổn định, error log không có dấu hiệu page corruption và truy vấn đọc được, tập trung vào logic dữ liệu:

1. Xác định thời điểm bản ghi bắt đầu sai bằng audit log, binlog hoặc lịch sử ứng dụng.
2. Tìm transaction hoặc batch đã ghi dữ liệu.
3. So sánh backup trước sự cố với trạng thái hiện tại.
4. Dùng PITR để dựng một bản sao ở thời điểm trước thao tác sai.
5. Trích xuất các hàng cần khôi phục từ bản sao đó.
6. Áp dụng bù trừ trên production bằng transaction có kiểm tra, không ghi đè toàn bảng nếu chỉ một tập hàng sai.
7. Đối chiếu số hàng và tổng nghiệp vụ sau sửa.

Không bật `innodb_force_recovery` cho một DELETE nhầm hoặc một migration sai nếu InnoDB vẫn hoạt động bình thường. Force recovery không hiểu lịch sử nghiệp vụ và có thể làm mất khả năng ghi của instance mà không giúp khôi phục giá trị cũ.

## 15. Runbook quyết định hướng xử lý

~~~text
Ứng dụng báo dữ liệu sai hoặc MySQL lỗi
                 |
                 v
       Lưu lỗi, timestamp, host,
       query và phạm vi ảnh hưởng
                 |
                 v
     SQL trực tiếp trên đúng instance
     có tái hiện lỗi không?
          /             \
        Không             Có
         |                |
         v                v
  Điều tra app, cache,   Error log có dấu hiệu
  routing, replica,      InnoDB page/tablespace
  transaction, ORM      hoặc I/O corruption?
                          /       \
                        Không      Có
                         |          |
                         v          v
                 Kiểm tra logic,   Bảo toàn snapshot,
                 schema, DML,      backup, error log
                 constraint, PITR       |
                                        v
                              MySQL khởi động bình thường?
                                  /             \
                                Có               Không
                                 |                |
                                 v                v
                         Restore/repair logic   Thử backup/replica
                         từ backup/PITR trên    tốt trước
                         instance sạch              |
                                                     v
                                          Không có đường tốt hơn?
                                                     |
                                                     v
                                      Force recovery trên bản sao,
                                      tăng từ mức thấp, chỉ dump
                                                     |
                                                     v
                                         Rebuild instance sạch,
                                         validate và mới cutover
~~~

Sơ đồ là hướng quyết định tổng quát. Thực tế có thể cần phối hợp DBA, storage/platform team và owner ứng dụng; không bỏ qua quy trình incident hoặc quyền phê duyệt thao tác phá hủy.

## 16. Checklist sự cố

**Phân loại ban đầu**

- [ ] Ghi lại MySQL version, host, server_uuid, schema/table và timestamp.
- [ ] Xác minh request đang đọc đúng instance và database.
- [ ] Tái hiện bằng truy vấn SQL độc lập, chỉ đọc.
- [ ] So sánh primary, replica, cache và dữ liệu nguồn.
- [ ] Phân biệt lỗi ứng dụng, lỗi logic dữ liệu và lỗi vật lý InnoDB.

**Bảo toàn bằng chứng**

- [ ] Lưu error log, SHOW ENGINE INNODB STATUS và SQL error đầy đủ.
- [ ] Ghi page/space ID, tablespace, index và file liên quan nếu có.
- [ ] Kiểm tra disk, filesystem, storage volume và log hệ điều hành.
- [ ] Xác minh backup, binary log, PITR và replica.
- [ ] Giữ bản gốc và tạo snapshot/bản sao nhất quán trước thử nghiệm.

**Nếu phải dùng innodb_force_recovery**

- [ ] Chỉ dùng khi recovery bình thường không thể khởi động/đọc dữ liệu cần cứu.
- [ ] Thử trên bản sao hoặc môi trường phục hồi riêng.
- [ ] Bắt đầu từ mức thấp nhất và tăng từng bước.
- [ ] Không dùng instance đó để phục vụ production hoặc tiếp tục ghi.
- [ ] Dump từng bảng/phạm vi, lưu đầy đủ lỗi và danh sách dữ liệu thiếu.
- [ ] Dựng datadir/instance sạch để import.

**Trước khi mở traffic**

- [ ] Đối chiếu row count, key range, aggregate và checksum theo batch.
- [ ] Kiểm tra unique, foreign key, NOT NULL và dữ liệu nghiệp vụ.
- [ ] Xác minh schema, index, routine, trigger, event và quyền.
- [ ] Chạy smoke test và truy vấn quan trọng.
- [ ] Kiểm tra backup mới và khả năng restore.
- [ ] Ghi rõ phần dữ liệu không cứu được và quyết định nghiệp vụ.

## 17. Ghi nhớ

- Dữ liệu trả sai không đồng nghĩa InnoDB corruption; kiểm tra ứng dụng, SQL, cache, replica và transaction trước.
- Dữ liệu logic bị ghi sai cần audit, backup hoặc PITR; force recovery không sửa được quy tắc nghiệp vụ.
- Page corruption, checksum mismatch, tablespace error và I/O failure là dấu hiệu cần điều tra vật lý.
- Bảo toàn error log, InnoDB status, datadir snapshot và backup trước khi thử thao tác phục hồi.
- Replica không tự động là backup; thay đổi logic sai có thể đã được replication truyền đi.
- `innodb_force_recovery` là chế độ khẩn cấp để khởi động và cứu xuất dữ liệu, không phải repair tool.
- Tăng mức từ thấp lên cao từng bước; mức 4–6 đưa InnoDB vào read-only.
- Mức 3 trở lên có thể làm trạng thái transaction không còn nhất quán; mức 5/6 bỏ qua các bước recovery quan trọng.
- Không ghi dữ liệu, chạy migration hoặc đưa traffic production vào instance force recovery.
- Dựng instance sạch, import dữ liệu cứu được, xác minh nghiệp vụ và backup trước cutover.

Khi phân biệt rõ lỗi ứng dụng, dữ liệu logic và hỏng vật lý, nhóm vận hành có thể chọn đúng công cụ. Chỉ dùng `innodb_force_recovery` như biện pháp cuối để đọc và cứu dữ liệu khi InnoDB không thể hoạt động bình thường; phục hồi dịch vụ phải kết thúc trên một instance sạch đã được kiểm chứng.

## Tài liệu tham khảo

- [MySQL 8.0 Reference Manual: Forcing InnoDB Recovery](https://dev.mysql.com/doc/refman/8.0/en/forcing-innodb-recovery.html)
- [MySQL 8.0 Reference Manual: InnoDB Recovery](https://dev.mysql.com/doc/refman/8.0/en/innodb-recovery.html)
- [MySQL 8.0 Reference Manual: innochecksum — Offline InnoDB File Checksum Utility](https://dev.mysql.com/doc/refman/8.0/en/innochecksum.html)
- [MySQL 8.0 Reference Manual: CHECK TABLE Statement](https://dev.mysql.com/doc/refman/8.0/en/check-table.html)
- [MySQL 8.0 Reference Manual: mysqldump](https://dev.mysql.com/doc/refman/8.0/en/mysqldump.html)
- [MySQL 8.0 Reference Manual: Point-in-Time Recovery](https://dev.mysql.com/doc/refman/8.0/en/point-in-time-recovery.html)

