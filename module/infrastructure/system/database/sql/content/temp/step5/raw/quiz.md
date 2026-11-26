Câu 1. Muốn chỉ đọc hai cột `id` và `name` từ customers, câu SQL nào đúng?
A. `SELECT id, name FROM customers`
B. `SELECT customers FROM id, name`
C. `SELECT id AND name FROM customers`
D. `SELECT FROM customers id, name`
Đáp án đúng: A

Câu 2. Bảng customers có nhiều dòng cùng city; câu nào lấy các city không trùng?
A. `SELECT city FROM customers`
B. `SELECT DISTINCT city, id FROM customers`
C. `SELECT DISTINCT city FROM customers`
D. `SELECT ALL city FROM customers`
Đáp án đúng: C

Câu 3. Mệnh đề nào lọc từng dòng trước khi dữ liệu được GROUP BY?
A. Dùng `GROUP BY` để lọc từng dòng dữ liệu
B. Dùng `WHERE` để lọc từng dòng dữ liệu
C. Dùng `HAVING` để lọc từng dòng dữ liệu
D. Dùng `ORDER BY` để lọc từng dòng dữ liệu
Đáp án đúng: B

Câu 4. Muốn tìm dòng có `deleted_at` là SQL NULL, điều kiện nào đúng?
A. `deleted_at = NULL`
B. `deleted_at IN (NULL)`
C. `deleted_at IS NULL`
D. `deleted_at LIKE NULL`
Đáp án đúng: C

Câu 5. Với SQL LIKE, điều kiện nào khớp mọi name bắt đầu bằng `An`?
A. `name LIKE 'An_'`
B. `name LIKE 'An%'`
C. `name LIKE '%An'`
D. `name LIKE '%An%'`
Đáp án đúng: B

Câu 6. Muốn sắp created_at từ mới nhất đến cũ nhất, viết thế nào?
A. `ORDER BY created_at ASC`
B. `ORDER BY created_at DESC`
C. `ORDER BY created_at`
D. `ORDER BY created_at, id`
Đáp án đúng: B

Câu 7. Trong SQL chuẩn, `score BETWEEN 10 AND 20` bao gồm giá trị biên nào?
A. Chỉ 20 được tính vào khoảng
B. Cả 10 và 20 đều bị loại
C. Cả 10 và 20 đều được tính
D. Chỉ 10 được tính vào khoảng
Đáp án đúng: C

Câu 8. Điều kiện nào lọc status bằng `new` hoặc `paid` theo một danh sách?
A. `status BETWEEN 'new' AND 'paid'`
B. `status = ('new', 'paid')`
C. `status LIKE ('new', 'paid')`
D. `status IN ('new', 'paid')`
Đáp án đúng: D

Câu 9. INNER JOIN theo điều kiện khóa trả về tập dòng nào?
A. Chỉ các cặp hàng khớp điều kiện JOIN
B. Mọi hàng bên phải dù không có bản ghi khớp
C. Tất cả cặp hàng bất kể điều kiện JOIN
D. Mọi hàng bên trái dù không có bản ghi khớp
Đáp án đúng: A

Câu 10. LEFT JOIN giữ những dòng nào khi hai bảng không có hàng khớp?
A. Chỉ giữ các hàng không khớp ở hai bảng
B. Giữ mọi hàng bảng phải, phần trái có thể NULL
C. Chỉ giữ cặp hàng có khóa khớp ở hai bảng
D. Giữ mọi hàng bảng trái, phần phải có thể NULL
Đáp án đúng: D

Câu 11. Với a.id và b.a_id là các khóa không NULL, phép nối nào tìm a không có b tương ứng?
A. `LEFT JOIN b ON a.id=b.a_id WHERE b.a_id IS NULL`
B. `LEFT JOIN b ON a.id=b.a_id WHERE b.a_id IS NOT NULL`
C. `INNER JOIN b ON a.id=b.a_id WHERE b.a_id IS NULL`
D. `INNER JOIN b ON a.id=b.a_id WHERE b.a_id IS NOT NULL`
Đáp án đúng: A

