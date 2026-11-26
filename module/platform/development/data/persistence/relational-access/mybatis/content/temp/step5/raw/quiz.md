Khác biệt thực dụng của MyBatis với ORM tự sinh SQL là gì?
A. Chỉ tạo schema từ các entity đã gắn annotation
B. Cấm chạy SQL khi chưa định nghĩa lớp entity Java
C. Tự chuyển mọi truy vấn sang HQL của Hibernate
D. Tự viết SQL rồi ánh xạ kết quả về Java
Đáp án đúng: D

Mapper interface trong MyBatis chủ yếu dùng để làm gì?
A. Thay hoàn toàn driver JDBC của cơ sở dữ liệu
B. Gắn phương thức Java với câu SQL đã cấu hình
C. Tạo transaction riêng cho từng cột được đọc
D. Tự chuyển class thành bảng khi ứng dụng khởi động
Đáp án đúng: B

Trong câu SQL MyBatis, cú pháp `#{userId}` có tác dụng nào?
A. Bind giá trị tham số qua PreparedStatement
B. Chèn nguyên văn giá trị vào tên bảng hoặc cột
C. Đổi tên trường Java thành tên cột trong resultMap
D. Buộc driver mở transaction trước khi truy vấn
Đáp án đúng: A

Nếu dùng `${sortColumn}` từ dữ liệu người dùng, nguy cơ nào phải xử lý?
A. Giá trị tự được bind như tham số có kiểu JDBC
B. Chèn text vào SQL nên phải kiểm soát đầu vào
C. Giá trị bị MyBatis biến thành chuỗi đã mã hóa
D. Cột sẽ được MyBatis tự đổi sang tên Java property
Đáp án đúng: B

Khi tên cột và thuộc tính Java khác nhau, resultMap giúp giải quyết điều gì?
A. Chỉ xác định timeout cho toàn bộ statement
B. Chỉ định DataSource cho từng row được trả về
C. Ánh xạ cột vào property và object lồng nhau
D. Thực thi lệnh tạo bảng cho mọi class Java
Đáp án đúng: C

Muốn thêm điều kiện lọc SQL chỉ khi tham số khác null, phần tử nào phù hợp?
A. Dùng thẻ `<if>` với biểu thức kiểm tra tham số
B. Dùng `resultMap` để quyết định có thêm WHERE
C. Dùng `TypeHandler` để sinh nguyên câu SELECT
D. Dùng `SqlSession` để nối SQL qua phép cộng chuỗi
Đáp án đúng: A

Thẻ `<where>` trong dynamic SQL hỗ trợ trường hợp nào?
A. Luôn thêm WHERE kể cả khi không có điều kiện
B. Chỉ thêm ORDER BY sau phần truy vấn SELECT
C. Thêm WHERE khi cần và xử lý AND/OR đứng đầu
D. Ép mọi biến dùng `${}` thay cho `#{}`
Đáp án đúng: C

Cách sử dụng SqlSession nào giúp tránh rủi ro chia sẻ trạng thái?
A. Dùng SqlSession singleton cho mọi request trong ứng dụng
B. Cho nhiều thread cùng gọi một SqlSession chung
C. Dùng cùng SqlSession đến khi process bị dừng
D. Giới hạn session theo tác vụ, không chia sẻ đa luồng
Đáp án đúng: D

Khi ứng dụng MyBatis tự quản lý SqlSession và transaction, điều gì cần làm?
A. Mặc định mọi lệnh đều tự commit ngay lập tức
B. Commit hoặc rollback transaction phù hợp
C. Đóng ResultSet là đủ để xác nhận transaction
D. Tạo một session khác rồi quên session đang mở
Đáp án đúng: B

Cache cấp một mặc định của MyBatis gắn với phạm vi nào?
A. Toàn bộ các ứng dụng dùng cùng một database
B. Mọi node cơ sở dữ liệu thuộc cùng một cluster
C. Trong các truy vấn thuộc cùng một SqlSession
D. Mọi SqlSession đều dùng chung một vùng dữ liệu
Đáp án đúng: C

Cache cấp hai của MyBatis, khi được bật, thường liên quan đến phạm vi nào?
A. Toàn bộ máy chủ database bên ngoài ứng dụng
B. Một request HTTP dù có nhiều mapper khác nhau
C. Riêng lần gọi method Java đang thực hiện
D. Namespace của mapper khi đã cấu hình bật
Đáp án đúng: D

TypeHandler của MyBatis đảm nhận thao tác nào?
A. Tạo chỉ mục database từ annotation của field
B. Chọn mức isolation cho toàn bộ DataSource
C. Tự thêm mệnh đề WHERE vào mọi câu truy vấn
D. Chuyển đổi giá trị giữa kiểu Java và JDBC
Đáp án đúng: D

ExecutorType.BATCH trong MyBatis giúp tổ chức các thao tác ghi lặp lại ra sao?
A. Gom lệnh INSERT/UPDATE rồi thực thi theo batch
B. Tự biến mọi lệnh UPDATE thành truy vấn SELECT
C. Mở transaction mới sau mỗi dòng được cập nhật
D. Bảo đảm mọi ghi đều không thể gây deadlock
Đáp án đúng: A

Trong ứng dụng Spring Boot tích hợp MyBatis, mô hình quản lý phiên nào phù hợp?
A. Giữ một SqlSession thủ công ở singleton service
B. Gọi commit từ mapper sau từng câu SQL riêng
C. Để Spring quản lý session và giao dịch mapper
D. Bỏ DataSource vì framework tự cấp kết nối SQL
Đáp án đúng: C

Ánh xạ collection bằng truy vấn lồng nhau trên mỗi row có thể gây vấn đề nào?
A. Tự động khóa toàn bộ bảng khi mapping chạy
B. N+1 truy vấn do tải dữ liệu liên quan từng hàng
C. Mọi field Java trở thành SQL VARCHAR mặc định
D. Cache cấp một tự tắt cho tất cả mapper namespace
Đáp án đúng: B

Khi một truy vấn MyBatis chậm, dữ liệu nào hữu ích để tìm nguyên nhân?
A. Xem SQL chạy thật, tham số và execution plan
B. Chỉ số dòng trong tệp XML khai báo statement
C. Thứ tự khởi tạo các bean Java ở startup
D. Số method công khai của lớp DTO ánh xạ
Đáp án đúng: A
