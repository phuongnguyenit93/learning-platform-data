Câu 1. Trong InnoDB, vai trò chính của `PRIMARY KEY` trên bảng là gì?
A. Bản ghi được tổ chức theo khóa trong clustered index.
B. Lưu bảng theo thứ tự của mọi secondary index đang có.
C. Tự tạo một bản sao bảng riêng cho từng cột có khóa.
D. Tự khóa toàn bộ bảng mỗi khi một bản ghi được ghi.
Đáp án đúng: A

Câu 2. Với một cột nullable có `UNIQUE` index, MySQL cho phép trường hợp nào?
A. Chỉ một hàng có `NULL`, còn các giá trị khác được trùng.
B. Cho phép nhiều `NULL`, còn giá trị thực phải duy nhất.
C. Mọi giá trị, kể cả khác `NULL`, đều phải có thứ tự tăng.
D. Mọi hàng có `NULL` đều bị từ chối bởi unique index.
Đáp án đúng: B

Câu 3. `ON DELETE CASCADE` trên foreign key của InnoDB tác động thế nào?
A. Chặn xóa hàng cha nếu vẫn còn hàng con liên kết.
B. Đặt khóa ngoại thành `NULL` khi hàng cha bị xóa.
C. Chuyển hàng con sang một khóa cha mặc định khi xóa.
D. Xóa các hàng con tham chiếu khi hàng cha bị xóa.
Đáp án đúng: D

Câu 4. Kiểu MySQL nào phù hợp để lưu số tiền cần phần thập phân chính xác?
A. `DOUBLE` với biểu diễn dấu phẩy động nhị phân.
B. `DECIMAL(p,s)` với precision và scale được chọn.
C. `FLOAT` với số bit mantissa nhỏ hơn DOUBLE.
D. `VARCHAR` để lưu số theo dạng chuỗi ký tự.
Đáp án đúng: B

Câu 5. Charset `utf8mb4` của MySQL hữu ích trong tình huống nào?
A. Cần mỗi ký tự luôn chiếm đúng bốn byte.
B. Cần so sánh chuỗi luôn phân biệt hoa thường.
C. Cần rút ngắn mọi cột chuỗi còn tối đa bốn ký tự.
D. Cần lưu toàn bộ Unicode, gồm ký tự emoji.
Đáp án đúng: D

Câu 6. So với `DATETIME`, cột `TIMESTAMP` của MySQL khác biệt đáng chú ý nào?
A. Giá trị luôn giữ nguyên chuỗi thời gian khi đổi time zone.
B. Giá trị không thể được dùng với hàm ngày giờ của SQL.
C. Đổi theo múi giờ session khi ghi và đọc `TIMESTAMP`.
D. Giá trị chỉ lưu được ngày mà không lưu được giờ phút.
Đáp án đúng: C

Câu 7. Để tìm các hàng có `phone` là `NULL`, điều kiện SQL nào đúng?
A. `WHERE phone = NULL` so sánh bằng giá trị thiếu.
B. `WHERE phone IN (NULL)` so khớp giá trị thiếu.
C. `WHERE phone IS NULL` kiểm tra giá trị thiếu.
D. `WHERE phone <> NULL` loại mọi giá trị không thiếu.
Đáp án đúng: C

Câu 8. Sau `LEFT JOIN`, đặt điều kiện `b.state = 'ok'` trong `WHERE` thường có hệ quả gì?
A. Hàng bên trái không khớp có thể bị loại bởi `WHERE`.
B. Mọi hàng bên trái vẫn giữ, kể cả hàng không khớp.
C. MySQL tự thay `LEFT JOIN` bằng `FULL OUTER JOIN`.
D. Điều kiện chỉ ảnh hưởng đến phép sắp xếp kết quả.
Đáp án đúng: A

Câu 9. Khi cần lọc nhóm theo `COUNT(*) > 10`, mệnh đề SQL nào phù hợp?
A. Dùng `WHERE` sau `GROUP BY` để lọc kết quả đếm.
B. Dùng `HAVING` sau `GROUP BY` để lọc kết quả nhóm.
C. Dùng `ORDER BY` trước `GROUP BY` để lọc nhóm.
D. Dùng `LIMIT` trước `GROUP BY` để lọc nhóm.
Đáp án đúng: B

