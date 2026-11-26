Câu 1. Reactor Netty đảm nhiệm vai trò nào trong ứng dụng reactive?
A. Thay thế scheduler để thực thi mọi tác vụ nghiệp vụ
B. Lưu trữ trạng thái phiên và dữ liệu HTTP của ứng dụng
C. Cung cấp I/O mạng bất đồng bộ dựa trên Netty cho Reactor
D. Tự động phân tán request qua nhiều cụm máy chủ
Đáp án đúng: C

Câu 2. Event loop của Netty chủ yếu thực hiện công việc nào?
A. Lưu toàn bộ response vào bộ nhớ trước khi gửi đi
B. Tạo một thread riêng cho mỗi request HTTP đang chạy
C. Xử lý sự kiện I/O và callback của các channel được đăng ký
D. Thực thi truy vấn cơ sở dữ liệu đồng bộ cho từng channel
Đáp án đúng: C

Câu 3. Trong cấu hình mặc định thông dụng, Reactor Netty quản lý tài nguyên client và server thế nào?
A. Dùng chung tài nguyên event loop toàn cục khi phù hợp
B. Dùng chung một channel cho mọi kết nối TCP đang mở
C. Chạy toàn bộ I/O trên scheduler dành cho tác vụ blocking
D. Tạo một nhóm event loop riêng cho mỗi request mới
Đáp án đúng: A

Câu 4. Điều gì có thể xảy ra khi gọi API blocking trực tiếp trên event loop?
A. Chỉ làm chậm request hiện tại mà không ảnh hưởng channel khác
B. Tự động chuyển lời gọi sang một thread nền riêng
C. Làm chậm xử lý I/O của nhiều channel trên cùng loop
D. Làm connection pool tăng kích thước để bù thời gian chờ
Đáp án đúng: C

Câu 5. Cách phù hợp để tích hợp lời gọi blocking vào luồng reactive là gì?
A. Gọi trực tiếp trên event loop rồi tăng timeout của client
B. Offload sang scheduler có giới hạn thread và hàng đợi
C. Tạo một thread mới cho mỗi phần tử của publisher
D. Chuyển lời gọi blocking thành callback nhưng vẫn chờ đồng bộ
Đáp án đúng: B

Câu 6. Khi cần cô lập tải mạng của một workload đặc biệt, nên cân nhắc điều gì?
A. Tắt event loop dùng chung cho mọi thành phần trong ứng dụng
B. Tăng số thread toàn cục mà không đo tải thực tế
C. Cấu hình LoopResources riêng và quản lý vòng đời của nó
D. Tạo một connection pool mới cho từng request gửi đi
Đáp án đúng: C

Câu 7. Non-blocking I/O khác blocking I/O ở điểm nào?
A. Kết quả I/O luôn được trả về ngay trong cùng lời gọi
B. Thread có thể xử lý việc khác khi thao tác I/O đang chờ
C. Ứng dụng không cần xử lý lỗi hoặc timeout khi chờ
D. Mỗi thao tác I/O luôn cần một thread chuyên dụng riêng
Đáp án đúng: B

Câu 8. Backpressure trong Reactive Streams giúp điều gì?
A. Producer luôn gửi toàn bộ dữ liệu nhanh nhất có thể
B. Consumer tự tăng vô hạn bộ đệm khi xử lý chậm
C. Network layer loại bỏ mọi phần tử khi tải tăng cao
D. Consumer điều tiết số phần tử mà producer phát ra
Đáp án đúng: D

Câu 9. Vì sao cần chú ý vòng đời ByteBuf khi viết xử lý Netty tùy chỉnh?
A. ByteBuf luôn được garbage collector thu hồi ngay sau callback
B. ByteBuf tự sao chép dữ liệu khi truyền qua mọi operator
C. ByteBuf không thể được chia sẻ giữa các channel khác nhau
D. ByteBuf có reference counting và cần release đúng lúc
Đáp án đúng: D

Câu 10. HttpClient của Reactor Netty phù hợp với nhiệm vụ nào?
A. Gửi và nhận HTTP request bằng luồng reactive
B. Lập lịch tác vụ nền theo chu kỳ cho ứng dụng
C. Mở raw TCP stream mà không dùng giao thức HTTP
D. Quản lý danh tính và quyền truy cập của người dùng
Đáp án đúng: A

Câu 11. Khi nào TcpClient phù hợp hơn HttpClient?
A. Khi cần giao tiếp TCP tùy biến ngoài ngữ nghĩa HTTP
B. Khi cần dựng endpoint REST với routing theo path
C. Khi cần trình duyệt xử lý cookie và redirect tự động
D. Khi cần tự động phân tích header và status HTTP
Đáp án đúng: A

