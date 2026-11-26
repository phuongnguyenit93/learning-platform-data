Bạn giải thích vai trò của JDBC trong kiến trúc ứng dụng Java và điểm khác biệt so với ORM như thế nào?
Bạn lựa chọn JDBC driver và thiết lập URL kết nối cho từng hệ quản trị cơ sở dữ liệu theo tiêu chí nào?
Bạn so sánh DriverManager với DataSource về cấu hình, kiểm thử và quản lý kết nối như thế nào?
Bạn mô tả vòng đời một Connection khi ứng dụng lấy từ connection pool và trả về pool ra sao?
Bạn giải thích vì sao không nên tùy tiện dùng chung một Connection cho nhiều luồng xử lý như thế nào?
Bạn quản lý thông tin xác thực, TLS và cấu hình kết nối JDBC trong các môi trường phát triển và production ra sao?
Bạn dùng try-with-resources để bảo đảm đóng ResultSet, Statement và Connection đúng cách khi xảy ra ngoại lệ như thế nào?
Bạn phân biệt Statement, PreparedStatement và CallableStatement theo mục đích và rủi ro sử dụng ra sao?
Bạn sử dụng SQL tham số hóa bằng PreparedStatement để giảm nguy cơ SQL injection như thế nào?
Khi tên bảng hoặc cột cần lựa chọn động nhưng không thể bind bằng placeholder, bạn thiết kế giới hạn đầu vào ra sao?
Bạn giải thích lợi ích và giới hạn của việc chuẩn bị sẵn câu SQL đối với hiệu năng trên các driver khác nhau như thế nào?
Bạn ánh xạ kiểu dữ liệu Java sang SQL, đặc biệt giá trị null, bằng các phương thức bind phù hợp ra sao?
Bạn xử lý timestamp, timezone và các kiểu thời gian Java để tránh lệch dữ liệu khi đọc ghi qua JDBC như thế nào?
Bạn dùng BigDecimal và kiểu cột SQL tương ứng để lưu giá trị tiền tệ mà không mất độ chính xác ra sao?
Bạn tổ chức đọc hoặc ghi dữ liệu BLOB và CLOB lớn để tránh giữ toàn bộ nội dung trong bộ nhớ như thế nào?
Bạn bảo đảm đúng thứ tự và kiểu của nhiều tham số trong một câu PreparedStatement phức tạp ra sao?
Bạn thiết kế thao tác INSERT để lấy generated key và liên kết bản ghi mới với đối tượng Java như thế nào?
Bạn lựa chọn executeQuery, executeUpdate và execute theo bản chất câu lệnh cũng như kết quả mong đợi như thế nào?
Bạn mô tả cơ chế dịch chuyển con trỏ ResultSet và cách tránh đọc dữ liệu sau khi tài nguyên đã đóng ra sao?
Bạn phân biệt giá trị SQL NULL với giá trị mặc định của kiểu nguyên thủy khi đọc ResultSet như thế nào?
Bạn thiết kế lớp ánh xạ một hàng ResultSet thành domain object và xử lý cột thiếu hoặc kiểu không hợp lệ ra sao?
Bạn lựa chọn fetch size và kiểu ResultSet để đọc tập kết quả lớn mà không làm cạn bộ nhớ như thế nào?
Bạn thiết kế phân trang dựa trên keyset hoặc offset khi cần trả dữ liệu theo từng trang qua JDBC ra sao?
Bạn phân tích số bản ghi được cập nhật khi thực hiện UPDATE hoặc DELETE để phát hiện cập nhật không đúng kỳ vọng như thế nào?
Bạn sử dụng addBatch và executeBatch cho tập thao tác ghi lặp lại rồi đánh giá lợi ích so với ghi từng dòng ra sao?
Nếu một batch JDBC thất bại ở giữa, bạn xác định bản ghi nào đã xử lý và quyết định rollback như thế nào?
Bạn giải thích auto-commit ảnh hưởng đến ranh giới transaction và trạng thái dữ liệu như thế nào?
Bạn tổ chức commit và rollback khi một use case phải thực hiện nhiều câu SQL liên quan ra sao?
Bạn thiết kế giao dịch chuyển tiền qua JDBC để bảo toàn bất biến số dư khi một bước xử lý lỗi như thế nào?
Bạn lựa chọn mức transaction isolation dựa trên yêu cầu nhất quán và mức tranh chấp của hệ thống như thế nào?
Bạn nhận diện dirty read, non-repeatable read và phantom read bằng các lịch thực thi giao dịch cụ thể như thế nào?
Khi hai transaction cùng sửa một bản ghi, bạn xác định nguy cơ lost update và cơ chế ngăn ngừa ra sao?
Bạn phân tích deadlock ở cơ sở dữ liệu và lên chiến lược thử lại giao dịch an toàn như thế nào?
Bạn sử dụng Savepoint để phục hồi một phần công việc trong transaction và giới hạn của cách làm này ra sao?
Bạn quản lý lại auto-commit, isolation và trạng thái read-only trước khi Connection trở về pool như thế nào?
Bạn xác định ranh giới transaction ở tầng service và bảo đảm nhiều DAO dùng chung Connection phù hợp ra sao?
Bạn phát hiện các transaction kéo dài gây giữ khóa hoặc cạn kết nối và rút ngắn thời gian thực thi như thế nào?
Bạn kết hợp query timeout, network timeout và thời hạn của request để không để tác vụ JDBC chờ vô hạn ra sao?
Bạn phân tích SQLException theo SQLState, mã lỗi nhà cung cấp và chuỗi nguyên nhân để xác định hướng xử lý như thế nào?
Bạn phân biệt lỗi dữ liệu, lỗi ràng buộc, lỗi kết nối tạm thời và lỗi cấu hình khi quyết định trả lỗi hay retry ra sao?
Khi kết nối mất ngay sau COMMIT, bạn thiết kế khả năng thực thi lại an toàn khi chưa biết giao dịch trước đã thành công hay chưa như thế nào?
Bạn ghi log SQL, thời gian chạy và thông số chẩn đoán mà vẫn bảo vệ mật khẩu hay dữ liệu cá nhân ra sao?
Khi một truy vấn trả kết quả chậm, bạn kết hợp đo thời gian JDBC với kế hoạch thực thi SQL để tìm nguyên nhân ra sao?
Bạn đánh giá vai trò của index và sự khác biệt giữa truy vấn nhiều cột khi dùng các bộ tham số khác nhau như thế nào?
Bạn lựa chọn kích thước connection pool dựa trên tải thực tế, số transaction đồng thời và giới hạn máy chủ như thế nào?
Bạn phát hiện và điều tra rò rỉ Connection hoặc Statement bằng metric và dấu vết sử dụng ra sao?
Bạn thiết kế giới hạn tải để ứng dụng không tạo hàng đợi vô hạn khi pool JDBC đã bận hết như thế nào?
Bạn xác định cách ứng dụng xử lý truy vấn chỉ đọc trên replica khi dữ liệu có thể trễ so với primary ra sao?
Bạn phối hợp thay đổi schema cơ sở dữ liệu và phiên bản ứng dụng để các bản triển khai JDBC cũ mới cùng hoạt động như thế nào?
Bạn xây dựng kiểm thử tích hợp JDBC với cơ sở dữ liệu thật để xác minh SQL, kiểu dữ liệu và transaction ra sao?
Bạn tổ chức dữ liệu kiểm thử và dọn dẹp sau mỗi lần chạy để các bài kiểm thử CRUD JDBC độc lập nhau như thế nào?
Bạn dùng DatabaseMetaData hoặc ResultSetMetaData để kiểm tra khả năng hỗ trợ và cấu trúc dữ liệu động như thế nào?
Khi cần bảo đảm truy vấn chỉ trả dữ liệu thuộc một tenant, bạn thiết kế việc ràng buộc tenant ID và kiểm thử phân quyền truy cập ra sao?
Bạn đo thông lượng, p95 latency, số kết nối chờ và tỷ lệ lỗi để đánh giá các thay đổi tối ưu JDBC như thế nào?
