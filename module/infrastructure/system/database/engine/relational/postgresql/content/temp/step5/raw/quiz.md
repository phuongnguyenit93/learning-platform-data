1. Email bắt buộc không được trùng dù khác chữ hoa/thường. Cách ràng buộc PostgreSQL phù hợp là gì?
A. Dùng NOT NULL và UNIQUE trên nguyên giá trị của email.
B. Dùng NOT NULL và UNIQUE INDEX trên biểu thức lower(email).
C. Dùng NOT NULL và INDEX thường trên biểu thức lower(email).
D. Dùng CHECK email khác rỗng và UNIQUE trên email gốc.
Đáp án đúng: B

2. Ở PostgreSQL 15+, external_id được phép NULL nhưng tối đa một dòng NULL; giá trị khác NULL phải duy nhất. Chọn gì?
A. Khai báo UNIQUE thông thường trên cột external_id.
B. Tạo UNIQUE INDEX chỉ cho external_id IS NOT NULL.
C. Tạo UNIQUE INDEX chỉ cho external_id IS NULL.
D. UNIQUE NULLS NOT DISTINCT (external_id) cho cột.
Đáp án đúng: D

3. Cần tính tổng số tiền chính xác đến hai chữ số thập phân. Nên dùng kiểu cột nào?
A. Dùng DOUBLE PRECISION rồi ROUND ở cuối phép tính.
B. NUMERIC(14,2) cho giá trị tiền thập phân.
C. Dùng REAL rồi ROUND ở cuối câu truy vấn tính tổng.
D. Dùng TEXT rồi CAST khi cộng các dòng số tiền.
Đáp án đúng: B

4. Kiểu timestamptz thể hiện dữ liệu thời gian thế nào trong PostgreSQL?
A. Lưu nguyên tên múi giờ gốc kèm mỗi giá trị thời gian.
B. Lưu giờ địa phương, không quy đổi thời điểm về UTC.
C. Lưu thời điểm và hiển thị theo TimeZone của phiên.
D. Lưu múi giờ lúc chèn và không bị ảnh hưởng bởi phiên.
Đáp án đúng: C

5. Ứng dụng thường lọc cột payload qua toán tử chứa @> trên tài liệu JSON. Lựa chọn nào hợp lý?
A. Dùng cột json và B-tree index hỗ trợ toán tử @>.
B. Dùng cột jsonb và GIN index hỗ trợ toán tử @>.
C. Dùng cột jsonb và BRIN index hỗ trợ toán tử @>.
D. Dùng cột text và GIN index hỗ trợ toán tử @>.
Đáp án đúng: B

6. Mã dự án chỉ duy nhất trong mỗi tenant. Task phải tham chiếu Project bằng khóa nào?
A. FOREIGN KEY chỉ theo project_id đến bảng Project.
B. FOREIGN KEY chỉ theo tenant_id đến bảng Project.
C. FOREIGN KEY ghép (tenant_id, project_id) đến Project.
D. UNIQUE ghép (tenant_id, project_id) tại bảng Task.
Đáp án đúng: C

7. quantity phải là số nguyên dương và không được NULL. Ràng buộc nào thực thi đúng yêu cầu?
A. INTEGER NOT NULL và CHECK (quantity > 0).
B. INTEGER với CHECK (quantity > 0), không có NOT NULL.
C. INTEGER với DEFAULT 1 cùng CHECK (quantity >= 0).
D. INTEGER với UNIQUE(quantity) và DEFAULT 1 trên cột.
Đáp án đúng: A

8. Giả sử đã bật btree_gist, muốn cấm hai lượt đặt cùng room_id có tstzrange giao nhau. Chọn ràng buộc nào?
A. UNIQUE (room_id, period) trên mọi bản ghi đặt phòng.
B. CHECK (lower(period) < upper(period)) trên từng dòng.
C. EXCLUDE USING gist với room_id = và period &&.
D. FOREIGN KEY (room_id) tới bảng liệt kê phòng đang rảnh.
Đáp án đúng: C

9. Email có UNIQUE; cần chèn tài khoản hoặc cập nhật tên nếu email đã có. SQL nào thích hợp?
A. INSERT ... ON CONFLICT (email) DO NOTHING RETURNING id.
B. INSERT ... ON CONFLICT (id) DO UPDATE SET name = ...
C. INSERT ... ON CONFLICT (email) DO UPDATE SET name = ...
D. INSERT ... ON CONFLICT (email) DO UPDATE SET id = NULL.
Đáp án đúng: C

