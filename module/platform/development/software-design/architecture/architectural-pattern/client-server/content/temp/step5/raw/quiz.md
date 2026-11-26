1. Trong mô hình client–server, luồng yêu cầu–phản hồi cơ bản diễn ra thế nào?
A. Server luôn mở yêu cầu mới tới từng client trước
B. Client trực tiếp phân phối yêu cầu giữa các server
C. Client gửi yêu cầu và server xử lý để trả đáp ứng
D. Server chỉ lưu yêu cầu, client tự xử lý nghiệp vụ
Đáp án đúng: C

2. Lợi ích chính khi tách giao diện client khỏi xử lý nghiệp vụ server là gì?
A. Giao diện không cần tuân theo hợp đồng API chung
B. Client có thể ghi trực tiếp lên mọi cơ sở dữ liệu
C. Hai phần có thể phát triển và triển khai độc lập hơn
D. Server không còn chịu trách nhiệm xác thực đầu vào
Đáp án đúng: C

3. Với kiến trúc ba lớp, lớp nào thường chứa quy tắc nghiệp vụ?
A. Lớp giao diện trình duyệt chịu mọi quy tắc ghi dữ liệu
B. Lớp ứng dụng nằm giữa giao diện và lưu trữ dữ liệu
C. Lớp cơ sở dữ liệu quyết định toàn bộ luồng tương tác
D. Lớp cân bằng tải duy trì toàn bộ quy tắc miền nghiệp vụ
Đáp án đúng: B

4. Trong HTTP, tính stateless của giao thức yêu cầu điều gì?
A. Server buộc phải xóa mọi dữ liệu giữa các request
B. Client không được gửi cookie qua hai lượt yêu cầu
C. Mỗi request mang ngữ cảnh đủ để server xử lý
D. Mọi response bắt buộc không được lưu trong cache
Đáp án đúng: C

5. Nếu đặt reverse proxy trước các server ứng dụng, proxy thường làm gì?
A. Nhận request và chuyển tiếp đến backend phù hợp
B. Chuyển bytecode Java thành trang giao diện người dùng
C. Thay thế việc xác thực quyền truy cập trong nghiệp vụ
D. Đồng bộ toàn bộ dữ liệu của mọi máy chủ cơ sở dữ liệu
Đáp án đúng: A

6. Health check của load balancer chủ yếu phục vụ mục tiêu nào?
A. Tránh điều hướng request vào backend đang không khỏe
B. Tự động xác nhận mọi response nghiệp vụ đều chính xác
C. Thay thế hoàn toàn việc quan sát p95 của ứng dụng
D. Bảo đảm mọi server có cùng lượng dữ liệu trong cache
Đáp án đúng: A

7. Vì sao round-robin chưa chắc chia tải CPU đều giữa các server?
A. Mọi request đều có thời gian xử lý luôn như nhau
B. Round-robin bắt buộc giữ cùng user tại một backend
C. Round-robin chỉ phân phối các kết nối đã thất bại
D. Các request có thời gian và chi phí xử lý khác nhau
Đáp án đúng: D

8. Tại sao sticky session có thể làm failover phức tạp hơn?
A. Sticky session bảo đảm không có backend nào lỗi
B. Session bắt buộc được tái tạo ngay trên mọi backend
C. Session của người dùng có thể chỉ nằm tại một node
D. Load balancer sẽ tự sao chép dữ liệu ghi xuống DB
Đáp án đúng: C

9. Để mở rộng ngang server ứng dụng, thiết kế session nào thường thuận lợi?
A. Giữ toàn bộ session trong RAM của một node duy nhất
B. Lưu trạng thái phiên trong kho dùng chung hoặc token
C. Gắn mọi client vĩnh viễn với cùng backend ban đầu
D. Cho mọi client tự thay đổi quyền phiên của server
Đáp án đúng: B

10. Trong hệ thống web có API gateway, chức năng nào phù hợp đặt tại đây?
A. Trực tiếp quyết định toàn bộ quy tắc nghiệp vụ miền
B. Thay thế cơ sở dữ liệu cho mọi thao tác ghi có giao dịch
C. Giữ toàn bộ logic hiển thị riêng cho từng nút giao diện
D. Định tuyến, rate limit và xác thực chung ở rìa hệ
Đáp án đúng: D

11. Khác biệt chính giữa authentication và authorization phía server là gì?
A. Một bên mã hóa kết nối, bên kia nén payload HTTP
B. Một bên xác minh danh tính, bên kia xét quyền thao tác
C. Một bên cân bằng tải, bên kia lưu response cache
D. Một bên đo latency, bên kia điều chỉnh số connection
Đáp án đúng: B

12. Nếu client ẩn nút 'Xóa' nhưng API vẫn cho user thường xóa, cần sửa gì?
A. Kiểm tra quyền ở server trước khi thực hiện thao tác
B. Chỉ ẩn nút kỹ hơn bằng mã JavaScript phía client
C. Chỉ thay đổi tên endpoint để khó bị người dùng đoán
D. Chỉ giảm tốc độ gửi request tại trình duyệt người dùng
Đáp án đúng: A