Câu 10. Trong MySQL, khác biệt giữa `COUNT(col)` và `COUNT(*)` là gì?
A. `COUNT(col)` đếm mọi hàng; `COUNT(*)` bỏ giá trị `NULL`.
B. `COUNT(col)` chỉ đếm hàng trùng; `COUNT(*)` đếm hàng khác.
C. `COUNT(col)` đếm nhóm; `COUNT(*)` đếm số cột của bảng.
D. `COUNT(col)` bỏ qua `NULL`; `COUNT(*)` đếm mọi hàng.
Đáp án đúng: D

Câu 11. Biểu thức `EXISTS (SELECT ... )` trả về đúng khi nào?
A. Truy vấn con trả về ít nhất một cột không `NULL`.
B. Truy vấn con trả về chính xác một hàng dữ liệu.
C. Truy vấn con trả về ít nhất một hàng dữ liệu.
D. Truy vấn con có `ORDER BY` và `LIMIT` đồng thời.
Đáp án đúng: C

Câu 12. Cách giảm nguy cơ SQL injection khi nhận giá trị từ người dùng là gì?
A. Ghép chuỗi SQL rồi tự xóa dấu nháy đơn.
B. Bind tham số qua prepared statement của driver.
C. Dùng `ESCAPE` với mọi giá trị trước khi ghép SQL.
D. Chỉ giới hạn độ dài chuỗi nhận từ biểu mẫu.
Đáp án đúng: B

Câu 13. `EXPLAIN SELECT ...` trong MySQL cung cấp thông tin gì?
A. Thời gian thực tế và row count sau mỗi operator.
B. Báo cáo toàn bộ transaction và khóa đang chờ.
C. Danh sách toàn bộ connection đang mở trên server.
D. Xem kế hoạch optimizer dự tính mà chưa chạy SELECT.
Đáp án đúng: D

Câu 14. Với truy vấn SELECT, `EXPLAIN ANALYZE` trong MySQL 8 có điểm nào khác `EXPLAIN`?
A. Chạy SELECT và hiện số hàng cùng thời gian thực tế.
B. Chỉ ước lượng kế hoạch mà không chạy câu SELECT.
C. Tự động thêm index để dùng cho lần SELECT tiếp theo.
D. Luôn chuyển truy vấn thành stored procedure trước khi chạy.
Đáp án đúng: A

Câu 15. Nhận định nào đúng về giá trị `AUTO_INCREMENT` của khóa chính MySQL?
A. Dãy ID luôn liên tục kể cả khi có rollback transaction.
B. Dãy ID được đánh lại liên tục sau mỗi câu DELETE.
C. Dãy ID luôn theo thứ tự commit giữa mọi transaction.
D. Dãy ID có thể bị khuyết sau lỗi ghi hoặc rollback.
Đáp án đúng: D

Câu 16. Index `(tenant_id, created_at)` phù hợp với bộ lọc nào theo nguyên tắc tiền tố trái?
A. `WHERE created_at = ?` luôn dùng toàn bộ index hiệu quả.
B. `WHERE status = ?` có thể dùng tiền tố của index.
C. `WHERE tenant_id = ?` tận dụng tiền tố trái của index.
D. `WHERE email = ?` luôn dùng tiền tố của index này.
Đáp án đúng: C

Câu 17. Với truy vấn `WHERE tenant_id = ? AND created_at >= ?`, index nào đáng cân nhắc đầu tiên?
A. `(created_at, status)` cho lọc bằng rồi lọc khoảng.
B. `(status, created_at)` cho lọc bằng rồi lọc khoảng.
C. `(tenant_id, created_at)` cho lọc bằng rồi lọc khoảng.
D. `(tenant_id, status)` cho lọc bằng rồi lọc khoảng.
Đáp án đúng: C

Câu 18. Một covering index có thể cải thiện truy vấn theo cách nào?
A. Lấy các cột ngay tại index, giảm việc truy cập bảng dữ liệu.
B. Tự động làm mọi câu UPDATE bỏ qua việc ghi vào bảng.
C. Loại bỏ chi phí duy trì index cho mỗi lần INSERT dữ liệu.
D. Tự tạo bản sao toàn bảng để tránh truy cập trang đĩa.
Đáp án đúng: A

Câu 19. Với B-tree index trên cột `name`, điều kiện nào thường dễ dùng range scan?
A. `name LIKE '%Ann'` với ký tự bất kỳ phía trước.
B. `name LIKE '%Ann%'` với hai ký tự đại diện.
C. `LOWER(name) LIKE '%Ann'` với hàm trên cột.
D. `name LIKE 'Ann%'` với tiền tố cố định phía trước.
Đáp án đúng: D