10. Muốn lấy ID từ dòng vừa INSERT mà không chạy thêm truy vấn đọc bảng. Sử dụng gì?
A. INSERT ... rồi SELECT MAX(id) từ toàn bộ dữ liệu bảng.
B. INSERT ... rồi SELECT id ORDER BY id DESC LIMIT 1.
C. INSERT ... rồi SELECT currval của sequence bất kỳ.
D. INSERT ... RETURNING id ngay tại câu lệnh thêm dữ liệu.
Đáp án đúng: D

11. Một SELECT cần trả tổng số đơn và số đơn paid theo từng khách. Cách tổng hợp nào đúng?
A. COUNT(*) WHERE status='paid' cho số đơn paid cùng nhóm.
B. COUNT(DISTINCT status) cho số đơn paid cùng nhóm.
C. COUNT(*) FILTER (WHERE status='paid') cho số đơn paid.
D. COUNT(*) OVER (PARTITION BY status) cho số đơn paid.
Đáp án đúng: C

12. Muốn lấy đơn mới nhất của mỗi khách bằng cú pháp riêng của PostgreSQL. Cách nào đúng?
A. DISTINCT ON (created_at) cùng ORDER BY customer_id, created_at DESC.
B. DISTINCT ON (customer_id) ORDER BY customer_id, created_at DESC.
C. GROUP BY customer_id, created_at và ORDER BY created_at DESC.
D. DISTINCT customer_id cùng ORDER BY created_at DESC, id DESC.
Đáp án đúng: B

13. Subquery liệt kê mã bị chặn có thể chứa NULL. Lọc mã không bị chặn nên chọn gì?
A. NOT IN với subquery có thể trả về các giá trị NULL.
B. <> ALL với subquery có thể trả về các giá trị NULL.
C. LEFT JOIN rồi lọc mã ở bảng bên trái IS NULL.
D. NOT EXISTS với điều kiện so sánh khóa tương ứng.
Đáp án đúng: D

14. Bảng danh mục có parent_id trỏ về chính bảng, cần lấy mọi cấp con. Câu SQL nào phù hợp?
A. WITH RECURSIVE gồm phần gốc và bước nối đệ quy.
B. WITH MATERIALIZED gồm phần gốc và bước nối đệ quy.
C. WINDOW PARTITION BY gồm phần gốc và bước nối đệ quy.
D. GROUPING SETS gồm phần gốc và bước nối đệ quy.
Đáp án đúng: A

15. Mỗi khách cần tối đa ba đơn gần nhất trong một truy vấn. JOIN nào giúp chạy subquery theo từng khách?
A. LEFT JOIN thường với ORDER BY ngày DESC và LIMIT 3.
B. CROSS JOIN chung với ORDER BY ngày DESC và LIMIT 3.
C. FULL JOIN thường với ORDER BY ngày DESC và LIMIT 3.
D. LEFT JOIN LATERAL với ORDER BY ngày DESC và LIMIT 3.
Đáp án đúng: D

16. Muốn xếp hạng mỗi sản phẩm theo doanh số trong từng category, kể cả khi có hòa điểm. Hàm nào đánh số thứ tự riêng?
A. ROW_NUMBER() OVER (PARTITION BY category ORDER BY sales DESC, id DESC).
B. ROW_NUMBER() OVER (ORDER BY sales DESC, id DESC).
C. RANK() OVER (PARTITION BY category ORDER BY sales DESC).
D. ROW_NUMBER() OVER (PARTITION BY category ORDER BY id DESC).
Đáp án đúng: A

17. Với READ COMMITTED mặc định, hai SELECT liên tiếp trong một transaction có snapshot thế nào?
A. Cả transaction dùng snapshot tại SELECT đầu tiên.
B. Các SELECT đều thấy thay đổi chưa COMMIT của phiên khác.
C. Cả transaction dùng snapshot chốt từ khi kết nối.
D. Mỗi lệnh dùng snapshot riêng khi lệnh đó bắt đầu.
Đáp án đúng: D

18. PostgreSQL REPEATABLE READ cấp bảo đảm nào với giao dịch nhiều câu lệnh?
A. Tạo snapshot mới ở mỗi SELECT để tránh write skew.
B. Giữ snapshot chung nhưng vẫn có thể gặp write skew.
C. Khóa mọi bảng đã đọc nên không có write skew.
D. Bảo đảm tương đương SERIALIZABLE cho mọi trường hợp.
Đáp án đúng: B

19. Khi transaction SERIALIZABLE thất bại với SQLSTATE 40001, ứng dụng nên xử lý thế nào?
A. Retry riêng SELECT cuối sau lỗi serialization_failure.
B. Bỏ qua lỗi và COMMIT phần ghi còn lại của transaction.
C. Chỉ chạy VACUUM bảng trước khi COMMIT lại transaction.
D. Retry toàn transaction khi gặp serialization_failure (40001).
Đáp án đúng: D

