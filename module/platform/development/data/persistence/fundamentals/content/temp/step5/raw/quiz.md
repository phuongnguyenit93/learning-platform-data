Câu 1: Ranh giới persistence trong ứng dụng Java nên bảo vệ điều gì?
A. Logic domain không gắn trực tiếp với API lưu trữ
B. Logic domain khỏi mọi thao tác chuyển đổi giữa DTO
C. Logic domain khỏi việc khai báo invariant nghiệp vụ
D. Logic domain khỏi việc kiểm tra đầu vào ở service
Đáp án đúng: A

Câu 2: Khi dữ liệu có nhiều quan hệ và cần giao dịch nhất quán, lựa chọn nào phù hợp?
A. File log văn bản không schema và không transaction
B. Key-value cache đơn thuần không kiểm tra ràng buộc
C. Object store cho blob không có quan hệ tham chiếu
D. Cơ sở dữ liệu quan hệ có hỗ trợ transaction
Đáp án đúng: D

Câu 3: Khi một aggregate có dữ liệu lồng nhau đọc cùng lúc, document model có lợi thế gì?
A. Tự bảo đảm transaction nhiều document trên mọi hệ thống
B. Có thể lưu và lấy cả document theo ranh giới aggregate
C. Tự xử lý mọi truy vấn join như cơ sở dữ liệu quan hệ
D. Tự ngăn dữ liệu lặp dù các document trùng nội dung
Đáp án đúng: B

Câu 4: Mục tiêu của chuẩn hóa dữ liệu quan hệ là gì?
A. Gộp tất cả bảng vào một nơi để không cần join
B. Tạo thêm bản sao các cột để mọi truy vấn nhanh hơn
C. Bỏ mọi khóa ngoại để dễ thay đổi kiểu dữ liệu
D. Giảm dư thừa gây bất nhất khi cập nhật bản ghi
Đáp án đúng: D

Câu 5: Khóa ngoại trong schema quan hệ chủ yếu giúp bảo đảm gì?
A. Giá trị mọi cột trong bảng luôn là duy nhất
B. Thứ tự của hàng khi SELECT không có ORDER BY
C. Tốc độ của mọi truy vấn JOIN luôn dưới ngưỡng
D. Giữ tham chiếu khóa ngoại hợp lệ trong dữ liệu
Đáp án đúng: D

Câu 6: Chọn index cho bảng lớn nên dựa trên yếu tố nào?
A. Dựa vào số giá trị distinct mà bỏ qua điều kiện lọc
B. Bộ lọc, join và các truy vấn được chạy thường xuyên
C. Dựa vào độ dài dữ liệu cột mà bỏ qua chi phí ghi
D. Dựa vào số hàng trong bảng mà không xem workload
Đáp án đúng: B

Câu 7: Với index B-tree tổng hợp (a,b), truy vấn nào thường dễ tận dụng prefix?
A. Chỉ lọc theo b mà bỏ qua giá trị a
B. Lọc theo a rồi thêm điều kiện theo b
C. Chỉ lọc theo c không thuộc index hiện có
D. Chỉ lọc theo hàm ngẫu nhiên trên cột c
Đáp án đúng: B

Câu 8: Covering index có thể tăng tốc truy vấn vì sao?
A. Giúp mọi truy vấn không phải lọc dữ liệu bằng WHERE
B. Giúp transaction luôn tránh xung đột khóa ghi
C. Chứa đủ cột cần đọc để giảm lookup về bảng gốc
D. Giúp index tự cập nhật mà không phải ghi vào đĩa
Đáp án đúng: C

Câu 9: Vì sao không nên tạo index cho mọi cột mà không đo lường?
A. Index tốn dung lượng và tăng chi phí ghi dữ liệu
B. Index chỉ chiếm RAM nên không làm tăng chi phí lưu trữ
C. Index giúp mọi thao tác ghi nhanh hơn khi dữ liệu lớn
D. Index tự xóa bản ghi thừa nên không tốn thêm bộ nhớ
Đáp án đúng: A