Câu 20. Tác dụng phụ thường gặp khi thêm nhiều secondary index vào bảng là gì?
A. Làm giảm số transaction có thể rollback trong InnoDB.
B. Làm xóa bỏ mọi khóa hàng khi có các câu UPDATE.
C. Làm tăng chi phí ghi và dung lượng lưu trữ index.
D. Làm mọi phép truy vấn bắt buộc quét toàn bảng.
Đáp án đúng: C

Câu 21. Sau khi phân bố dữ liệu bảng thay đổi mạnh, `ANALYZE TABLE` thường giúp điều gì?
A. Làm mới thống kê index để optimizer dự đoán tốt hơn.
B. Sửa trực tiếp mọi giá trị trùng trong unique index.
C. Thêm index tự động vào các cột được dùng trong WHERE.
D. Đổi engine của bảng từ InnoDB sang MEMORY.
Đáp án đúng: A

Câu 22. Lợi ích của index phù hợp với `ORDER BY ... LIMIT` có thể là gì?
A. Bảo đảm không cần lọc WHERE trong mọi câu truy vấn.
B. Tăng kích thước kết quả để bộ nhớ đệm dùng hiệu quả.
C. Chặn mọi câu UPDATE khi chạy truy vấn có LIMIT.
D. Tránh bước sắp xếp riêng và giảm số hàng cần đọc.
Đáp án đúng: D

Câu 23. Khi `autocommit = 1` và không bắt đầu transaction riêng, DML thành công sẽ thế nào?
A. Mọi statement chờ đến khi connection đóng mới commit.
B. Chỉ câu SELECT được commit tự động; DML phải COMMIT.
C. Mọi statement được rollback khi kết thúc connection.
D. Mỗi DML thành công được commit sau khi chạy xong.
Đáp án đúng: D

Câu 24. Isolation level mặc định thường dùng của InnoDB trong MySQL là gì?
A. `READ COMMITTED` cho transaction thông thường.
B. `READ UNCOMMITTED` cho transaction thông thường.
C. `REPEATABLE READ` là mức cách ly mặc định của InnoDB.
D. `SERIALIZABLE` cho transaction thông thường.
Đáp án đúng: C

Câu 25. MVCC của InnoDB giúp `SELECT` không khóa thông thường bằng cách nào?
A. Khóa độc quyền mọi hàng được SELECT cho đến khi commit.
B. Đọc phiên bản hàng phù hợp với snapshot của transaction.
C. Chép toàn bộ bảng vào một temporary table riêng cho SELECT.
D. Buộc các writer tạm ngừng trong khi đọc snapshot.
Đáp án đúng: B

Câu 26. Trong transaction đang mở, `SELECT ... FOR UPDATE` thường thực hiện gì?
A. Dùng consistent snapshot mà không đặt khóa trên hàng nào.
B. Khóa các hàng được chọn để cập nhật đến hết transaction.
C. Tự commit ngay sau SELECT bất kể transaction đang mở.
D. Chuyển mọi row lock hiện hữu thành table lock độc quyền.
Đáp án đúng: B

Câu 27. Trong InnoDB `READ COMMITTED`, hai SELECT snapshot liên tiếp có thể thấy gì?
A. Cả transaction luôn dùng snapshot lần đọc đầu tiên.
B. SELECT thứ hai chỉ thấy dữ liệu sau khi transaction commit.
C. SELECT sau có thể thấy commit mới từ transaction khác.
D. Mỗi SELECT luôn khóa toàn bảng để ngăn thay đổi.
Đáp án đúng: C

Câu 28. Next-key lock trong InnoDB kết hợp loại khóa nào khi locking range?
A. Khóa bảng và metadata để chặn mọi schema change.
B. Khóa bản ghi và khoảng để hạn chế phantom insert.
C. Khóa phiên và connection để tránh đọc dữ liệu cũ.
D. Khóa cache và disk page để chặn mọi lần ghi dữ liệu.
Đáp án đúng: B

Câu 29. Khi InnoDB phát hiện deadlock giữa hai transaction, điều thường xảy ra là gì?
A. Cả hai transaction luôn bị rollback ngay lập tức.
B. Transaction có thời gian chạy dài hơn luôn được giữ.
C. Rollback một transaction để phá vòng chờ deadlock.
D. MySQL tự tăng isolation level để giải quyết deadlock.
Đáp án đúng: C

Câu 30. Điều gì cần chú ý khi chạy `ALTER TABLE` trong transaction MySQL?
A. DDL thường gây implicit commit, không rollback như DML.
B. DDL luôn rollback cùng mọi UPDATE trước nó khi gặp lỗi.
C. DDL chỉ có hiệu lực sau lệnh COMMIT của transaction.
D. DDL tự chuyển thành SELECT để tránh khóa metadata.
Đáp án đúng: A

