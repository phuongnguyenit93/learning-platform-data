Câu 1. Vì sao ghi đơn hàng vào database rồi publish event trực tiếp có thể gây bất nhất?
A. Vì mọi broker đều yêu cầu dùng chung một database
B. Vì INSERT luôn tự phát event sau khi commit
C. Vì dữ liệu commit nhưng event có thể chưa gửi
D. Vì consumer bắt buộc đọc dữ liệu trước lúc commit
Đáp án đúng: C

Câu 2. Một giao dịch tạo đơn dùng Transactional Outbox đúng cách thực hiện điều gì?
A. Ghi đơn và bản ghi outbox trong cùng transaction
B. Ghi đơn trước, publish xong mới ghi outbox
C. Publish event trước rồi kiểm tra database có ghi không
D. Ghi outbox vào dịch vụ khác với transaction riêng
Đáp án đúng: A

Câu 3. Outbox relay có trách nhiệm chính nào trong kiến trúc?
A. Định nghĩa toàn bộ business rule của dịch vụ tạo đơn
B. Tạo bản ghi nghiệp vụ thay cho database transaction
C. Đảm bảo mọi consumer commit trong cùng một lúc
D. Đọc outbox đã commit và chuyển event tới broker
Đáp án đúng: D

Câu 4. Khi poll outbox, cách nào tránh gửi dữ liệu chưa commit?
A. Chỉ đọc các bản ghi đã được transaction commit
B. Bỏ mọi điều kiện truy vấn trên bảng outbox
C. Đọc trực tiếp cache tạm của transaction chưa xong
D. Chuyển mọi bản ghi outbox sang file cấu hình
Đáp án đúng: A

Câu 5. Điểm nổi bật của CDC relay so với polling bảng outbox là gì?
A. CDC đòi mọi consumer cùng dùng một schema SQL
B. CDC đọc thay đổi từ database log theo nguồn
C. CDC luôn đồng bộ tuyệt đối dữ liệu giữa các dịch vụ
D. CDC không cần theo dõi vị trí đọc sau restart
Đáp án đúng: B

Câu 6. Debezium được ứng dụng ra sao trong mô hình Transactional Outbox?
A. Thực hiện toàn bộ bước thanh toán trong consumer
B. Tạo SQL business rule thay cho application service
C. Theo dõi thay đổi database để chuyển outbox event
D. Chỉ tạo database schema nhưng không đọc thay đổi
Đáp án đúng: C

Câu 7. Outbox record nên có trường định danh riêng để phục vụ mục tiêu nào?
A. Đổi ngẫu nhiên event ID ở mỗi lần relay thử lại
B. Giúp nhận ra event bị phát lại qua cùng ID
C. Buộc broker dùng topic mới cho mỗi sự kiện
D. Cho phép bỏ qua mọi ràng buộc của payload
Đáp án đúng: B

Câu 8. Relay publish thành công nhưng crash trước khi đánh dấu đã gửi; điều gì có thể xảy ra?
A. Event luôn bị broker tự hủy khi relay bị crash
B. Database tự rollback bản ghi nghiệp vụ đã commit
C. Relay biết chắc broker đã nhận mà không cần lưu dấu
D. Event có thể được publish lại sau khi khởi động
Đáp án đúng: D

Câu 9. Để consumer chịu được event phát lặp, chiến lược nào thường phù hợp?
A. Ghi nhận event ID đã xử lý trong cùng transaction
B. Bỏ mọi event sau lần nhận đầu dù ID khác nhau
C. Chỉ tăng timeout của consumer khi broker chậm
D. Cho phép mỗi lần nhận tạo thêm một giao dịch mới
Đáp án đúng: A

Câu 10. Nếu relay đánh dấu outbox đã gửi trước khi broker nhận, rủi ro nào quan trọng nhất?
A. Event luôn được broker nhận thành hai bản sao
B. Event có thể mất khi publish sau đó thất bại
C. Consumer sẽ buộc phải dùng giao thức HTTP thay
D. Truy vấn database sẽ không còn khóa chính
Đáp án đúng: B

Câu 11. Vì sao Transactional Outbox không tự bảo đảm consumer xử lý đúng một lần?
A. Vì outbox chỉ hoạt động với dữ liệu không có ID
B. Vì CDC chỉ dùng được khi ứng dụng không có retry
C. Vì relay có thể publish lặp sau lỗi hoặc mất ACK
D. Vì consumer không được phép lưu trạng thái đã xử lý
Đáp án đúng: C

Câu 12. Với hai event E1 rồi E2 của cùng một đơn, chiến lược nào hỗ trợ bảo toàn thứ tự?
A. Để mỗi relay worker tự chọn random topic
B. Gắn aggregate key và sequence, duy trì thứ tự phát
C. Dùng event ID ngẫu nhiên để xác định thứ tự nghiệp vụ
D. Đặt cùng timestamp bất kể thứ tự transaction
Đáp án đúng: B

