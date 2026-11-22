# Khôi phục bảng lớn, kiểm tra ràng buộc và số liệu nghiệp vụ

Khôi phục một bảng lớn trong MySQL đòi hỏi nhiều hơn việc nạp lại một tệp SQL. Bảng có thể chứa hàng triệu hoặc hàng tỷ dòng, có khóa ngoại đến các bảng khác, chỉ mục duy nhất, ràng buộc CHECK, trigger và dữ liệu đang tiếp tục thay đổi trong hệ thống. Một lần phục hồi chỉ được xem là thành công khi dữ liệu đã được nạp đầy đủ, cấu trúc và các quan hệ được bảo toàn, số liệu nghiệp vụ khớp với mốc phục hồi đã chọn và ứng dụng có thể tiếp tục hoạt động an toàn.

Bài học này thuộc nội dung làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa, truy vấn, index và transaction đến sao lưu, phục hồi và xử lý vấn đề vận hành. Trọng tâm là quy trình khôi phục một bảng lớn, cách kiểm tra ràng buộc và cách đối soát dữ liệu theo góc nhìn nghiệp vụ trước khi đưa bảng trở lại phục vụ ứng dụng.

## 1. Xác định đúng mục tiêu phục hồi

Trước khi chạy lệnh, cần làm rõ bảng cần phục hồi, mốc dữ liệu cần lấy và ảnh hưởng đến ứng dụng. Có một số tình huống khác nhau:

| Tình huống | Mục tiêu | Hướng xử lý thường dùng |
|---|---|---|
| Một bảng bị xóa nhầm | Khôi phục bảng tại thời điểm trước khi xóa | Phục hồi bản sao lưu vào môi trường tạm, áp dụng binary log đến ngay trước thao tác xóa, sau đó trích xuất bảng |
| Một số dòng bị sửa hoặc xóa sai | Khôi phục các dòng bị ảnh hưởng | Phục hồi đến thời điểm phù hợp, xác định khóa chính của các dòng cần lấy và đối chiếu trước khi cập nhật |
| Bảng bị lỗi dữ liệu sau triển khai | Khôi phục trạng thái dữ liệu đúng | Dùng bản sao lưu hoặc nguồn dữ liệu đáng tin cậy, kiểm tra thay đổi phát sinh kể từ thời điểm sao lưu |
| Cần chuyển bảng sang máy chủ khác | Chuyển cấu trúc và dữ liệu sang đích | Xuất bảng, nạp vào bảng staging, kiểm tra tương thích rồi mới chuyển ứng dụng |
| Cần khôi phục bảng rất lớn | Đưa dữ liệu trở lại với thời gian gián đoạn có kiểm soát | Phục hồi ở staging, nạp theo lô hoặc song song có giới hạn, đối soát theo từng phần và lập kế hoạch cutover |

Ba thông tin cần xác định rõ là:

- **Recovery point:** dữ liệu phải đúng tại thời điểm nào? Bản sao lưu gần nhất có thể chưa đủ nếu sự cố xảy ra sau đó.
- **Recovery scope:** cần phục hồi toàn bộ bảng, một khoảng thời gian, hay một tập dòng được xác định bằng khóa?
- **Write boundary:** trong khi phục hồi, ứng dụng còn được ghi vào bảng hay phải tạm dừng ghi để tránh mất các thay đổi mới?

Không nên bắt đầu nạp dữ liệu trước khi biết bản sao lưu được tạo từ đâu, có nhất quán hay không và binary log nào còn sẵn để đưa dữ liệu đến mốc cần thiết. Nếu chưa xác định được nguồn dữ liệu đáng tin cậy hoặc mốc phục hồi, hãy giữ nguyên hiện trạng và thu thập thông tin trước.

## 2. Chuẩn bị môi trường và nguồn phục hồi

### 2.1. Giữ lại bằng chứng và dữ liệu hiện tại

Khi phát hiện bảng có vấn đề, hạn chế các thao tác có thể ghi đè thêm dữ liệu. Ghi lại thời điểm phát hiện, tài khoản thực hiện thay đổi nếu biết, câu lệnh hoặc phiên triển khai liên quan và phạm vi ứng dụng bị ảnh hưởng. Nếu có thể, chụp lại trạng thái hiện tại bằng một bản sao lưu hoặc bản xuất riêng trước khi sửa chữa.

Không ghi đè trực tiếp bảng đang gặp sự cố chỉ vì đã tìm thấy một bản backup. Bảng hiện tại có thể chứa các giao dịch hợp lệ phát sinh sau thời điểm backup. Giữ một bản sao phục vụ điều tra và so sánh giúp giảm nguy cơ mất các thay đổi đó.

### 2.2. Chọn nguồn dữ liệu

Nguồn phục hồi thường thuộc một trong các loại sau:

- **Logical backup:** dữ liệu được xuất thành câu lệnh SQL hoặc định dạng logic. Có thể phục hồi riêng bảng, dễ chuyển giữa các máy chủ tương thích, nhưng thời gian xuất và nạp có thể dài với bảng rất lớn.
- **Physical backup:** bản sao các tệp dữ liệu của MySQL hoặc InnoDB. Phục hồi thường nhanh hơn với toàn bộ instance lớn, nhưng không đồng nghĩa có thể lấy riêng một bảng một cách trực tiếp. Thông thường cần phục hồi instance vào máy tạm rồi trích xuất bảng.
- **Binary log:** ghi lại các sự kiện thay đổi dữ liệu sau mốc backup. Có thể áp dụng các sự kiện đến một thời điểm hoặc vị trí xác định để thực hiện point-in-time recovery (PITR).
- **Nguồn dữ liệu nghiệp vụ:** bản xuất từ hệ thống nguồn, kho dữ liệu hoặc bản ghi đối soát. Nguồn này có thể hỗ trợ xác nhận số liệu nhưng cần kiểm tra tính đầy đủ, thời điểm và quy tắc chuyển đổi.

Với PITR, cần có bản backup nền và binary log liên tục từ vị trí ghi nhận trong metadata của backup đến thời điểm đích. Nếu thiếu một đoạn log, không thể giả định rằng các log còn lại đủ để tái tạo trạng thái chính xác.

### 2.3. Kiểm tra tương thích

Trước khi phục hồi vào staging, kiểm tra ít nhất:

- Phiên bản MySQL và storage engine của bảng.
- Bộ ký tự, collation, kiểu dữ liệu, độ chính xác của DECIMAL và múi giờ được ứng dụng sử dụng.
- Cấu trúc khóa chính, unique index, khóa ngoại, CHECK constraint, generated column và partition.
- Trigger, view hoặc tác vụ ứng dụng có phụ thuộc vào bảng.
- Các plugin, mã hóa tablespace, cấu hình TLS hoặc tính năng đặc thù của môi trường nguồn nếu có.

Đối chiếu định nghĩa bảng bằng:

~~~sql
SHOW CREATE TABLE app_db.orders;
~~~

Đừng chỉ so sánh tên và số lượng cột. Khác biệt về **UNSIGNED**, **NULL**, giá trị mặc định, collation, thứ tự cột trong index hoặc biểu thức generated column đều có thể làm dữ liệu được diễn giải khác đi hoặc khiến ứng dụng hoạt động sai.

### 2.4. Ước lượng tài nguyên

Với bảng lớn, dung lượng tệp backup không bằng dung lượng cần có khi phục hồi. Cần tính đến:

- Dung lượng cho bản staging, bản hiện tại và bản lưu giữ sau cutover.
- Dung lượng cho chỉ mục phụ, temporary file, redo log, undo log và binary log phát sinh trong lúc nạp.
- I/O đĩa, tốc độ mạng và số luồng nạp đồng thời.
- Dung lượng buffer pool và ảnh hưởng đến các workload khác.
- Độ trễ replication nếu máy phục hồi đang là nguồn hoặc đích của replica.

Hãy đo thử trên dữ liệu đại diện hoặc môi trường tương đương. Một lần nạp chạy nhanh trên máy thử nhỏ không đủ để dự đoán thời gian phục hồi của bảng production.

## 3. Phục hồi bảng vào môi trường staging

Staging là nơi kiểm tra dữ liệu trước khi thay thế bảng đang phục vụ ứng dụng. Có thể dùng một MySQL instance riêng hoặc một schema tạm được cô lập phù hợp. Môi trường này nên tương thích với phiên bản, cấu hình và cấu trúc của đích.

### 3.1. Xuất một bảng bằng mysqldump

Nếu nguồn là một MySQL instance đang hoạt động và bảng dùng InnoDB, có thể tạo logical dump riêng:

~~~bash
mysqldump --single-transaction --quick --hex-blob app_db orders > orders.sql
~~~

Ý nghĩa các tùy chọn:

- **--single-transaction** tạo consistent snapshot cho các bảng transactional như InnoDB mà không khóa toàn bộ bảng trong suốt quá trình dump.
- **--quick** đọc và xuất từng dòng thay vì giữ toàn bộ kết quả trong bộ nhớ client.
- **--hex-blob** biểu diễn dữ liệu nhị phân theo dạng an toàn cho quá trình xuất và nhập.

**--single-transaction** không bảo đảm snapshot nhất quán cho bảng dùng engine không hỗ trợ transaction như MyISAM. Trong lúc dump, cũng cần tránh các thao tác DDL như ALTER, DROP hoặc RENAME trên bảng được xuất vì chúng có thể làm quá trình dump lỗi hoặc mất tính nhất quán. Nếu cần dump nhiều bảng có quan hệ, phải xem xét cách tạo snapshot và các bảng có cùng mốc dữ liệu.

Với bảng rất lớn, tệp dump có thể chiếm nhiều dung lượng và thời gian. Kiểm tra dung lượng đĩa đích, theo dõi tiến trình và bảo vệ tệp backup theo chính sách dữ liệu của hệ thống.

### 3.2. Phục hồi dump vào schema tạm

Tạo schema staging với charset và collation phù hợp:

~~~sql
CREATE DATABASE restore_stage
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

