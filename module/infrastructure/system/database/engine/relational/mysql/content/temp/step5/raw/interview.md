Bạn sẽ dựa vào các tiêu chí nào để quyết định sử dụng MySQL cho một hệ thống nghiệp vụ có nhiều giao dịch?
Bạn sẽ giải thích vai trò của MySQL Server và storage engine trong quá trình xử lý một truy vấn như thế nào?
Những đặc điểm nào của InnoDB khiến nó phù hợp với các ứng dụng yêu cầu giao dịch và tính toàn vẹn dữ liệu?
Bạn sẽ phân biệt tác động của workload OLTP và workload phân tích đối với thiết kế cơ sở dữ liệu MySQL ra sao?
Bạn sẽ lựa chọn giữa MySQL và một hệ quản trị dữ liệu khác dựa trên yêu cầu lưu trữ, tính nhất quán và khả năng mở rộng như thế nào?
Bạn sẽ mô tả hành trình của một lệnh SELECT từ kết nối ứng dụng đến trình tối ưu và storage engine như thế nào?
Bạn sẽ đo những chỉ số nào để đánh giá sức khỏe và năng lực phục vụ của một máy chủ MySQL?
Bạn sẽ phân tích yêu cầu nghiệp vụ trước khi xác định thực thể, thuộc tính và quan hệ của một cơ sở dữ liệu như thế nào?
Bạn sẽ thiết kế bảng khách hàng, đơn hàng và chi tiết đơn hàng để đảm bảo các mối quan hệ dữ liệu ra sao?
Bạn sẽ lựa chọn khóa chính tự tăng, UUID hoặc khóa tự nhiên dựa trên những đánh đổi nào?
Bạn sẽ giải thích cách clustered index của InnoDB ảnh hưởng đến lựa chọn khóa chính và kích thước secondary index như thế nào?
Bạn sẽ dùng khóa ngoại và các hành động ON DELETE hoặc ON UPDATE để bảo toàn dữ liệu theo quy tắc nghiệp vụ ra sao?
Bạn sẽ lựa chọn giữa UNIQUE, NOT NULL, CHECK và kiểm tra ở tầng ứng dụng theo mục tiêu toàn vẹn dữ liệu như thế nào?
Bạn sẽ xác định khi nào cần chuẩn hóa dữ liệu tới các dạng chuẩn cao hơn và khi nào có thể phi chuẩn hóa có kiểm soát ra sao?
Bạn sẽ phát hiện và xử lý các bất thường thêm, sửa hoặc xóa dữ liệu trong một thiết kế bảng thiếu chuẩn hóa như thế nào?
Bạn sẽ mô hình hóa quan hệ nhiều-nhiều và các thuộc tính phát sinh trên quan hệ đó trong MySQL như thế nào?
Bạn sẽ quyết định giữa INT, BIGINT và các kiểu số nhỏ hơn dựa trên phạm vi giá trị và dung lượng lưu trữ ra sao?
Bạn sẽ dùng DECIMAL thay cho FLOAT hoặc DOUBLE trong những bài toán nào và vì sao?
Bạn sẽ chọn VARCHAR, CHAR, TEXT hoặc BLOB dựa trên đặc điểm dữ liệu và cách truy vấn như thế nào?
Bạn sẽ thiết kế mã hóa ký tự, collation và quy tắc so sánh chuỗi để hỗ trợ dữ liệu đa ngôn ngữ ra sao?
Bạn sẽ quản lý múi giờ và sự khác biệt giữa TIMESTAMP và DATETIME khi lưu thời điểm giao dịch như thế nào?
Bạn sẽ lựa chọn giữa cột JSON và các bảng quan hệ khi dữ liệu có thuộc tính linh hoạt dựa trên tiêu chí nào?
Bạn sẽ thiết kế cột sinh (generated column) khi cần tìm kiếm theo giá trị được suy ra từ dữ liệu như thế nào?
Bạn sẽ quản lý giá trị NULL và giá trị mặc định để tránh hiểu sai dữ liệu thiếu như thế nào?
Bạn sẽ cân nhắc những yếu tố nào khi dùng ENUM hoặc bảng danh mục riêng cho các trạng thái nghiệp vụ?
Bạn sẽ lập kế hoạch thay đổi schema của bảng lớn mà vẫn hạn chế ảnh hưởng đến truy cập đồng thời ra sao?
Bạn sẽ viết truy vấn lọc danh sách đơn hàng theo thời gian, trạng thái và khách hàng để giữ kết quả chính xác như thế nào?
Bạn sẽ phân biệt cách dùng INNER JOIN, LEFT JOIN và EXISTS khi tìm những bản ghi thỏa điều kiện quan hệ như thế nào?
Bạn sẽ phát hiện nguyên nhân một phép JOIN làm số dòng kết quả tăng ngoài dự kiến như thế nào?
Bạn sẽ giải thích sự khác biệt giữa điều kiện trong WHERE và HAVING với một báo cáo tổng hợp như thế nào?
Bạn sẽ dùng GROUP BY và các hàm tổng hợp để tính doanh thu theo tháng mà không đếm trùng dòng đơn hàng ra sao?
Bạn sẽ xử lý COUNT(*), COUNT(cột) và COUNT(DISTINCT cột) như thế nào khi dữ liệu có NULL hoặc trùng lặp?
Bạn sẽ dùng CASE cùng với các hàm tổng hợp để tính nhiều nhóm chỉ số trong một truy vấn ra sao?
Bạn sẽ lựa chọn giữa subquery, CTE và JOIN dựa trên khả năng đọc hiểu và hiệu năng truy vấn như thế nào?
Bạn sẽ sử dụng window function để xếp hạng khách hàng, tính tổng tích lũy hoặc so sánh kỳ trước ra sao?
Bạn sẽ thiết kế truy vấn top sản phẩm theo doanh thu nhưng vẫn xử lý các trường hợp đồng hạng như thế nào?
Bạn sẽ giải quyết bài toán phân trang trên bảng có hàng triệu bản ghi bằng OFFSET và keyset pagination ra sao?
Bạn sẽ viết truy vấn lọc theo khoảng thời gian để tránh bỏ sót dữ liệu có độ chính xác phần giây như thế nào?
Bạn sẽ thiết kế báo cáo cần kết hợp dữ liệu từ nhiều bảng nhưng vẫn đảm bảo một dòng trên mỗi thực thể ra sao?
Bạn sẽ áp dụng INSERT nhiều dòng, INSERT ... SELECT và cơ chế xử lý trùng khóa trong các trường hợp nạp dữ liệu nào?
Bạn sẽ dùng INSERT ... ON DUPLICATE KEY UPDATE như thế nào để xử lý yêu cầu ghi lặp an toàn?
Bạn sẽ phát hiện sự khác biệt giữa kết quả truy vấn mong đợi và dữ liệu thực tế bằng cách kiểm tra tập mẫu ra sao?
Bạn sẽ giải thích cách B-tree index hỗ trợ truy vấn tra cứu và tìm theo khoảng trong InnoDB như thế nào?
Bạn sẽ chọn cột nào để lập index dựa trên tần suất truy vấn, tính chọn lọc và chi phí ghi ra sao?
Bạn sẽ xác định thứ tự cột trong composite index khi truy vấn có cả điều kiện bằng, điều kiện khoảng và ORDER BY như thế nào?
Bạn sẽ giải thích quy tắc tiền tố trái của composite index thông qua một ví dụ truy vấn như thế nào?
Bạn sẽ cân nhắc giữa index đơn cột và composite index để tránh trùng lặp chỉ mục như thế nào?
Bạn sẽ đánh giá lợi ích và chi phí của covering index đối với một truy vấn thực tế ra sao?
Bạn sẽ kiểm tra tác động của việc thêm nhiều secondary index đến INSERT, UPDATE và dung lượng lưu trữ như thế nào?
Bạn sẽ sử dụng EXPLAIN để nhận biết thứ tự JOIN, kiểu truy cập, ước lượng số dòng và chỉ mục được chọn ra sao?
Bạn sẽ dùng EXPLAIN ANALYZE để đối chiếu số dòng và thời gian thực tế với ước lượng của trình tối ưu như thế nào?
Bạn sẽ tìm nguyên nhân truy vấn quét toàn bộ bảng dù đã có index phù hợp như thế nào?
Bạn sẽ xử lý một truy vấn có hàm hoặc phép biến đổi trên cột lọc khiến index khó được tận dụng ra sao?
Bạn sẽ tối ưu truy vấn ORDER BY hoặc GROUP BY phát sinh bước sắp xếp hay bảng tạm tốn kém như thế nào?
Bạn sẽ đánh giá ảnh hưởng của phân bố dữ liệu, thống kê bảng và histogram đến kế hoạch truy vấn ra sao?
Bạn sẽ lựa chọn index cho các truy vấn theo tiền tố chuỗi và tìm kiếm nội dung văn bản dựa trên yêu cầu nào?
Bạn sẽ dùng functional index hoặc generated column để hỗ trợ các biểu thức lọc thường xuyên như thế nào?
Bạn sẽ phân tích ảnh hưởng của implicit type conversion đến khả năng sử dụng index trong MySQL ra sao?
Bạn sẽ thiết kế thí nghiệm trước và sau khi tối ưu truy vấn để kiểm chứng hiệu quả thay đổi như thế nào?
Bạn sẽ quyết định khi nào cần partitioning cho một bảng lớn và vì sao partitioning không tự động thay thế index?
Bạn sẽ chọn khóa phân vùng và chiến lược lưu giữ dữ liệu theo thời gian mà không làm mất khả năng truy vấn hiệu quả như thế nào?
Bạn sẽ giải thích bốn thuộc tính ACID qua một giao dịch chuyển tiền giữa hai tài khoản như thế nào?
Bạn sẽ xác định ranh giới transaction và các bước COMMIT hoặc ROLLBACK trong một luồng đặt hàng như thế nào?
Bạn sẽ lý giải vai trò của undo log, redo log và binary log trong giao dịch, khôi phục và sao chép dữ liệu ra sao?
Bạn sẽ giải thích MVCC trong InnoDB giúp các giao dịch đọc dữ liệu nhất quán như thế nào?
Bạn sẽ so sánh hành vi đọc dữ liệu ở các mức cách ly READ COMMITTED và REPEATABLE READ trong MySQL như thế nào?
Bạn sẽ tái hiện và phân tích các hiện tượng dirty read, non-repeatable read và phantom read như thế nào?
Bạn sẽ giải thích sự khác nhau giữa consistent read và locking read trong InnoDB như thế nào?
Bạn sẽ sử dụng SELECT ... FOR UPDATE trong tình huống nào để tránh hai giao dịch cùng sửa sai một bản ghi?
Bạn sẽ xác định sự khác biệt giữa row lock, gap lock và next-key lock khi xử lý truy vấn trong transaction như thế nào?
Những yếu tố nào khiến một câu lệnh UPDATE khóa nhiều bản ghi hơn số bản ghi thực sự thay đổi, và bạn sẽ kiểm chứng chúng ra sao?
Bạn sẽ phòng tránh lost update khi nhiều yêu cầu đồng thời chỉnh sửa cùng một bản ghi như thế nào?
Bạn sẽ chọn giữa optimistic locking và pessimistic locking cho các luồng nghiệp vụ cạnh tranh cao ra sao?
Bạn sẽ thiết kế kiểm thử đồng thời để phát hiện race condition khi nhiều người cùng đặt hàng tồn kho giới hạn như thế nào?
Bạn sẽ tìm nguyên nhân deadlock bằng thông tin InnoDB và xây dựng chiến lược retry an toàn như thế nào?
Bạn sẽ điều tra giao dịch giữ khóa quá lâu khiến nhiều truy vấn khác phải chờ ra sao?
Bạn sẽ cân bằng kích thước transaction, số lần commit và độ trễ khi nạp dữ liệu hàng loạt như thế nào?
Bạn sẽ xử lý lỗi giữa chừng trong chuỗi cập nhật nhiều bảng để giữ trạng thái dữ liệu nhất quán như thế nào?
Bạn sẽ xác định ngưỡng timeout và giới hạn thời gian chờ khóa phù hợp với từng loại giao dịch ra sao?
Bạn sẽ thiết kế cơ chế retry transaction có tính idempotent để tránh tạo đơn hàng hoặc thanh toán trùng như thế nào?
Bạn sẽ quản lý kết nối và connection pool để hạn chế quá tải MySQL khi lưu lượng ứng dụng tăng đột biến ra sao?
Bạn sẽ phân tích dấu hiệu CPU cao, I/O chậm, thiếu bộ nhớ hoặc chờ khóa để xác định nút thắt của MySQL như thế nào?
Bạn sẽ quan sát truy vấn chậm bằng slow query log và các số liệu từ Performance Schema như thế nào?
Bạn sẽ lựa chọn cấu hình buffer pool dựa trên dung lượng dữ liệu nóng, bộ nhớ máy chủ và đặc điểm tải ra sao?
Bạn sẽ đánh giá tác động của cấu hình durability như innodb_flush_log_at_trx_commit và sync_binlog đến an toàn dữ liệu như thế nào?
Bạn sẽ lên kế hoạch cấp quyền cho tài khoản ứng dụng theo nguyên tắc quyền tối thiểu và tách biệt môi trường ra sao?
Bạn sẽ kiểm soát truy cập bằng user, role và các quyền trên schema hoặc bảng như thế nào?
Bạn sẽ bảo vệ mật khẩu, thông tin kết nối và dữ liệu nhạy cảm khi truyền tải và lưu trữ như thế nào?
Bạn sẽ ngăn SQL injection khi ứng dụng cần truy vấn với bộ lọc động như thế nào?
Bạn sẽ thiết kế quy trình backup nhất quán cho dữ liệu InnoDB đang có giao dịch liên tục ra sao?
Bạn sẽ lựa chọn giữa backup logic và backup vật lý dựa trên kích thước dữ liệu, thời gian khôi phục và ngân sách như thế nào?
Bạn sẽ thực hiện khôi phục đến một thời điểm xác định bằng backup và binary log theo yêu cầu RPO/RTO ra sao?
Bạn sẽ kiểm tra khả năng khôi phục của bản sao lưu trong một bài diễn tập thảm họa như thế nào?
Bạn sẽ mô tả luồng sao chép của primary và replica dựa trên binary log như thế nào?
Bạn sẽ phát hiện và xử lý replication lag khi ứng dụng đọc dữ liệu mới ghi từ replica ra sao?
Bạn sẽ lựa chọn giữa đọc trên primary và đọc trên replica dựa trên yêu cầu nhất quán của từng chức năng như thế nào?
Bạn sẽ đánh giá ưu nhược điểm của replication bất đồng bộ, bán đồng bộ và Group Replication cho yêu cầu sẵn sàng cao ra sao?
Bạn sẽ lập kế hoạch failover và kiểm tra nguy cơ mất hoặc ghi trùng dữ liệu khi thay đổi primary như thế nào?
Bạn sẽ quản lý migration schema và dữ liệu qua nhiều phiên bản ứng dụng để có thể rollback an toàn ra sao?
Bạn sẽ tổ chức giám sát, ngưỡng cảnh báo và nhật ký vận hành để phát hiện sự cố trước khi ảnh hưởng người dùng như thế nào?
Bạn sẽ xử lý tình huống dung lượng ổ đĩa tăng nhanh do binary log, bảng tạm hoặc dữ liệu không còn cần thiết ra sao?
Bạn sẽ thực hiện nâng cấp MySQL trên hệ thống đang phục vụ người dùng với kiểm thử tương thích và thời gian gián đoạn tối thiểu như thế nào?
Bạn sẽ lập kế hoạch tăng trưởng dữ liệu, lưu trữ theo vòng đời và mở rộng hệ thống MySQL khi lưu lượng vượt năng lực một máy ra sao?
Nếu một truy vấn đột ngột chậm sau khi dữ liệu tăng mạnh, bạn sẽ thiết lập trình tự kiểm tra để xác định nguyên nhân gốc như thế nào?
Nếu hệ thống báo tồn kho âm khi có khuyến mãi lớn, bạn sẽ phân tích transaction, khóa và logic ứng dụng để xử lý tận gốc như thế nào?
Nếu một bản ghi đã được commit nhưng người dùng đọc trên replica chưa thấy, bạn sẽ giải thích và đề xuất cách xử lý phù hợp như thế nào?
Bạn sẽ đề xuất cấu trúc MySQL cho một hệ thống thương mại điện tử cần vừa đảm bảo giao dịch, vừa hỗ trợ báo cáo và phục hồi sau sự cố ra sao?