20. UPDATE trong PostgreSQL MVCC ảnh hưởng tới phiên bản dòng như thế nào?
A. Ghi đè phiên bản cũ ngay và mọi SELECT đều thấy dữ liệu mới.
B. Xóa phiên bản cũ ngay khi lệnh UPDATE được thực thi.
C. Sinh phiên bản dòng mới, giữ bản cũ cho snapshot cần thiết.
D. Khóa toàn bộ bảng đến khi VACUUM xử lý mọi phiên bản.
Đáp án đúng: C

21. SELECT ... FOR UPDATE trong một transaction tác động tới truy cập song song thế nào?
A. Khóa dòng đã chọn trước các thao tác ghi tranh chấp.
B. Chặn cả SELECT thông thường trên mọi dòng đã chọn.
C. Khóa toàn bộ bảng để ngăn truy cập đọc từ phiên khác.
D. Giữ khóa dòng kể cả sau khi transaction đã COMMIT.
Đáp án đúng: A

22. Nhiều worker tranh nhau nhận task ở bảng queue. Cú pháp nào bỏ qua task đã bị khóa?
A. SELECT ... FOR UPDATE NOWAIT tự bỏ qua mọi dòng khóa.
B. SELECT ... FOR SHARE SKIP LOCKED ghi trạng thái nhận task.
C. SELECT ... FOR UPDATE SKIP LOCKED để bỏ qua dòng khóa.
D. SELECT ... DISTINCT ON để bỏ qua dòng có row lock.
Đáp án đúng: C

23. PostgreSQL phát hiện hai transaction chờ khóa lẫn nhau. Hệ thống xử lý gì?
A. Hủy một transaction để phá vòng chờ deadlock.
B. Cho hai transaction tự COMMIT mà bỏ qua khóa.
C. Khóa mọi bảng liên quan cho tới khi cả hai kết thúc.
D. Chuyển hai transaction sang READ UNCOMMITTED để tiếp tục.
Đáp án đúng: A

24. Một transaction có savepoint s1, thao tác sau đó lỗi; muốn hủy phần sau s1 nhưng giữ phần trước. Dùng gì?
A. ROLLBACK toàn transaction rồi tiếp tục chạy phần trước.
B. ROLLBACK TO SAVEPOINT s1 để hoàn tác phần sau mốc.
C. RELEASE SAVEPOINT s1 để hoàn tác phần sau mốc.
D. COMMIT SAVEPOINT s1 để ghi bền riêng phần trước mốc.
Đáp án đúng: B

25. Chỉ mục mặc định nào phù hợp khi cột được lọc bằng và theo khoảng, dữ liệu phân bố thông thường?
A. GIN cho toán tử so sánh bằng và phép so sánh khoảng.
B. Hash cho toán tử so sánh bằng và phép so sánh khoảng.
C. BRIN cho toán tử so sánh bằng và phép so sánh khoảng.
D. B-tree cho toán tử so sánh bằng và phép so sánh khoảng.
Đáp án đúng: D

26. Truy vấn lọc tenant_id = ... và created_at BETWEEN ... rồi ORDER BY created_at. B-tree nào có lợi thế?
A. B-tree trên (created_at, tenant_id) theo thứ tự đó.
B. B-tree trên (status, created_at) theo thứ tự đó.
C. B-tree (tenant_id, created_at) là thứ tự phù hợp.
D. B-tree trên (tenant_id, status) theo thứ tự đó.
Đáp án đúng: C

27. Cột search_vector kiểu tsvector thường được truy vấn với @@ tsquery. Chọn index nào?
A. GIN trên search_vector để tăng tốc truy vấn full-text.
B. B-tree trên search_vector để tăng tốc truy vấn full-text.
C. Hash trên search_vector để tăng tốc truy vấn full-text.
D. BRIN trên search_vector để tăng tốc truy vấn full-text.
Đáp án đúng: A

28. Chỉ 2% ticket ở trạng thái open và thường truy vấn open theo owner_id. Index nào gọn?
A. Partial index ON tickets(owner_id) WHERE status='closed'.
B. Index thường ON tickets(status) cho toàn bộ trạng thái.
C. Partial index ON tickets(owner_id) WHERE status='open'.
D. Index thường ON tickets(created_at) cho toàn bộ trạng thái.
Đáp án đúng: C

