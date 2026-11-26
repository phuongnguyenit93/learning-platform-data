Trong JDBC, vai trò chính của database driver là gì?
A. Quản lý trực tiếp toàn bộ giao diện người dùng
B. Tạo migration schema trước mỗi câu truy vấn
C. Kết nối lời gọi JDBC với giao thức của database
D. Tự chuyển mọi SQL thành truy vấn không cần index
Đáp án đúng: C

Với dịch vụ nhận nhiều request, DataSource thường được ưu tiên vì lý do nào?
A. Tự đồng bộ mọi câu lệnh vào cùng transaction
B. Tự tối ưu execution plan ở mỗi lần gọi SQL
C. Không còn cần đóng Connection sau mỗi request
D. Hỗ trợ cấu hình và tích hợp pool kết nối
Đáp án đúng: D

PreparedStatement với placeholder `?` bảo vệ tham số người dùng theo cách nào?
A. Tự mã hóa mọi giá trị đầu vào bằng cùng một khóa
B. Tạo SQL mới bằng cách nối trực tiếp chuỗi tham số
C. Bind giá trị riêng với cấu trúc câu lệnh SQL
D. Tự kiểm tra mọi quy tắc nghiệp vụ trước khi ghi
Đáp án đúng: C

Sau khi gọi executeQuery(), thao tác ResultSet.next() làm gì?
A. Tiến đến hàng kế và báo còn hàng hay không
B. Đóng cursor và trả lại Connection cho pool
C. Chuyển sang cột đầu tiên của hàng hiện tại
D. Chuyển kết quả thành một List tự động
Đáp án đúng: A

Dùng try-with-resources với Connection và Statement có ích gì?
A. Tự commit mọi transaction dù có exception
B. Tự đóng các tài nguyên khi ra khỏi scope
C. Tự retry câu SQL khi có lỗi mạng tạm thời
D. Tự chọn index cho truy vấn đang thực thi
Đáp án đúng: B

Muốn ba lệnh ghi thuộc một transaction JDBC, bước nào phù hợp?
A. Tắt auto-commit; commit hoặc rollback cả nhóm
B. Bật auto-commit để mỗi lệnh tạo một transaction
C. Chỉ sử dụng Statement thay cho PreparedStatement
D. Giữ ResultSet mở sau khi hoàn tất ba lệnh ghi
Đáp án đúng: A

Mức cô lập READ COMMITTED của transaction có tính chất nào?
A. Cho phép đọc các thay đổi chưa được commit
B. Luôn ngăn phantom read ở mọi database engine
C. Luôn bảo đảm hai lần đọc cùng một giá trị
D. Ngăn dirty read từ giao dịch chưa commit
Đáp án đúng: D

Với nhiều lần INSERT cùng cấu trúc SQL, cách dùng JDBC nào giảm số lần gửi lệnh?
A. Gọi executeQuery cho từng lần thêm một hàng
B. Dùng addBatch và executeBatch trên cùng lệnh
C. Dùng getMetaData sau mỗi lệnh để cache schema
D. Tạo mỗi INSERT trong một Connection riêng
Đáp án đúng: B

Với PreparedStatement, cách bind giá trị SQL NULL cho cột INTEGER là gì?
A. Gọi setString(index, "null") để bind chuỗi rỗng
B. Dùng setInt(index, 0) và xem 0 là NULL
C. Bỏ placeholder khỏi câu SQL trước khi chạy
D. Dùng setNull(index, Types.INTEGER) phù hợp
Đáp án đúng: D

Khi lấy Connection từ connection pool, gọi close() thường có ý nghĩa gì?
A. Đóng toàn bộ pool và ngắt mọi phiên đang chạy
B. Chặn mọi request mới đến ứng dụng Java
C. Trả kết nối về pool theo hợp đồng của pool
D. Luôn xóa dữ liệu transaction khỏi server
Đáp án đúng: C

Khi phân loại lỗi JDBC, thông tin nào của SQLException đặc biệt hữu ích?
A. SQLState và mã lỗi từ nhà cung cấp database
B. Tên Java package của lớp đang thực thi SQL
C. Số lượng dòng của đoạn mã gọi executeQuery
D. Tên worker thread đã tạo PreparedStatement
Đáp án đúng: A

Câu SQL UPDATE cần biết số hàng bị tác động, API JDBC nào phù hợp?
A. executeUpdate trả số hàng được DB báo là tác động
B. executeQuery trả một ResultSet chứa mỗi hàng đã sửa
C. getResultSet trả về toàn bộ khóa của hàng bị cập nhật
D. clearBatch trả về số hàng trong thao tác cuối
Đáp án đúng: A

Sau INSERT tự sinh khóa, JDBC có thể lấy khóa tạo mới bằng cách nào?
A. Gọi getWarnings sau khi hoàn tất mọi lệnh INSERT
B. Yêu cầu trả khóa rồi đọc từ getGeneratedKeys
C. Dùng ResultSet.next trước khi thực thi INSERT
D. Đọc DatabaseMetaData để tìm khóa mới nhất
Đáp án đúng: B

Một transaction đã cập nhật một bảng rồi lệnh sau báo lỗi, cách xử lý nào đúng?
A. Commit ngay phần đầu để giữ lại thay đổi đã ghi
B. Thử lại riêng lệnh cuối với auto-commit bật
C. Đóng ResultSet mà không quan tâm trạng thái ghi
D. Rollback transaction trước khi xử lý hoặc báo lỗi
Đáp án đúng: D

Khi ResultSet.getInt trả 0, làm sao biết giá trị SQL thực tế là NULL?
A. So sánh số 0 với giá trị mặc định của Java
B. Đọc lại cùng cột bằng getString rồi đoán
C. Gọi wasNull sau khi đọc cột để xác nhận
D. Đọc số cột bằng ResultSetMetaData để suy ra
Đáp án đúng: C

Để giảm dữ liệu gửi qua mạng trong một truy vấn JDBC, thay đổi nào trực tiếp hữu ích?
A. Luôn dùng SELECT * cho mọi bảng được truy vấn
B. Chỉ chọn cột cần dùng và giới hạn số hàng
C. Tắt mọi index dù câu SQL lọc theo khóa
D. Lấy toàn bộ hàng rồi lọc lại trong ứng dụng
Đáp án đúng: B