Tên collation trên là ví dụ cho MySQL 8.0; hãy dùng charset và collation thực tế của hệ thống nguồn. Nạp dump vào schema tạm:

~~~bash
mysql --host=restore-db --user=restore_operator --password restore_stage < orders.sql
~~~

Tùy chọn **--password** không kèm giá trị yêu cầu client hỏi mật khẩu tương tác, tránh ghi bí mật trực tiếp vào lịch sử lệnh. Tài khoản phục hồi chỉ nên có quyền cần thiết trên môi trường staging.

Sau khi nạp, xác nhận bảng xuất hiện và cấu trúc đúng:

~~~sql
SHOW TABLES FROM restore_stage LIKE 'orders';
SHOW CREATE TABLE restore_stage.orders;
~~~

Nếu nguồn là physical backup, quy trình thường là phục hồi bản backup vào một instance tạm theo đúng hướng dẫn của công cụ backup, khởi động và kiểm tra instance đó, sau đó dùng logical dump để trích xuất bảng cần thiết. Không sao chép tùy tiện một tệp .ibd vào thư mục dữ liệu đang chạy và kỳ vọng MySQL tự nhận bảng; InnoDB có metadata, dictionary, tablespace và điều kiện tương thích cần được xử lý đúng.

### 3.3. Phục hồi đến đúng thời điểm bằng binary log

Khi bảng bị thay đổi sai sau thời điểm backup, có thể cần PITR. Quy trình tổng quát:

1. Phục hồi bản backup nền vào instance tạm.
2. Đọc metadata của backup để xác định binary log file/position hoặc GTID bắt đầu.
3. Áp dụng binary log liên tục đến ngay trước giao dịch gây lỗi hoặc đến mốc phục hồi đã được phê duyệt.
4. Kiểm tra dữ liệu trên instance tạm, sau đó mới trích xuất bảng.

Ví dụ minh họa việc áp dụng log theo vị trí bắt đầu và thời điểm dừng:

~~~bash
mysqlbinlog \
  --start-position=12345 \
  --stop-datetime="2026-11-19 10:30:00" \
  binlog.000123 binlog.000124 \
  | mysql --host=restore-db --user=restore_operator --password
~~~

Các giá trị file, vị trí và thời điểm trong ví dụ chỉ là chỗ giữ chỗ. Phải thay bằng metadata thực tế của backup và mốc đã xác nhận. Vị trí bắt đầu phải khớp với trạng thái backup; mốc dừng phải nằm trước giao dịch gây hỏng nếu mục tiêu là khôi phục trạng thái trước giao dịch đó. Khi có thể, dùng file/position hoặc GTID đã được ghi nhận để xác định ranh giới chính xác; thời gian chỉ nên dùng khi đã hiểu múi giờ và thời điểm sự kiện trong log.

Không áp dụng binary log trực tiếp lên production chỉ để thử một mốc phục hồi. Binary log có thể chứa thay đổi của nhiều bảng và nhiều schema; hãy áp dụng trên instance tạm, kiểm tra kết quả rồi mới trích xuất phạm vi cần khôi phục.

## 4. Nạp dữ liệu lớn theo cách có kiểm soát

Một lệnh import duy nhất có thể phù hợp với bảng vừa phải, nhưng bảng lớn thường cần quản lý tốc độ, bộ nhớ, transaction và khả năng tiếp tục khi có lỗi.

### 4.1. Nạp theo lô dựa trên khóa chính

Nếu dữ liệu được xuất thành các tập dòng hoặc tệp theo khoảng khóa, hãy chia theo khóa chính ổn định. Ví dụ với **orders.id**:

~~~sql
SELECT *
FROM restore_stage.orders
WHERE id >= 1 AND id < 100001
ORDER BY id;
~~~

Lô tiếp theo dùng khoảng [100001, 200001) và cứ tiếp tục như vậy. Ranh giới không chồng lấn và không bỏ sót. Phân đoạn theo khóa chính thường dễ tiếp tục hơn phân trang bằng LIMIT offset, count, vì offset lớn buộc máy chủ phải đọc và bỏ qua nhiều dòng.

Khi nạp theo lô vào bảng staging, dùng danh sách cột tường minh:

~~~sql
INSERT INTO app_db.orders_restore
  (id, customer_id, status, total_amount, created_at)
SELECT
  id, customer_id, status, total_amount, created_at
FROM restore_stage.orders
WHERE id >= 1 AND id < 100001
ORDER BY id;
~~~

Danh sách cột giúp tránh phụ thuộc vào thứ tự cột và làm rõ cách xử lý các cột generated hoặc có giá trị mặc định. Ví dụ trên giả định hai bảng có cấu trúc tương thích và bảng đích đã được tạo sẵn. Cần xác nhận kiểu dữ liệu, charset, collation và quy tắc chuyển đổi trước khi chạy.

### 4.2. Chọn kích thước transaction

Không nên mặc định nạp toàn bộ bảng trong một transaction duy nhất. Transaction quá lớn có thể tạo nhiều undo, giữ row lock lâu, làm tăng thời gian rollback và gây áp lực lên redo log hoặc replication. Transaction quá nhỏ lại làm tăng chi phí commit và có thể giảm thông lượng.