Câu 31. Slow query log của MySQL được dùng chủ yếu để làm gì?
A. Ghi mọi thao tác cấp quyền kèm thời gian hết hạn.
B. Ghi mọi câu SQL thất bại do vi phạm unique constraint.
C. Ghi tất cả trang dữ liệu được đẩy ra khỏi buffer pool.
D. Ghi truy vấn thỏa điều kiện chậm để phân tích hiệu năng.
Đáp án đúng: D

Câu 32. MySQL Performance Schema phù hợp nhất cho công việc nào?
A. Quan sát statement, wait event và tài nguyên thực thi.
B. Sao lưu mọi bảng mà không cần kết nối database.
C. Thay đổi isolation level cho toàn bộ transaction cũ.
D. Chuyển mọi truy vấn từ SQL sang một định dạng đồ thị.
Đáp án đúng: A

Câu 33. InnoDB buffer pool có vai trò chính gì trong hoạt động MySQL?
A. Cache toàn bộ file binary log để thay cơ chế backup.
B. Cache trang dữ liệu và index để giảm số lần đọc đĩa.
C. Cache câu lệnh `GRANT` nhằm bỏ qua xác thực user.
D. Cache các connection TCP cho replica khi ứng dụng đọc.
Đáp án đúng: B

Câu 34. Lệnh `SHOW PROCESSLIST` hữu ích để quan sát điều gì?
A. Toàn bộ index và constraint định nghĩa trên mỗi bảng.
B. Các session, trạng thái và truy vấn đang thực thi.
C. Bản sao lưu gần nhất được ghi vào thư mục dữ liệu.
D. Danh sách các row lock đã được giải phóng trước đó.
Đáp án đúng: B

Câu 35. Để điều tra deadlock InnoDB, lệnh nào cung cấp thông tin chẩn đoán trực tiếp?
A. `SHOW TABLE STATUS` có mục deadlock gần nhất.
B. `SHOW GRANTS` có mục deadlock gần nhất.
C. `SHOW ENGINE INNODB STATUS` báo deadlock gần nhất.
D. `SHOW CREATE TABLE` có mục deadlock gần nhất.
Đáp án đúng: C

Câu 36. Khi dùng `mysqldump --single-transaction` cho bảng InnoDB, mục tiêu là gì?
A. Dump bảng InnoDB bằng snapshot nhất quán theo transaction.
B. Khóa ghi mọi bảng trong toàn bộ quá trình dump InnoDB.
C. Tạo backup vật lý các data file thay vì câu SQL.
D. Tự khôi phục database từ bản dump vừa tạo ra.
Đáp án đúng: A

Câu 37. Để khôi phục MySQL đến thời điểm trước sự cố bằng PITR, cần phối hợp gì?
A. Chỉ phát lại slow query log mà không cần bản backup.
B. Restore backup phù hợp rồi phát lại binary log đến mốc.
C. Chỉ xem `EXPLAIN` rồi tạo lại index đã mất.
D. Chỉ tăng `innodb_buffer_pool_size` để phục hồi hàng.
Đáp án đúng: B

Câu 38. Nguyên tắc cấp quyền nào giảm thiểu tác hại khi tài khoản ứng dụng bị lộ?
A. Chỉ cấp quyền cần thiết trên đúng đối tượng sử dụng.
B. Cấp `ALL PRIVILEGES` toàn server để giảm lỗi kết nối.
C. Dùng tài khoản `root` chung cho mọi ứng dụng backend.
D. Cho mọi tài khoản quyền thay đổi user để tiện vận hành.
Đáp án đúng: A

Câu 39. Trong hệ MySQL primary-replica với replication bất đồng bộ, điều gì có thể xảy ra?
A. Replica luôn đồng bộ tức thời trước khi primary commit.
B. Primary ngừng nhận ghi cho đến khi mọi replica phản hồi.
C. Replica có thể tự xác nhận commit thay cho primary.
D. Replica có thể chưa đọc thấy commit mới trên primary.
Đáp án đúng: D

Câu 40. Khi nhiều instance ứng dụng cùng kết nối vào MySQL, cần kiểm tra gì khi định cỡ pool?
A. So tổng kết nối từ pool với giới hạn `max_connections`.
B. Số class repository so với giới hạn `open_files_limit`.
C. Số bảng InnoDB so với giới hạn `max_allowed_packet`.
D. Số câu SELECT so với giới hạn `innodb_page_size`.
Đáp án đúng: A