Câu 12. HttpServer cần hoàn tất bước nào để bắt đầu nhận kết nối?
A. Tạo trước một connection cho từng client dự kiến
B. Đợi request đầu tiên rồi mới đăng ký event loop
C. Bind tới địa chỉ và cổng lắng nghe phù hợp
D. Mở connection pool outbound tới mọi client tiềm năng
Đáp án đúng: C

Câu 13. Connection pool của HttpClient chủ yếu giúp gì?
A. Tái sử dụng kết nối để giảm chi phí thiết lập
B. Mã hóa payload trước khi gửi qua mạng
C. Đảm bảo mọi request được xử lý song song vô hạn
D. Tự retry mọi request khi server trả lỗi
Đáp án đúng: A

Câu 14. maxConnections trong pool giới hạn điều gì?
A. Số kết nối tối đa mà pool cấp phát đồng thời
B. Thời gian tối đa giữa hai lần đọc response
C. Số request tối đa được xếp hàng chờ cấp kết nối
D. Thời gian tối đa chờ thiết lập kết nối TCP
Đáp án đúng: A

Câu 15. pendingAcquireTimeout liên quan đến giai đoạn nào?
A. Thời gian chờ byte đầu tiên từ response server
B. Thời gian giữ kết nối nhàn rỗi trong pool
C. Thời gian thiết lập TLS handshake với server
D. Thời gian chờ lấy một kết nối từ pool
Đáp án đúng: D

Câu 16. maxIdleTime trong cấu hình pool biểu thị điều gì?
A. Thời gian tối đa một kết nối được giữ ở trạng thái nhàn rỗi
B. Tổng thời gian tối đa một request được phép thực thi
C. Thời gian tối đa chờ một kết nối mới được tạo
D. Khoảng thời gian tối đa giữa các lần gửi request
Đáp án đúng: A

Câu 17. maxLifeTime thường được dùng để kiểm soát điều gì?
A. Số request được gửi qua một kết nối đang mở
B. Thời gian chờ một channel được đăng ký event loop
C. Tuổi thọ tổng thể của kết nối trong pool
D. Khoảng cách giữa hai lần scrape metric của pool
Đáp án đúng: C

Câu 18. Vì sao nên đặt maxIdleTime phù hợp với idle timeout của server?
A. Ngăn server gửi FIN khi client không có request
B. Giảm khả năng tái sử dụng kết nối đã bị server đóng
C. Bảo đảm client giữ kết nối lâu hơn mọi server trung gian
D. Tăng số kết nối nhàn rỗi để giảm độ trễ TLS
Đáp án đúng: B

Câu 19. Connect timeout thường giới hạn giai đoạn nào?
A. Thời gian thiết lập kết nối tới địa chỉ đích
B. Thời gian đọc toàn bộ nội dung response body
C. Thời gian chờ một kết nối rảnh trong pool
D. Thời gian xử lý toàn bộ nghiệp vụ ở server
Đáp án đúng: A

Câu 20. responseTimeout trong HTTP client được dùng để kiểm soát điều gì?
A. Thời gian DNS cache giữ lại địa chỉ máy chủ
B. Thời gian chờ connection pool tạo channel mới
C. Thời gian giữ một kết nối sau khi response hoàn tất
D. Khoảng tối đa giữa các lần đọc dữ liệu response
Đáp án đúng: D

Câu 21. Read timeout handler phù hợp để phát hiện tình huống nào?
A. Không có kết nối nào được cấp từ pool trong thời gian chờ
B. Không thể xác minh chứng thư trong TLS handshake
C. Không thể phân giải hostname trước khi mở socket
D. Không có dữ liệu được đọc trong khoảng thời gian cấu hình
Đáp án đúng: D

Câu 22. Khi cấu hình TLS cho client, điều gì cần được xác minh?
A. Chuỗi chứng thư được tin cậy và danh tính máy chủ hợp lệ
B. Tắt kiểm tra hostname để tương thích nhiều máy chủ hơn
C. Chỉ cần bật mã hóa mà không cần xác minh chứng thư
D. Chứng thư bất kỳ có khóa công khai là đủ để kết nối
Đáp án đúng: A

Câu 23. Tắt hostname verification trong TLS client tạo ra rủi ro nào?
A. Server không thể gửi chứng thư trong handshake
B. Client có thể tin nhầm máy chủ không đúng hostname
C. Connection pool không thể tái sử dụng kết nối đã mở
D. Client không còn mã hóa dữ liệu truyền trên socket
Đáp án đúng: B

Câu 24. TLS handshake timeout giúp giới hạn điều gì?
A. Thời gian hoàn tất quá trình bắt tay TLS
B. Thời gian đọc response body sau khi handshake xong
C. Thời gian chờ lấy kết nối nhàn rỗi từ pool
D. Thời gian xử lý callback trên event loop
Đáp án đúng: A