13. Khi backend trả HTTP 503, client thường nên hiểu thế nào?
A. Người dùng chưa cung cấp thông tin xác thực hợp lệ
B. Dữ liệu được tạo thành công và có URI mới
C. Server đã xử lý hoàn tất mà không có response body
D. Dịch vụ tạm chưa sẵn sàng phục vụ yêu cầu
Đáp án đúng: D

14. Timeout ở phía client giúp giải quyết rủi ro nào của call đồng bộ?
A. Bảo đảm server hủy mọi thao tác giao dịch đã bắt đầu
B. Tự sửa được toàn bộ response không khớp JSON Schema
C. Tránh chờ vô hạn khi server hoặc mạng không hồi đáp
D. Bảo đảm request chỉ được xử lý chính xác một lần
Đáp án đúng: C

15. Khi retry POST tạo đơn hàng sau timeout, cần bảo vệ điều gì?
A. Tự tăng số kết nối đồng thời sau mỗi lần thử lại
B. Tắt mọi kiểm tra phân quyền cho yêu cầu lặp
C. Thay mọi mã HTTP lỗi bằng mã thành công 200
D. Tránh tạo trùng đơn bằng khóa idempotency phù hợp
Đáp án đúng: D

16. Vì sao retry đồng loạt có thể gây thêm tải lên server đang hồi phục?
A. Mỗi retry luôn giảm số kết nối xử lý ở backend
B. Các client gửi lại cùng lúc làm bùng lưu lượng đột ngột
C. Load balancer tự động từ chối mọi request có header
D. Mọi client sẽ chờ cho đến khi cache đồng bộ hoàn toàn
Đáp án đúng: B

17. Khi cache dữ liệu phía client, rủi ro nào cần quản lý?
A. Độ trễ của mọi request chắc chắn tăng lên gấp đôi
B. TLS không còn bảo vệ được đường truyền khi dùng cache
C. Dữ liệu có thể cũ sau khi nguồn trên server thay đổi
D. Server mặc định không thể cập nhật bất kỳ dữ liệu nào
Đáp án đúng: C

18. Với hệ thống sử dụng TLS termination ở reverse proxy, điều gì cần xem xét?
A. Bảo vệ thêm lưu lượng giữa proxy và các backend nội bộ
B. Bỏ kiểm tra certificate của phía client để giảm tải
C. Chỉ mã hóa các response trên cổng HTTP nội bộ
D. Bắt buộc lưu private key trên toàn bộ server backend
Đáp án đúng: A

19. Ưu điểm của pagination ở API danh sách lớn là gì?
A. Bảo đảm mọi trang luôn không thay đổi khi có bản ghi mới
B. Giới hạn dữ liệu mỗi response để giảm chi phí tải
C. Loại bỏ hoàn toàn nhu cầu tạo index của cơ sở dữ liệu
D. Cho phép client bỏ qua tham số tìm kiếm và sắp xếp
Đáp án đúng: B

20. Trong ứng dụng có cả web và mobile, biến thể BFF có lợi ở điểm nào?
A. Mỗi client có backend điều phối dữ liệu phù hợp riêng
B. Mọi client buộc phải hiển thị cùng cấu trúc giao diện
C. Các client bỏ qua hết xác thực của hệ thống phía sau
D. Một server BFF bắt buộc phải nắm quyền ghi dữ liệu gốc
Đáp án đúng: A

21. Khi nào WebSocket phù hợp hơn HTTP request–response đơn lẻ?
A. Khi client chỉ tải một tài liệu tĩnh đúng một lần
B. Khi hai phía cần trao đổi hai chiều liên tục, độ trễ thấp
C. Khi mọi thao tác cần gửi thành email không đồng bộ
D. Khi không được phép giữ kết nối quá vài mili giây
Đáp án đúng: B

22. Vì sao không nên cho client gọi trực tiếp database sản xuất?
A. Database sẽ mặc định không hỗ trợ nhiều kết nối đồng thời
B. Client không thể sử dụng bất kỳ trình điều khiển dữ liệu nào
C. Server ứng dụng không thể mở transaction nếu có client
D. Dễ lộ quyền và làm khó kiểm soát quy tắc nghiệp vụ
Đáp án đúng: D

23. Nếu backend cần tăng số node mà không thay đổi client, nên có lớp nào?
A. Mỗi client tự lưu IP của tất cả server từng xuất hiện
B. Gắn tên node vào từng màn hình và phát hành lại app
C. Buộc mọi request dùng kết nối trực tiếp tới DB chung
D. Một endpoint ổn định qua proxy hoặc load balancer
Đáp án đúng: D

24. Khi chẩn đoán request chậm qua nhiều lớp, telemetry nào hữu ích?
A. Trace ID kết hợp độ trễ từng lớp và tỷ lệ lỗi
B. Chỉ tổng số màu sắc giao diện tại thời điểm đo
C. Chỉ danh sách file được compiler tạo trong lần build
D. Chỉ số người đã cài ứng dụng trên thiết bị mobile
Đáp án đúng: A