Câu 12. Một customer có ba orders; INNER JOIN customers với orders theo customer_id tạo bao nhiêu dòng cho khách đó?
A. Ba dòng, tương ứng ba đơn hàng
B. Hai dòng, do chỉ cần hai khóa nối
C. Bốn dòng, cộng thêm dòng khách gốc
D. Một dòng, mỗi khách chỉ một dòng
Đáp án đúng: A

Câu 13. Muốn tính SUM(amount) theo từng category, thành phần nào cần dùng?
A. `GROUP BY amount`
B. `ORDER BY category`
C. `PARTITION BY category`
D. `GROUP BY category`
Đáp án đúng: D

Câu 14. Sau GROUP BY, muốn chỉ giữ nhóm có SUM(amount) > 100, dùng gì?
A. `ORDER BY SUM(amount) > 100`
B. `HAVING SUM(amount) > 100`
C. `GROUP BY SUM(amount) > 100`
D. `WHERE SUM(amount) > 100`
Đáp án đúng: B

Câu 15. Với các giá trị x: 1, NULL, 2, `COUNT(x)` trả về điều gì?
A. 0 vì có giá trị NULL trong cột
B. 2 vì chỉ đếm x khác NULL
C. 3 vì đếm tất cả các hàng
D. 1 vì chỉ đếm giá trị 1
Đáp án đúng: B

Câu 16. Muốn đếm user_id phân biệt và bỏ qua NULL, biểu thức nào thích hợp?
A. Dùng `COUNT(ALL user_id)`
B. Dùng `COUNT(user_id)` trực tiếp
C. Dùng `COUNT(DISTINCT user_id)`
D. Dùng `SUM(DISTINCT user_id)`
Đáp án đúng: C

Câu 17. Với x có các giá trị 10, 20, NULL, `AVG(x)` cho kết quả nào?
A. NULL, vì có một giá trị NULL
B. 15, vì bỏ qua giá trị NULL
C. 10, vì xem NULL như số 0
D. 30, vì cộng các số khác NULL
Đáp án đúng: B

Câu 18. Từ khóa nào bắt đầu một common table expression (CTE)?
A. `VIEW recent AS (...)`
B. `JOIN recent AS (...)`
C. `FROM recent AS (...)`
D. `WITH recent AS (...)`
Đáp án đúng: D

Câu 19. Recursive CTE thường dùng với cấu trúc dữ liệu nào?
A. Bảng thống kê có tổng đã tính sẵn
B. Bảng cache chỉ truy xuất theo khóa
C. Bảng lookup chỉ có một khóa chính
D. Cây phân cấp có quan hệ cha–con
Đáp án đúng: D

Câu 20. Biểu thức nào đúng khi cần kiểm tra subquery trả ít nhất một dòng?
A. `EXISTS (SELECT 1 FROM ...)`
B. `ANY (SELECT 1 FROM ...)`
C. `IN (SELECT 1 FROM ...)`
D. `ALL (SELECT 1 FROM ...)`
Đáp án đúng: A

Câu 21. Kết hợp hai kết quả SELECT và muốn giữ nguyên dòng trùng, dùng gì?
A. Dùng toán tử `INTERSECT`
B. Dùng toán tử `UNION ALL`
C. Dùng toán tử `EXCEPT`
D. Dùng toán tử `UNION`
Đáp án đúng: B

Câu 22. Muốn đánh số hàng theo salary giảm dần, bắt đầu lại ở mỗi department_id, dùng gì?
A. `ROW_NUMBER() OVER (PARTITION BY department_id ORDER BY salary ASC)`
B. `ROW_NUMBER() OVER (ORDER BY department_id, salary DESC)`
C. `ROW_NUMBER() OVER (PARTITION BY salary ORDER BY department_id)`
D. `ROW_NUMBER() OVER (PARTITION BY department_id ORDER BY salary DESC)`
Đáp án đúng: D

Câu 23. Với lương 100,100,90 giảm dần, `RANK()` trả thứ hạng nào?
A. 1,1,2 vì không bỏ vị trí sau hòa
B. 1,2,3 vì mỗi hàng một thứ hạng
C. 1,1,3 vì bỏ vị trí sau hòa
D. 1,2,2 vì hòa ở các vị trí cuối
Đáp án đúng: C