Câu 25. Mutual TLS bổ sung cơ chế nào so với TLS xác thực server thông thường?
A. Client bỏ xác minh chứng thư của server khi kết nối
B. Hai bên dùng chung một mật khẩu cho mọi phiên
C. Client cũng trình chứng thư để server xác minh
D. Payload HTTP được ký bằng khóa của người dùng cuối
Đáp án đúng: C

Câu 26. ALPN trong quá trình TLS thường được dùng để làm gì?
A. Xác định thuật toán nén của request body
B. Thỏa thuận giao thức ứng dụng như HTTP/1.1 hoặc HTTP/2
C. Thương lượng thời hạn sống của connection pool
D. Chọn số lượng event loop thread trên client
Đáp án đúng: B

Câu 27. Khi subscriber hủy request đang chạy, hành vi mong đợi của luồng reactive là gì?
A. Tự chuyển request sang connection khác để hoàn tất
B. Lan truyền cancellation và giải phóng tài nguyên liên quan
C. Chuyển cancellation thành response HTTP thành công
D. Giữ request chạy nền cho tới khi server đóng socket
Đáp án đúng: B

Câu 28. Vì sao cần tiêu thụ hoặc giải phóng response body đúng cách?
A. Bảo đảm mọi response được lưu vĩnh viễn trong heap
B. Buộc connection pool tạo kết nối mới cho request kế tiếp
C. Ngăn client áp dụng backpressure lên dữ liệu nhận
D. Cho phép tài nguyên và kết nối được tái sử dụng an toàn
Đáp án đúng: D

Câu 29. Khi retry một HTTP request sau timeout, rủi ro nào cần xem xét?
A. Timeout luôn chứng minh server chưa nhận request
B. Retry tự động làm request trở thành idempotent
C. Connection pool sẽ loại bỏ mọi tác dụng phụ bị lặp
D. Server có thể đã thực hiện thao tác trước khi client timeout
Đáp án đúng: D

Câu 30. Cách nào giúp retry thao tác ghi an toàn hơn khi kết quả lần đầu chưa rõ?
A. Bỏ qua status code và gửi lại cùng payload liên tục
B. Retry vô hạn cho tới khi nhận được response thành công
C. Dùng idempotency key và chính sách retry có giới hạn
D. Tăng connection pool để mỗi lần retry dùng socket khác
Đáp án đúng: C

Câu 31. Trong luồng reactive, onErrorResume thường được dùng để làm gì?
A. Bỏ qua mọi lỗi và tự động phát lại request
B. Giải phóng mọi connection pool của ứng dụng
C. Chặn thread hiện tại cho tới khi lỗi biến mất
D. Chuyển lỗi thành một luồng fallback phù hợp
Đáp án đúng: D

Câu 32. Metric connection pool nào hữu ích để phát hiện cạn kiệt pool?
A. CPU, heap và số class được nạp
B. Active, idle và pending acquisition
C. Số route, status code và kích thước header
D. Số thread, GC pause và số lần DNS lookup
Đáp án đúng: B

Câu 33. Vì sao không nên gắn URL đầy đủ hoặc user ID vào metric tag?
A. Prometheus không thể lưu metric có nhiều tag
B. Cardinality tăng mạnh và có thể lộ dữ liệu nhạy cảm
C. Histogram không hỗ trợ metric có nhãn dạng chuỗi
D. Tag động khiến TLS handshake không thể hoàn tất
Đáp án đúng: B

Câu 34. Bật wiretap ở môi trường production cần cân nhắc điều gì?
A. Wiretap thay thế được metrics và distributed tracing
B. Wiretap tự động mã hóa mọi nội dung trước khi ghi
C. Log có thể chứa token, header hoặc payload nhạy cảm
D. Wiretap luôn chỉ ghi metadata không có body
Đáp án đúng: C

Câu 35. Khi tự tạo LoopResources hoặc ConnectionProvider, cần làm gì lúc ứng dụng dừng?
A. Chỉ đóng listener nhưng giữ nguyên mọi event loop
B. Xóa metric trước khi đóng các connection đang mở
C. Giữ tài nguyên sống để lần khởi động sau tái sử dụng
D. Dispose tài nguyên theo vòng đời và thời gian chờ phù hợp
Đáp án đúng: D

Câu 36. Kiểm thử tải để chọn số event loop thread nên theo dõi yếu tố nào?
A. Chỉ số request đồng thời lớn nhất được dự kiến từ đầu
B. Throughput, latency, lỗi và mức dùng CPU theo đặc tính I/O
C. Số lượng kết nối TCP tối đa của một máy chủ đích
D. Dung lượng heap trống tại thời điểm khởi động ứng dụng
Đáp án đúng: B