29. Đọc status theo customer_id thường xuyên, muốn index chứa đủ hai giá trị nhưng chỉ lọc theo customer_id. Chọn gì?
A. INDEX (status) INCLUDE (customer_id) trên bảng cần đọc.
B. INDEX (customer_id, created_at) trên bảng cần đọc.
C. INDEX (status, created_at) trên bảng cần đọc.
D. INDEX (customer_id) INCLUDE (status) cho truy vấn.
Đáp án đúng: D

30. Tạo index lớn trên bảng vẫn có nhiều ghi, muốn giảm chặn thao tác INSERT/UPDATE. Chọn gì?
A. CREATE INDEX thông thường và chạy trong transaction block.
B. CREATE INDEX CONCURRENTLY và chạy trong transaction block.
C. REINDEX thông thường rồi chạy ngoài transaction block.
D. CREATE INDEX CONCURRENTLY chạy ngoài transaction block.
Đáp án đúng: D

31. EXPLAIN (ANALYZE, BUFFERS) giúp đọc hiệu năng một SELECT như thế nào?
A. Chạy câu lệnh và báo thời gian thực cùng thông tin buffer.
B. Chỉ lập kế hoạch ước lượng, không chạy câu lệnh được hỏi.
C. Chỉ liệt kê thông tin index hiện có, không chạy câu lệnh.
D. Chỉ xem lịch sử lock và wait event của phiên kết nối.
Đáp án đúng: A

32. Planner ước lượng sai số dòng sau nhiều lần cập nhật dữ liệu. Thao tác nào giúp thống kê mới hơn?
A. ANALYZE để cập nhật thống kê phân bố của dữ liệu.
B. REINDEX để cập nhật thống kê phân bố của dữ liệu.
C. CHECKPOINT để cập nhật thống kê phân bố của dữ liệu.
D. VACUUM FULL để cập nhật thống kê phân bố của dữ liệu.
Đáp án đúng: A

33. Write-ahead logging bảo đảm thứ tự ghi bền nào trước khi ghi trang dữ liệu thay đổi?
A. Trang dữ liệu được flush trước WAL liên quan đến thay đổi.
B. WAL liên quan được flush trước trang dữ liệu chứa thay đổi.
C. WAL chỉ flush sau khi CHECKPOINT đã ghi toàn bộ trang bẩn.
D. WAL chỉ được tạo sau khi VACUUM hoàn tất thu hồi tuple.
Đáp án đúng: B

34. CHECKPOINT tác động thế nào tới I/O của PostgreSQL khi cấu hình quá thường xuyên?
A. Xóa mọi WAL; chạy dày luôn làm I/O giảm rõ rệt.
B. Đẩy trang bẩn ra đĩa; chạy dày có thể tăng I/O.
C. Dọn dead tuple; chạy dày thay thế được VACUUM.
D. Chỉ ghi metadata; chạy dày không đụng trang dữ liệu.
Đáp án đúng: B

35. VACUUM thông thường xử lý dead tuple và dung lượng bảng theo cách nào?
A. Chỗ trống tái dùng, tệp thường không thu nhỏ ngay.
B. Luôn hoàn trả không gian tệp trống ngay cho hệ điều hành.
C. Luôn tạo bản sao bảng mới rồi bỏ tệp bảng cũ.
D. Xóa toàn bộ index để xây lại bảng từ đầu.
Đáp án đúng: A

36. Autovacuum phục vụ những công việc chính nào khi cơ sở dữ liệu hoạt động lâu dài?
A. Chỉ tạo index mới và phân vùng lại những bảng lớn.
B. Dọn dead tuple, ANALYZE và hạn chế XID wraparound.
C. Chỉ chép WAL và giữ bản sao tại một standby node.
D. Chỉ khóa bảng lúc backup và kiểm tra cấu trúc SQL.
Đáp án đúng: B

37. VACUUM FREEZE giúp giảm nguy cơ nào khi transaction ID tiếp tục tăng?
A. Khóa tuple mới để ngăn transaction ID wraparound.
B. Freeze tuple cũ để ngăn transaction ID wraparound.
C. Thu nhỏ WAL để tránh số segment tăng theo thời gian.
D. Ghi lại mọi index để tránh B-tree bị phân mảnh.
Đáp án đúng: B

38. Vì sao transaction đọc mở rất lâu có thể làm dead tuple tích tụ?
A. Snapshot cũ giúp VACUUM thu hồi tuple nhanh hơn bình thường.
B. Snapshot cũ buộc CHECKPOINT phải xóa dữ liệu mới trên đĩa.
C. Snapshot cũ khiến tất cả index tạm dừng cập nhật dữ liệu.
D. Snapshot cũ còn cần phiên bản nên VACUUM chưa thu hồi.
Đáp án đúng: D