Câu 13. Nhiều relay worker cùng poll outbox; giải pháp nào giảm xử lý tranh chấp một bản ghi?
A. Cho mọi worker cùng đọc và xóa ngay bản ghi
B. Bỏ transaction trong bước lấy batch outbox
C. Cho mọi worker publish theo một timer chung
D. Claim hoặc khóa hàng để chia batch giữa worker
Đáp án đúng: D

Câu 14. Khi broker ngừng hoạt động nhưng database còn dùng được, Outbox giúp điều gì?
A. Bản ghi chờ gửi vẫn được lưu bền để retry
B. Mọi consumer tự chuyển sang dùng SQL trực tiếp
C. Mọi giao dịch nghiệp vụ đều rollback tức thì
D. Relay sẽ bỏ vĩnh viễn event không gửi được
Đáp án đúng: A

Câu 15. Đánh đổi chính khi dùng polling relay thay vì CDC là gì?
A. Polling đòi thay đổi cấu trúc business transaction
B. Polling bỏ qua mọi event có cùng aggregate ID
C. Polling luôn giữ thứ tự toàn cục giữa các topic
D. Tần suất quét ảnh hưởng độ trễ và tải database
Đáp án đúng: D

Câu 16. Nếu schema event thay đổi, vấn đề nào cần được quản lý cùng outbox pipeline?
A. Chỉ tên trường khóa chính của bảng outbox
B. Chỉ số lượng relay worker chạy mỗi phút
C. Khả năng consumer đọc các phiên bản event
D. Chỉ tần suất database tạo checkpoint nội bộ
Đáp án đúng: C

Câu 17. Sau khi commit đơn, API trả thành công nhưng consumer chưa nhận event; trạng thái này cho thấy gì?
A. Dữ liệu đơn chắc chắn đã mất trong database
B. Hệ thống chấp nhận độ trễ nhất quán giữa dịch vụ
C. Broker đã xử lý event nhưng cố tình ẩn kết quả
D. Bản ghi outbox được coi là transaction chưa commit
Đáp án đúng: B

Câu 18. Khi payload chứa thông tin khách hàng nhạy cảm, thiết kế outbox cần lưu ý gì?
A. Chỉ lưu dữ liệu cần thiết, kiểm soát quyền đọc
B. Lưu toàn bộ thông tin vì outbox chỉ dùng nội bộ
C. Đặt payload vào log công khai để dễ tìm lỗi
D. Bỏ cơ chế phân quyền vì broker đã có retry
Đáp án đúng: A

Câu 19. Relay liên tục thất bại với một event không hợp lệ, cách xử lý vận hành nào phù hợp?
A. Thử vô hạn với khoảng chờ bằng không
B. Xóa event và không ghi nhận nguyên nhân nào
C. Giới hạn retry, ghi lỗi và cô lập bản ghi cần sửa
D. Cho phép event lỗi chặn mãi tất cả aggregate khác
Đáp án đúng: C

Câu 20. Metric nào giúp phát hiện outbox bị ùn lại dù giao dịch nghiệp vụ vẫn thành công?
A. Số event chờ và độ tuổi event chờ lâu nhất
B. Số lượng controller HTTP trong source code dịch vụ
C. Số trường nullable của tất cả bảng nghiệp vụ
D. Dung lượng các lớp Java ở thư mục test
Đáp án đúng: A

Câu 21. Khi rollback transaction tạo đơn, điều gì xảy ra với bản ghi outbox viết trong cùng transaction?
A. Bản ghi outbox vẫn publish để consumer tự bỏ qua
B. Outbox được commit độc lập để ghi nhận mọi lỗi
C. Broker tự biết giao dịch database đã rollback
D. Đơn và outbox đều rollback trong cùng transaction
Đáp án đúng: D

Câu 22. Khi dọn bản ghi outbox cũ, điều kiện nào giúp giảm nguy cơ xóa trước khi giao?
A. Xóa ngay sau khi application gọi INSERT outbox
B. Chỉ dọn khi có xác nhận phát bền vững từ relay
C. Xóa bản ghi trước khi relay nhận batch publish
D. Dọn theo thời gian cố định không xét tiến độ relay
Đáp án đúng: B

Câu 23. Outbox đưa event tới broker đáng tin cậy nhưng không giải quyết trực tiếp vấn đề nào?
A. Đảm bảo bản ghi event gắn với commit nghiệp vụ
B. Cho phép relay phục hồi sau khi ngắt kết nối
C. Bảo đảm mọi bước nghiệp vụ đa dịch vụ đều atomic
D. Cho phép consumer chống trùng qua định danh event
Đáp án đúng: C

Câu 24. Muốn test khả năng chịu lỗi của relay, nên tiêm lỗi tại thời điểm nào?
A. Trước khi tạo bất kỳ bản ghi outbox nào
B. Khi client bắt đầu xác thực mật khẩu API
C. Sau khi consumer đã xóa dữ liệu nghiệp vụ
D. Sau publish, trước khi ghi nhận đã gửi
Đáp án đúng: D