Câu 10: Khi truy vấn chậm dù có index, nên xem thông tin nào trước?
A. Execution plan và lượng dữ liệu thực tế được quét
B. Danh sách index đã tạo mà không xét cách planner dùng
C. Thống kê cột có giá trị null nhưng bỏ số hàng quét
D. Kích thước connection pool dù truy vấn đơn lẻ chậm
Đáp án đúng: A

Câu 11: Với phân trang dữ liệu thay đổi liên tục, keyset pagination có lợi gì?
A. Dùng OFFSET tăng dần để không cần lưu khóa cuối
B. Dùng random ORDER BY để mọi trang luôn khác nhau
C. Dùng khóa sắp xếp ổn định để tránh offset sâu
D. Dùng LIMIT không ORDER BY để tránh mất bản ghi
Đáp án đúng: C

Câu 12: Trong ACID, atomicity nói về bảo đảm nào?
A. Tránh đọc dữ liệu chưa commit từ giao dịch khác
B. Toàn bộ transaction được commit hoặc rollback
C. Giữ các ràng buộc dữ liệu hợp lệ sau commit
D. Dữ liệu commit vẫn tồn tại sau khởi động lại
Đáp án đúng: B

Câu 13: Trong ACID, consistency được hiểu đúng thế nào?
A. Giao dịch được cách ly khỏi các tác động đồng thời
B. Giao dịch giữ các invariant và ràng buộc hợp lệ
C. Thay đổi đã commit có thể phục hồi sau restart
D. Giao dịch hoặc commit hết hoặc không đổi dữ liệu
Đáp án đúng: B

Câu 14: Ở isolation READ COMMITTED, thao tác nào thường bị ngăn?
A. Đọc dữ liệu chưa commit của transaction khác
B. Đọc lại cùng hàng và thấy dữ liệu mới đã commit
C. Thấy thêm hàng mới khớp điều kiện khi truy vấn lại
D. Xảy ra xung đột cập nhật trong mọi trường hợp
Đáp án đúng: A

Câu 15: Hiện tượng non-repeatable read xảy ra khi nào?
A. Một hàng chưa commit được đọc ở transaction khác
B. Một transaction ghi đè dữ liệu mà không có rollback
C. Câu SELECT trả về dữ liệu với thứ tự dòng khác
D. Cùng một hàng được đọc lại và thấy giá trị đã đổi
Đáp án đúng: D

Câu 16: Mức SERIALIZABLE nhằm cung cấp tính chất nào?
A. Mọi truy vấn không cần dùng khóa hoặc kiểm tra xung đột
B. Mọi transaction sẽ không bao giờ phải retry do xung đột
C. Kết quả tương đương một lịch thực thi tuần tự
D. Các giao dịch luôn xử lý theo thứ tự client gửi tới
Đáp án đúng: C

Câu 17: Khi hai người cùng sửa entity JPA, @Version giúp cơ chế nào?
A. Optimistic locking kiểm tra phiên bản khi cập nhật
B. Pessimistic locking giữ row lock suốt request HTTP
C. Full-table locking ngăn mọi thao tác đọc dữ liệu
D. Schema locking tự động tạo index khi thay đổi entity
Đáp án đúng: A

Câu 18: Trong SQL, SELECT ... FOR UPDATE thường dùng nhằm mục đích gì?
A. Khóa cả bảng ngay cả khi chỉ đọc một vài hàng
B. Giữ snapshot MVCC mà không yêu cầu khóa hàng
C. Khóa các hàng đọc để phối hợp cập nhật đồng thời
D. Chỉ kiểm tra xung đột khi commit mà không khóa trước
Đáp án đúng: C