Câu 24. Với lương 100,100,90 giảm dần, `DENSE_RANK()` trả thứ hạng nào?
A. 1,1,2 vì không bỏ bậc sau hòa
B. 1,2,3 vì gán thứ tự mỗi hàng
C. 1,2,2 vì hòa ở hai vị trí cuối
D. 1,1,3 vì có khoảng trống sau hòa
Đáp án đúng: A

Câu 25. Điểm khác biệt quan trọng giữa window aggregate và GROUP BY thường là gì?
A. Giữ các hàng gốc và tính giá trị cửa sổ
B. Gộp các hàng gốc thành một hàng cho mỗi nhóm
C. Chỉ đọc cột dùng làm khóa trong phép nối
D. Chỉ xử lý các hàng đã cập nhật bằng DML
Đáp án đúng: A

Câu 26. Muốn cộng dồn theo thời gian trong cửa sổ đã ORDER BY timestamp, ROWS frame nào phù hợp?
A. `ROWS BETWEEN 1 PRECEDING AND CURRENT ROW`
B. `ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING`
C. `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`
D. `ROWS BETWEEN CURRENT ROW AND 1 FOLLOWING`
Đáp án đúng: C

Câu 27. Câu SQL nào thêm khách hàng id=7, name='Lan' vào hai cột tương ứng?
A. `MERGE INTO customers(id,name) VALUES(7,'Lan')`
B. `INSERT customers(id,name) VALUES(7,'Lan')`
C. `UPDATE customers(id,name) VALUES(7,'Lan')`
D. `INSERT INTO customers(id,name) VALUES(7,'Lan')`
Đáp án đúng: D

Câu 28. Muốn cập nhật status='paid' cho order id=5, câu SQL nào giới hạn đúng dòng?
A. `UPDATE orders SET status='paid' WHERE id=5`
B. `UPDATE orders SET status='paid'`
C. `UPDATE orders WHERE id=5 SET status='paid'`
D. `ALTER orders SET status='paid' WHERE id=5`
Đáp án đúng: A

Câu 29. Câu SQL nào chỉ xóa order có id=5?
A. `DROP FROM orders WHERE id=5`
B. `DELETE orders WHERE id=5`
C. `DELETE FROM orders WHERE id=5`
D. `TRUNCATE orders WHERE id=5`
Đáp án đúng: C

Câu 30. DDL nào khai báo một bảng customers mới?
A. `ALTER TABLE customers (...)`
B. `INSERT INTO customers (...)`
C. `CREATE TABLE customers (...)`
D. `CREATE VIEW customers (...)`
Đáp án đúng: C

Câu 31. Thao tác DDL nào bổ sung cột vào một bảng đang tồn tại?
A. Dùng `CREATE INDEX` với mệnh đề thêm cột
B. Dùng `DELETE FROM` với mệnh đề thêm cột
C. Dùng `UPDATE TABLE` với mệnh đề thêm cột
D. Dùng `ALTER TABLE` với mệnh đề thêm cột
Đáp án đúng: D

Câu 32. PRIMARY KEY theo SQL chuẩn có thuộc tính nào?
A. Giá trị duy nhất và không được NULL
B. Giá trị tự tăng trên mọi hệ quản trị
C. Giá trị duy nhất nhưng được phép NULL
D. Giá trị trùng nhau nếu các hàng khác
Đáp án đúng: A

Câu 33. FOREIGN KEY chủ yếu đảm bảo điều gì trong quan hệ hai bảng?
A. Giá trị trong cột phải được mã hóa trước khi ghi
B. Giá trị trong cột phải khác mọi cột cùng bảng
C. Giá trị trong cột phải tăng dần theo thời gian
D. Giá trị tham chiếu phải hợp lệ theo khóa đích
Đáp án đúng: D