Hãy chọn kích thước lô dựa trên thời gian commit, I/O, dung lượng log và tải hệ thống. Sau mỗi lô:

1. Xác nhận câu lệnh thành công và số dòng được xử lý.
2. Ghi nhận khoảng khóa đã hoàn thành vào nhật ký tiến trình.
3. Kiểm tra số dòng hoặc tổng hợp của lô.
4. Chỉ đánh dấu lô hoàn tất sau khi transaction đã commit.

Nếu tiến trình bị gián đoạn, dùng nhật ký để tiếp tục từ khoảng chưa hoàn tất. Không chạy lại mù quáng một lô có thể đã commit. **INSERT IGNORE** hoặc **ON DUPLICATE KEY UPDATE** có thể che giấu xung đột khóa hoặc ghi đè dữ liệu ngoài ý muốn; chỉ dùng khi chính sách phục hồi định nghĩa rõ cách xử lý từng trường hợp.

### 4.3. Tổ chức index và ràng buộc

Chỉ mục giúp truy vấn và kiểm tra tính duy nhất, nhưng việc duy trì nhiều secondary index trong lúc nạp hàng triệu dòng có thể làm tăng chi phí ghi. Với bảng staging, có thể cân nhắc tạo một số secondary index sau khi nạp nếu quy trình kiểm tra và yêu cầu toàn vẹn cho phép. Tuy nhiên:

- Khóa chính và unique constraint có vai trò bảo vệ tính duy nhất; không bỏ qua xung đột chỉ để tăng tốc.
- Nếu thêm unique index sau khi nạp, phải kiểm tra trùng lặp trước và xử lý dữ liệu trùng theo quy tắc nghiệp vụ.
- Không xóa khóa ngoại hoặc CHECK constraint trên bảng production để tăng tốc phục hồi nếu chưa có phương án xác minh tương đương.
- Việc tạo index sau nạp cũng tiêu tốn I/O, CPU và dung lượng tạm; hãy đo thử và lập kế hoạch.

Sau khi nạp số lượng lớn, có thể cập nhật thống kê cho optimizer:

~~~sql
ANALYZE TABLE app_db.orders_restore;
~~~

Lệnh này cập nhật thống kê phục vụ lựa chọn kế hoạch truy vấn; nó không chứng minh dữ liệu đúng về mặt nghiệp vụ.

### 4.4. Theo dõi tác động vận hành

Trong lúc nạp, theo dõi:

- Tốc độ ghi, độ trễ commit và thời gian xử lý mỗi lô.
- CPU, IOPS, thông lượng đĩa và dung lượng còn trống.
- Kích thước redo/undo, binary log và dung lượng tệp tạm.
- Số kết nối, lock wait, deadlock và transaction chạy lâu.
- Replication lag nếu có replica nhận thay đổi từ máy chủ phục hồi.

Giới hạn số luồng nạp đồng thời. Tăng concurrency quá nhanh có thể khiến nhiều luồng tranh chấp I/O và index, làm tổng thời gian dài hơn. Khi production bị ảnh hưởng, giảm tốc độ nạp hoặc chuyển công việc sang instance riêng thay vì tiếp tục tăng tải.

## 5. Kiểm tra cấu trúc và ràng buộc

Kiểm tra ràng buộc phải diễn ra trước cutover. Một bảng có đủ số dòng vẫn có thể sai nếu thiếu index, có khóa ngoại mồ côi hoặc chứa dữ liệu không hợp lệ theo quy tắc nghiệp vụ.

### 5.1. So sánh cấu trúc

Đối chiếu SHOW CREATE TABLE giữa nguồn tin cậy, staging và bảng đích. Kiểm tra:

- Danh sách cột, thứ tự, kiểu dữ liệu, độ dài và thuộc tính UNSIGNED.
- NULL, DEFAULT, AUTO_INCREMENT và generated column.
- Primary key, unique index, secondary index và thứ tự cột trong từng index.
- Foreign key, hành động ON DELETE và ON UPDATE.
- CHECK constraint, partition, engine, charset và collation.
- Trigger gắn với bảng và các đối tượng phụ thuộc.

Nếu bảng được phục hồi từ phiên bản MySQL khác, cần xác minh cú pháp và hành vi của tính năng. Ví dụ, CHECK constraint được MySQL thực thi từ phiên bản 8.0.16; các phiên bản trước đó có thể chấp nhận cú pháp nhưng không thực thi điều kiện như mong đợi. Cũng cần kiểm tra constraint có được khai báo ENFORCED hay không.

### 5.2. Kiểm tra khóa chính và unique key

Khóa chính phải có giá trị duy nhất và không NULL. Nếu bảng staging đã có primary key, lỗi trùng khóa trong lúc nạp thường khiến transaction hoặc câu lệnh thất bại. Nếu dữ liệu được nạp vào một bảng tạm không có unique index, hãy kiểm tra trước khi tạo index:

~~~sql
SELECT id, COUNT(*) AS duplicate_count
FROM app_db.orders_restore
GROUP BY id
HAVING COUNT(*) > 1
LIMIT 20;
~~~

Kiểm tra một khóa nghiệp vụ duy nhất, ví dụ **order_number**:

~~~sql
SELECT order_number, COUNT(*) AS duplicate_count
FROM app_db.orders_restore
GROUP BY order_number
HAVING COUNT(*) > 1
LIMIT 20;
~~~

Nếu unique key gồm nhiều cột, phải nhóm theo toàn bộ các cột của khóa. Không tự ý xóa một trong các dòng trùng; cần xác định dòng nào hợp lệ theo nguồn dữ liệu và quy tắc nghiệp vụ.

### 5.3. Kiểm tra khóa ngoại

Giả sử **orders.customer_id** tham chiếu **customers.id**. Có thể tìm dòng mồ côi bằng anti-join:

~~~sql
SELECT COUNT(*) AS orphan_count
FROM app_db.orders_restore AS o
LEFT JOIN app_db.customers AS c
  ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

Kết quả mong đợi là **orphan_count = 0**, trừ khi nghiệp vụ cho phép một trường hợp tham chiếu đặc biệt đã được mô tả rõ. Hãy chạy kiểm tra cho từng khóa ngoại và xác nhận bảng cha đang được kiểm tra ở cùng mốc dữ liệu với bảng con.

Thứ tự phục hồi thường là bảng cha trước, bảng con sau. Nếu phải nạp dữ liệu theo thứ tự khác, có thể gặp lỗi foreign key. MySQL không hỗ trợ trì hoãn kiểm tra khóa ngoại đến cuối transaction như một số hệ quản trị khác.

**SET FOREIGN_KEY_CHECKS = 0** có thể được dùng trong một quy trình nạp được kiểm soát, nhưng cần hiểu giới hạn quan trọng: khi bật lại **FOREIGN_KEY_CHECKS = 1**, MySQL không tự quét và xác minh lại các dòng đã được nạp trong thời gian tắt kiểm tra. Vì vậy, bật lại không chứng minh rằng dữ liệu không có orphan. Nếu dùng tùy chọn này, phải chạy các truy vấn đối soát khóa ngoại độc lập trước khi cutover. Tránh thay đổi biến ở cấp global cho một công việc nạp dữ liệu thông thường.

### 5.4. Kiểm tra CHECK constraint và quy tắc miền dữ liệu

CHECK constraint có thể biểu diễn các điều kiện như số lượng không âm hoặc ngày kết thúc không sớm hơn ngày bắt đầu. Ví dụ:

~~~sql
ALTER TABLE app_db.orders_restore
  ADD CONSTRAINT chk_orders_total_nonnegative
  CHECK (total_amount >= 0);
~~~

Chỉ thêm constraint nếu nó đúng với quy tắc nghiệp vụ và phiên bản MySQL hỗ trợ thực thi. Trước khi thêm, tìm các dòng vi phạm:

~~~sql
SELECT COUNT(*) AS invalid_amount_count
FROM app_db.orders_restore
WHERE total_amount < 0;
~~~

Các điều kiện có thể trả về UNKNOWN khi biểu thức chứa NULL; vì vậy CHECK constraint không tự thay thế yêu cầu NOT NULL. Ví dụ, nếu total_amount bắt buộc phải có giá trị, cần kiểm tra cả null và giá trị âm, hoặc khai báo cột NOT NULL theo đúng thiết kế.

## 6. Đối soát số liệu nghiệp vụ

Đối soát nghiệp vụ trả lời câu hỏi: dữ liệu sau phục hồi có tạo ra kết quả mà hệ thống và người dùng mong đợi hay không? Kiểm tra cấu trúc và ràng buộc là cần thiết, nhưng chưa đủ. Một bảng có thể không vi phạm khóa nào mà vẫn thiếu một ngày dữ liệu, sai trạng thái đơn hàng hoặc lệch tổng tiền.

### 6.1. So sánh số dòng và phạm vi khóa

Kiểm tra số dòng, giá trị khóa nhỏ nhất và lớn nhất:

~~~sql
SELECT
  COUNT(*) AS row_count,
  MIN(id) AS min_id,
  MAX(id) AS max_id
FROM app_db.orders_restore;
~~~

So sánh với nguồn backup hoặc số liệu đã ghi nhận tại cùng mốc. COUNT(*) trên InnoDB có thể cần đọc nhiều dữ liệu và tốn thời gian với bảng lớn. Giá trị ước lượng trong information_schema.TABLES.TABLE_ROWS không phải số đếm chính xác; chỉ dùng để tham khảo khi lập kế hoạch.

Để tìm khoảng bị thiếu, có thể chia dữ liệu theo các dải khóa chính và so sánh số dòng từng dải giữa nguồn và staging. Cách này giúp khoanh vùng sai lệch mà không cần xử lý toàn bộ bảng trong một truy vấn tổng hợp duy nhất.

### 6.2. So sánh tổng tiền và số lượng theo trạng thái

Giả sử bảng đơn hàng có status, total_amount và created_at. Một báo cáo tổng hợp có thể là:

~~~sql
SELECT
  DATE(created_at) AS order_date,
  status,
  COUNT(*) AS order_count,
  SUM(total_amount) AS total_amount
FROM app_db.orders_restore
WHERE created_at >= '2026-11-01'
  AND created_at <  '2026-11-20'
GROUP BY DATE(created_at), status
ORDER BY order_date, status;
~~~

So sánh kết quả theo ngày và trạng thái với nguồn tin cậy hoặc báo cáo nghiệp vụ đã chốt tại cùng mốc thời gian. Dùng kiểu DECIMAL cho tiền tệ và so sánh theo độ chính xác đã quy định; không chuyển sang FLOAT để đối soát số tiền vì sai số biểu diễn nhị phân có thể gây chênh lệch.

### 6.3. Kiểm tra null, miền giá trị và mốc thời gian

Các truy vấn sau giúp phát hiện dữ liệu bất thường:

~~~sql
SELECT
  SUM(customer_id IS NULL) AS missing_customer,
  SUM(total_amount IS NULL) AS missing_total,
  SUM(total_amount < 0) AS negative_total,
  MIN(created_at) AS first_order,
  MAX(created_at) AS last_order
FROM app_db.orders_restore;
~~~

Điều kiện cụ thể phụ thuộc nghiệp vụ. Một đơn hàng có thể chưa có customer_id trong một số luồng nhập liệu; một số trạng thái có thể có tổng tiền bằng 0. Không kết luận dữ liệu sai chỉ dựa trên một giá trị khác 0 hoặc một giá trị NULL mà chưa hiểu quy tắc.

### 6.4. Đối chiếu với bảng liên quan hoặc hệ thống nguồn

Nếu đơn hàng phải có bản ghi thanh toán tương ứng, có thể kiểm tra số đơn chưa có thanh toán:

~~~sql
SELECT COUNT(*) AS orders_without_payment
FROM app_db.orders_restore AS o
LEFT JOIN app_db.payments AS p
  ON p.order_id = o.id
WHERE o.status = 'PAID'
  AND p.order_id IS NULL;
~~~

Đây là kiểm tra ví dụ; hệ thống có thể cho phép thanh toán được ghi nhận trễ hoặc chia thành nhiều giao dịch. Hãy điều chỉnh theo mô hình dữ liệu thật, chẳng hạn tổng hợp nhiều payment cho một order hoặc loại trừ các trạng thái chưa hoàn tất.

Với dữ liệu quan trọng như số dư, doanh thu hoặc tồn kho, nên đối chiếu thêm với sổ cái, hệ thống thanh toán hoặc nguồn nghiệp vụ độc lập. Chốt rõ thời điểm, múi giờ, trạng thái được tính và quy tắc hoàn tiền/hủy đơn. Hai báo cáo dùng các mốc thời gian hoặc bộ lọc khác nhau có thể lệch dù bảng đã được phục hồi đúng.

### 6.5. Kiểm tra theo từng lô

Đối với bảng quá lớn, chia đối soát theo khoảng khóa hoặc khoảng thời gian:

~~~sql
SELECT
  COUNT(*) AS row_count,
  SUM(total_amount) AS total_amount,
  MIN(created_at) AS first_created_at,
  MAX(created_at) AS last_created_at
FROM app_db.orders_restore
WHERE id >= 100001
  AND id < 200001;
~~~

Lưu kết quả từng lô cùng ranh giới khóa, số dòng và tổng tiền. Khi một lô sai lệch, chỉ cần điều tra khoảng đó. Có thể bổ sung digest theo lô nếu hệ thống có công cụ tính checksum ổn định; checksum chỉ là tín hiệu hỗ trợ và cần xác định rõ cột, thứ tự dòng, kiểu dữ liệu và cách chuẩn hóa trước khi so sánh.

### 6.6. So sánh trên cùng một mốc dữ liệu

Một lỗi đối soát phổ biến là so sánh staging tại thời điểm backup với production đang tiếp tục nhận giao dịch. Hai bên sẽ khác nhau một cách hợp lệ. Hãy chọn một trong các cách:

- Tạm dừng ghi trong khoảng kiểm tra và cutover.
- Đưa staging và nguồn về cùng mốc bằng binary log hoặc cơ chế đồng bộ đã kiểm chứng.
- Ghi nhận watermark rõ ràng, ví dụ khóa chính lớn nhất hoặc thời điểm giao dịch cuối cùng đã được xử lý, rồi so sánh cùng phạm vi.

Nếu ứng dụng có nhiều writer hoặc xử lý bất đồng bộ, cần xác định cả các sự kiện đang nằm trong queue. Một watermark đơn giản theo MAX(id) có thể không đủ nếu ID được cấp trước khi transaction commit hoặc có nhiều nguồn ghi độc lập.

## 7. Chuyển bảng đã kiểm chứng vào sử dụng

Chỉ cutover khi dữ liệu và cấu trúc đã vượt qua các kiểm tra cần thiết. Kế hoạch cutover phải nêu rõ thời gian ngừng ghi, cách xử lý các giao dịch phát sinh sau mốc backup và cách quay lại bảng cũ nếu kiểm tra sau chuyển đổi thất bại.