39. Chạy pg_dump -Fc để sao lưu một database. Định dạng kết quả phục hồi phù hợp là gì?
A. Bản sao vật lý dạng cluster, khôi phục bằng pg_basebackup.
B. Bản sao WAL liên tục, khôi phục bằng restore_command.
C. Bản sao logic dạng custom, khôi phục bằng pg_restore.
D. Bản sao replica standby, khôi phục bằng streaming WAL.
Đáp án đúng: C

40. Đã có base backup và WAL archive đầy đủ, muốn quay về thời điểm trước lệnh xóa nhầm. Cách nào đúng?
A. Base backup rồi replay WAL tới recovery_target_time.
B. Phục hồi pg_dump và replay WAL đến recovery_target_time.
C. Chạy VACUUM FULL và replay WAL đến recovery_target_time.
D. Chạy ANALYZE và replay WAL đến recovery_target_time.
Đáp án đúng: A

41. pg_basebackup chủ yếu tạo loại dữ liệu nào để dựng standby PostgreSQL?
A. Bản sao câu lệnh INSERT theo thứ tự khóa chính.
B. Bản sao từng bảng sang tệp CSV dùng để import.
C. Bản sao vật lý cluster, có thể kèm WAL cần thiết.
D. Bản sao chỉ gồm role và quyền truy cập toàn cluster.
Đáp án đúng: C

42. Trong streaming physical replication, standby nhận thay đổi từ primary thế nào?
A. Nhận DDL dạng SQL rồi thực hiện theo lịch định kỳ.
B. Nhận và replay WAL, có thể chậm hơn dữ liệu primary.
C. Tự COMMIT mọi lệnh ghi rồi chuyển dữ liệu ngược về primary.
D. Chỉ nhận những bảng được khai báo trong publication.
Đáp án đúng: B

43. Logical replication qua publication/subscription có giới hạn nào đáng lưu ý?
A. Chuyển đầy đủ role và DDL cùng các thay đổi dòng.
B. Chỉ hoạt động khi có bản sao vật lý của toàn cluster.
C. Luôn replay WAL vật lý giống streaming replication.
D. Chuyển thay đổi dòng; không tự đồng bộ phần lớn DDL.
Đáp án đúng: D

44. Replication slot trên primary có thể gây vấn đề gì khi consumer bị chậm rất lâu?
A. Xóa WAL chưa gửi, làm consumer thiếu dữ liệu cần thiết.
B. Tự động giảm số replica khi replay tiến độ không đồng đều.
C. Chặn toàn bộ giao dịch ghi ngay cả khi async mode bật.
D. Giữ WAL chưa được tiêu thụ khiến đĩa primary tăng dùng.
Đáp án đúng: D

45. Cấu hình synchronous replication có thể ảnh hưởng độ trễ COMMIT thế nào?
A. COMMIT không đợi standby nên luôn giảm độ trễ so với async.
B. COMMIT chờ xác nhận standby tùy chế độ, tăng độ trễ.
C. COMMIT chỉ chờ khi client đang đọc trên primary node.
D. COMMIT đợi pg_dump kết thúc trước khi phản hồi ứng dụng.
Đáp án đúng: B

46. Cần xác định ai đang chặn transaction vì khóa. Nên kiểm tra các nguồn nào?
A. pg_stat_activity cùng pg_locks để tìm phiên chặn.
B. Ghép pg_roles với pg_tables để tìm phiên đang chặn.
C. Ghép pg_database với pg_type để tìm phiên đang chặn.
D. Ghép pg_indexes với pg_class để tìm phiên đang chặn.
Đáp án đúng: A

47. Muốn tìm nhóm SQL tốn tổng thời gian nhất qua nhiều lần gọi, có extension đã bật. Nên xem gì?
A. pg_stat_statements cho tổng lượt và thời gian SQL.
B. pg_stat_activity chỉ lưu mọi lần gọi lịch sử của câu SQL.
C. pg_locks lưu tổng thời gian CPU của mỗi nhóm câu SQL.
D. pg_roles lưu số lần chạy và thời gian của mọi câu SQL.
Đáp án đúng: A

48. pg_hba.conf quyết định quy tắc xác thực kết nối theo những thông tin nào?
A. Loại index, database, schema, bảng và kiểu dữ liệu.
B. Loại WAL, timeline, checkpoint, slot và archive directory.
C. Loại kết nối, database, user, địa chỉ và kiểu xác thực.
D. Loại câu SQL, query ID, mức CPU, địa chỉ và thời gian chạy.
Đáp án đúng: C