Câu 19: Khi DB báo deadlock và hủy một transaction, cách phản ứng phù hợp?
A. Giữ nguyên transaction và tiếp tục ghi từ câu SQL lỗi
B. Tắt toàn bộ ràng buộc khóa ngoại để tránh deadlock
C. Đổi mọi thao tác ghi thành SELECT không có khóa
D. Rollback rồi retry có giới hạn và backoff
Đáp án đúng: D

Câu 20: Tại sao kiểm tra tồn tại ở application chưa đủ để ngăn trùng khóa?
A. Hai request luôn tuần tự nên không thể xung đột nhau
B. Hai request vẫn có thể đua nhau trước bước INSERT
C. Lệnh SELECT tự khóa toàn bộ bảng theo mọi isolation
D. Index thường tự chặn mọi request khi đọc khóa chính
Đáp án đúng: B

Câu 21: Khi connection pool bị cạn do truy vấn treo, nên cải thiện gì?
A. Giới hạn timeout, đóng kết nối và giám sát pool
B. Tăng pool vô hạn để loại bỏ mọi lỗi truy vấn
C. Tắt timeout để mọi truy vấn được quyền đợi mãi
D. Tạo mới connection cho từng field của DTO trả về
Đáp án đúng: A

Câu 22: Retry transaction sau lỗi kết nối cần xét điều gì?
A. Chỉ tăng số lượt retry mà bỏ xác minh trạng thái
B. Luôn khẳng định chưa commit nếu client mất kết nối
C. Tính idempotent và việc commit có thể đã xảy ra
D. Luôn cấp ID mới để đảm bảo không trùng giao dịch
Đáp án đúng: C

Câu 23: Trong JDBC, cách chính để chống SQL injection khi truyền giá trị là gì?
A. Ghép chuỗi SQL với giá trị đã xóa dấu cách
B. Dùng PreparedStatement để bind giá trị SQL
C. Dùng Statement với dữ liệu được escape thủ công
D. Đổi tên bảng để tránh các keyword trong câu SQL
Đáp án đúng: B

Câu 24: Vì sao tài khoản DB của ứng dụng nên được cấp ít quyền nhất có thể?
A. Giảm số vòng network round-trip của mọi câu SQL
B. Cho phép tự động tăng isolation trong mọi transaction
C. Giảm phạm vi thiệt hại nếu credentials bị lộ
D. Cho phép mọi user truy cập bảng không cần xác thực
Đáp án đúng: C

Câu 25: Khi đổi tên cột trên hệ thống đang chạy, chiến lược expand-contract là gì?
A. Xóa cột cũ ngay trước khi triển khai ứng dụng mới
B. Thay tất cả trường bằng TEXT để khỏi chạy migration
C. Đóng DB rồi đổi schema không có bước tương thích
D. Thêm schema mới, chuyển client rồi loại bỏ schema cũ
Đáp án đúng: D

Câu 26: Khi một giao dịch DB phải phát sự kiện ra broker, outbox pattern giúp gì?
A. Gửi broker trước commit và mặc định coi là nhất quán
B. Gửi broker sau commit và bảo đảm không thể mất sự kiện
C. Lưu sự kiện cùng transaction rồi phát ra bất đồng bộ
D. Không cần xử lý trùng lặp khi consumer đọc sự kiện
Đáp án đúng: C

Câu 27: Trong chiến lược backup, RPO và RTO biểu thị điều gì?
A. Thời gian phục hồi rồi mức mất dữ liệu tối đa
B. Dung lượng backup và số lần restore cho phép
C. Độ trễ truy vấn và thời gian đồng bộ replica
D. Giới hạn mất dữ liệu cho phép và thời gian phục hồi
Đáp án đúng: D

Câu 28: Khi ORM sinh N+1 query lúc đọc một danh sách, biện pháp nào thích hợp?
A. Dùng fetch join, batch fetching hoặc projection
B. Chuyển tất cả quan hệ sang EAGER dù không truy vấn
C. Chỉ tăng pool kết nối mà không đổi truy vấn ORM
D. Thêm index cho mọi khóa nhưng giữ nguyên fetch plan
Đáp án đúng: A