### 7.1. Chốt thay đổi cuối cùng

Nếu ứng dụng vẫn ghi trong lúc staging được phục hồi, bảng staging có thể thiếu các giao dịch mới. Có ba cách xử lý thường gặp:

1. **Maintenance window:** dừng hoặc chuyển ứng dụng sang chế độ chỉ đọc, ghi nhận mốc cuối, đưa staging đến đúng mốc rồi cutover.
2. **Delta replay:** lưu và áp dụng phần thay đổi phát sinh kể từ snapshot theo một quy trình có thứ tự, bảo đảm không bỏ sót hoặc áp dụng trùng giao dịch.
3. **Dual-write hoặc change capture:** chỉ dùng khi hệ thống đã có cơ chế đồng bộ được thiết kế, giám sát và kiểm thử cho tình huống phục hồi.

Không tự tạo cơ chế sao chép thay đổi tạm thời trong lúc sự cố nếu chưa xác định được thứ tự transaction, xung đột ghi và cách phát hiện dữ liệu bị bỏ sót.

### 7.2. Chọn cách cutover

Với bảng đơn giản, có thể cân nhắc đổi tên bảng trong một thao tác RENAME TABLE nhiều bảng:

~~~sql
RENAME TABLE
  app_db.orders TO app_db.orders_before_restore,
  app_db.orders_restore TO app_db.orders;
~~~

Đây chỉ là ví dụ minh họa cho một phương án cutover. Trước khi sử dụng, phải kiểm thử trên phiên bản và cấu trúc tương đương, đặc biệt nếu bảng có foreign key được bảng khác tham chiếu, trigger, view, partition hoặc đối tượng phụ thuộc. Việc đổi tên có thể ảnh hưởng metadata và các phụ thuộc của ứng dụng. Không giả định rằng mọi hệ thống đều có thể hoán đổi bảng bằng một lệnh như trên mà không cần điều chỉnh.

Nếu không thể đổi tên an toàn, có thể dùng quy trình nạp dữ liệu vào bảng đích theo lô trong maintenance window, hoặc thiết kế một lần chuyển đổi riêng phù hợp với quan hệ dữ liệu. DDL như ALTER TABLE và RENAME TABLE có thể gây implicit commit; không dựa vào ROLLBACK để hoàn tác một cutover DDL.

### 7.3. Kiểm tra ngay sau cutover

Sau khi chuyển đổi:

- Xác nhận ứng dụng kết nối đúng schema và bảng mới.
- Chạy truy vấn đọc đại diện, truy vấn ghi thử có kiểm soát nếu quy trình cho phép.
- Kiểm tra lỗi ứng dụng, lỗi constraint và log MySQL.
- Theo dõi latency, lock wait, deadlock, CPU, I/O và replication lag.
- So sánh các chỉ số nghiệp vụ chính với kết quả staging đã phê duyệt.
- Giữ bảng cũ hoặc bản snapshot theo thời hạn lưu giữ đã thống nhất để có thể điều tra hoặc quay lại.

Không xóa bảng cũ ngay sau khi một truy vấn thử thành công. Chỉ dọn dẹp sau khi chủ sở hữu dữ liệu xác nhận kết quả và hết thời gian theo dõi cần thiết.

## 8. Những lỗi phục hồi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Import dừng vì duplicate key | Dữ liệu trùng khóa hoặc bảng đích đã có một phần dữ liệu | Xác định lô đã commit, tìm khóa trùng và quyết định xử lý theo quy tắc nghiệp vụ |
| Import báo lỗi foreign key | Bảng cha chưa được phục hồi, ID tham chiếu không tồn tại hoặc schema không khớp | Phục hồi bảng cha trước, chạy anti-join và đối chiếu kiểu dữ liệu khóa |
| Bật lại FOREIGN_KEY_CHECKS nhưng vẫn có dòng mồ côi | MySQL không tự kiểm tra lại dữ liệu đã nạp khi tắt kiểm tra | Chạy truy vấn xác minh cho từng quan hệ trước cutover |
| Nạp dữ liệu rất chậm | I/O bão hòa, nhiều secondary index, transaction quá lớn hoặc quá nhiều luồng | Đo từng lô, giảm concurrency, điều chỉnh kích thước transaction và kiểm tra tài nguyên |
| Dung lượng đĩa tăng nhanh | Tệp staging, index, redo/undo, binlog hoặc temporary file tăng | Dự báo dung lượng trước, theo dõi không gian trống và dừng có kiểm soát nếu sắp cạn |
| Tổng tiền đúng nhưng số đơn sai | Hai loại lỗi bù trừ nhau hoặc bộ lọc/trạng thái không giống nhau | So sánh đồng thời count, sum, nhóm trạng thái và khoảng thời gian |
| Dữ liệu staging khác production | Hai bên ở mốc thời gian khác nhau hoặc còn giao dịch chưa đồng bộ | Chốt watermark hoặc đưa hai phía về cùng mốc |
| Ứng dụng lỗi sau cutover | Thiếu index, trigger, quyền, view hoặc cấu trúc khác biệt | Đối chiếu schema và phụ thuộc, kiểm tra log ứng dụng/MySQL, kích hoạt phương án quay lại |