Câu 34. CHECK (quantity >= 0) chủ yếu ngăn trường hợp nào?
A. Ghi hoặc cập nhật giá trị quantity âm
B. Đặt quantity bằng một giá trị từ sequence
C. Để quantity trùng với khóa chính của bảng
D. Ghi quantity là NULL trên mọi hệ quản trị
Đáp án đúng: A

Câu 35. Trong giao dịch đang mở, lệnh `COMMIT` thường có tác dụng gì?
A. Hoàn tác các thay đổi của giao dịch
B. Chỉ tạo điểm lưu trong giao dịch
C. Xác nhận các thay đổi của giao dịch
D. Đổi mức cô lập của giao dịch hiện tại
Đáp án đúng: C

Câu 36. Trong giao dịch đang mở, `ROLLBACK` toàn giao dịch thực hiện điều gì?
A. Tạo một savepoint để quay lại sau
B. Hoàn tác các thay đổi chưa commit
C. Chuyển giao dịch sang chế độ chỉ đọc
D. Lưu vĩnh viễn các thay đổi vừa ghi
Đáp án đúng: B

Câu 37. Trong ACID, atomicity của transaction có nghĩa gì?
A. Mọi transaction đều đọc dữ liệu mới nhất
B. Mỗi transaction chạy độc lập trên một CPU
C. Toàn bộ thay đổi cùng thành công hoặc cùng hủy
D. Thứ tự transaction không bao giờ thay đổi
Đáp án đúng: C

Câu 38. Mức cô lập READ COMMITTED theo SQL chuẩn ngăn hiện tượng nào?
A. Đọc thêm hàng thỏa điều kiện truy vấn cũ
B. Đọc dữ liệu chưa được transaction khác commit
C. Hai transaction cùng muốn cập nhật một hàng
D. Đọc lại cùng hàng thấy giá trị đã thay đổi
Đáp án đúng: B

Câu 39. Có index B-tree (tenant_id, created_at), bộ lọc nào tận dụng tiền tố chỉ mục tốt nhất?
A. `WHERE status = 'paid'`
B. `WHERE tenant_id = 7`
C. `WHERE created_at >= 7`
D. `WHERE amount > 100`
Đáp án đúng: B

Câu 40. Muốn xem kế hoạch thực thi SQL trước khi tối ưu SELECT, dùng gì?
A. Dùng `ANALYZE` để tạo thống kê cột
B. Dùng `VACUUM` để xử lý dữ liệu chết
C. Dùng `COMMIT` để kết thúc giao dịch
D. Dùng `EXPLAIN` để xem kế hoạch truy vấn
Đáp án đúng: D

Câu 41. Muốn giảm SQL injection khi lọc theo email người dùng nhập, nên làm gì?
A. Kiểm tra độ dài rồi nối email vào SQL
B. Nối chuỗi email vào văn bản SQL trực tiếp
C. Thay khoảng trắng trong email trước khi nối
D. Sử dụng placeholder và bind parameter
Đáp án đúng: D

Câu 42. Trước UPDATE nhiều hàng, cách nào giảm nguy cơ sửa sai phạm vi?
A. Xóa khóa chính rồi chạy UPDATE trên bảng
B. Chạy SELECT với cùng điều kiện WHERE trước
C. Tắt constraint trước khi UPDATE hàng loạt
D. Bỏ WHERE và dựa vào transaction để giới hạn
Đáp án đúng: B

Câu 43. Khi hỗ trợ nhiều hệ quản trị SQL, phần nào dễ cần điều chỉnh nhất?
A. Cú pháp upsert và kiểu dữ liệu đặc thù
B. Điều kiện bằng của biểu thức so sánh
C. Dấu phẩy phân cách các cột SELECT
D. Cú pháp SELECT và tên cột theo chuẩn
Đáp án đúng: A

Câu 44. Thêm chỉ mục phụ trên bảng ghi nhiều thường tạo đánh đổi nào?
A. SELECT không đổi và INSERT không chịu ảnh hưởng
B. SELECT luôn nhanh hơn và INSERT luôn nhanh hơn
C. SELECT có thể nhanh hơn nhưng INSERT tốn thêm chi phí
D. SELECT luôn chậm hơn nhưng INSERT nhanh hơn
Đáp án đúng: C