## 9. Quy trình thực hành mẫu

Giả sử bảng orders của hệ thống bán hàng có hàng trăm triệu dòng. Bảng chứa id, customer_id, status, total_amount và created_at; customer_id tham chiếu customers.id. Một thao tác triển khai đã làm mất một phần dữ liệu trong khoảng ngày 18/11. Mục tiêu là khôi phục dữ liệu đúng đến ngay trước thao tác lỗi.

Thực hiện theo quy trình:

1. Ghi nhận thời điểm thao tác lỗi và xác định transaction hoặc sự kiện liên quan trong audit log/binlog.
2. Chọn bản backup nền gần nhất trước thời điểm lỗi, kiểm tra metadata và tính liên tục của binary log.
3. Phục hồi backup vào instance tạm tương thích với production.
4. Áp dụng binary log đến ngay trước thao tác gây lỗi; kiểm tra mốc dừng và dữ liệu tại thời điểm đó.
5. Xuất riêng bảng orders từ instance tạm, nạp vào restore_stage.
6. Đối chiếu cấu trúc, khóa chính, unique key, khóa ngoại, CHECK constraint và trigger.
7. Đối soát số dòng theo khoảng ID, tổng tiền theo ngày/trạng thái, min/max thời gian và số đơn theo trạng thái.
8. Chạy anti-join để kiểm tra customer_id mồ côi; đối chiếu số đơn đã thanh toán với bảng payment hoặc nguồn nghiệp vụ.
9. Chốt phương án giữ giao dịch mới phát sinh kể từ snapshot: maintenance window, delta replay hoặc cơ chế change capture đã có.
10. Cutover theo kế hoạch đã thử nghiệm, theo dõi ứng dụng và chỉ dọn bảng cũ sau khi chủ sở hữu dữ liệu xác nhận.

Kết quả cần lưu lại gồm nguồn backup, vị trí/GTID và thời điểm PITR, cấu trúc bảng, số dòng theo lô, các chỉ số đối soát, số lượng vi phạm ràng buộc, thời điểm cutover và người xác nhận. Những thông tin này giúp lần phục hồi sau có thể lặp lại và kiểm toán được.

## 10. Checklist trước khi xác nhận phục hồi

- [ ] Đã xác định đúng bảng, phạm vi dữ liệu và recovery point.
- [ ] Bản backup và binary log có nguồn gốc, metadata và tính liên tục đã được kiểm tra.
- [ ] Đã giữ lại trạng thái hiện tại phục vụ điều tra hoặc quay lại.
- [ ] Staging tương thích về phiên bản, engine, charset, collation và cấu trúc.
- [ ] Dữ liệu được nạp đủ; các lô đã commit được ghi nhận.
- [ ] Primary key và unique key không có xung đột ngoài dự kiến.
- [ ] Các khóa ngoại không có dòng mồ côi; CHECK constraint và quy tắc miền dữ liệu hợp lệ.
- [ ] Số dòng, khoảng khóa, tổng hợp nghiệp vụ và mốc thời gian khớp với nguồn tin cậy.
- [ ] Staging và dữ liệu dùng để so sánh ở cùng một mốc hoặc watermark.
- [ ] Đã xử lý các giao dịch phát sinh sau snapshot.
- [ ] Kế hoạch cutover và rollback đã được kiểm thử với các phụ thuộc của bảng.
- [ ] Ứng dụng và chỉ số vận hành đã được kiểm tra sau cutover.

## 11. Câu hỏi tự kiểm tra

1. Vì sao nên phục hồi một bảng lớn vào staging trước khi thay thế bảng production?
2. --single-transaction của mysqldump bảo đảm điều gì và không bảo đảm điều gì?
3. Vì sao phục hồi một bảng từ physical backup thường cần thêm bước phục hồi instance tạm?
4. Khi thực hiện PITR, cần biết thông tin nào từ metadata của backup để chọn đúng điểm bắt đầu áp dụng binary log?
5. Vì sao tắt FOREIGN_KEY_CHECKS rồi bật lại không đủ để chứng minh bảng không có dữ liệu mồ côi?
6. Với một bảng đơn hàng, những chỉ số nào cần đối chiếu ngoài COUNT(*)?
7. Vì sao phải so sánh staging và production tại cùng một mốc thời gian hoặc watermark?
8. Những phụ thuộc nào cần kiểm tra trước khi dùng RENAME TABLE để cutover?

Một lần phục hồi đáng tin cậy phải chứng minh được ba điều: dữ liệu đến từ nguồn và mốc thời gian xác định, các ràng buộc quan hệ được kiểm tra thực tế, và các số liệu nghiệp vụ quan trọng khớp với nguồn đối chiếu. Chỉ sau khi có đủ bằng chứng đó, bảng mới nên được đưa trở lại phục vụ ứng dụng.
