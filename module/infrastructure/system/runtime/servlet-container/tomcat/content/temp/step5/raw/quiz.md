Câu 1. Tomcat đảm nhiệm vai trò nào trong kiến trúc ứng dụng web Java?
A. Chỉ cung cấp reverse proxy HTTP cho ứng dụng
B. Chạy web application và quản lý servlet lifecycle
C. Quản lý database transaction và persistence của ứng dụng
D. Biên dịch mã Java thành native executable cho máy chủ
Đáp án đúng: B

Câu 2. Thành phần Coyote trong kiến trúc Tomcat chịu trách nhiệm chính về điều gì?
A. Tiếp nhận kết nối và chuyển HTTP request vào container
B. Quản lý context path và cấu hình triển khai WAR
C. Quản lý vòng đời servlet và ánh xạ URL tới servlet
D. Biên dịch và cache trang JSP thành servlet trước khi chạy
Đáp án đúng: A

Câu 3. Catalina đảm nhiệm chức năng nào trong Tomcat?
A. Biên dịch JSP và tạo class đã biên dịch trong thư mục work
B. Quản lý cấu trúc container và vòng đời web application
C. Quản lý pool JDBC và transaction của database
D. Quản lý socket và giao thức HTTP trên connector
Đáp án đúng: B

Câu 4. Connector của Tomcat đóng vai trò gì trong luồng request?
A. Quản lý JNDI resource cho các web application
B. Thực thi servlet logic và tạo response theo business rule
C. Lưu và đồng bộ session giữa các node trong cluster
D. Nhận giao thức mạng và chuyển request vào container
Đáp án đúng: D

Câu 5. NIO connector khác cách xử lý I/O kiểu blocking ở điểm nào?
A. Dùng một thread riêng cho từng socket đang mở
B. Đọc toàn bộ request vào file trước khi chuyển cho servlet
C. Chỉ xử lý HTTP/2 qua TLS và không hỗ trợ HTTP/1.1
D. Dùng non-blocking I/O để quản lý nhiều socket
Đáp án đúng: D

Câu 6. maxThreads của HTTP connector chủ yếu giới hạn tài nguyên nào?
A. Giới hạn thread xử lý request đồng thời
B. Giới hạn connection JDBC trong JNDI DataSource pool
C. Giới hạn số servlet được load khi WAR khởi động
D. Giới hạn số socket connector nhận và giữ mở cùng lúc
Đáp án đúng: A

Câu 7. maxConnections của connector biểu thị giới hạn nào?
A. Giới hạn request được ghi vào access log mỗi phút
B. Giới hạn connection JDBC của JNDI DataSource
C. Giới hạn thread đang xử lý servlet trong container
D. Giới hạn số kết nối đồng thời trên connector
Đáp án đúng: D

Câu 8. acceptCount có ý nghĩa gì khi connector đã đạt maxConnections?
A. Giới hạn số session nhàn rỗi trong web application
B. Giới hạn backlog khi connector đã đạt maxConnections
C. Giới hạn thread đang thực thi servlet trong container
D. Giới hạn request tối đa trên một kết nối keep-alive
Đáp án đúng: B

Câu 9. keepAliveTimeout kiểm soát khoảng thời gian nào?
A. Chờ TLS certificate được gia hạn tự động
B. Chờ request kế tiếp trên kết nối keep-alive
C. Chờ servlet hoàn tất nghiệp vụ trước khi trả response
D. Chờ connection JDBC được trả lại về pool
Đáp án đúng: B

Câu 10. Trong vòng đời servlet, phương thức service thường được gọi khi nào?
A. Chỉ chạy khi servlet khai báo loadOnStartup trong cấu hình
B. Chỉ chạy khi WAR được deploy lần đầu tiên
C. Mỗi request được container dispatch tới servlet
D. Chạy một lần trước khi container dừng toàn bộ server process
Đáp án đúng: C

Câu 11. Ý nghĩa của loadOnStartup trong khai báo servlet là gì?
A. Giới hạn số request xử lý đồng thời
B. Đặt thời hạn cho servlet instance
C. Khởi tạo servlet khi web application khởi động
D. Bật hot reload khi WAR có thay đổi
Đáp án đúng: C

Câu 12. Filter trong Servlet API thường được dùng để làm gì?
A. Chỉ nhận socket TCP trực tiếp từ connector của Tomcat
B. Tạo classloader riêng và quản lý việc nạp thư viện cho WAR
C. Lưu session bền vững sau mỗi request hoàn tất
D. Bao quanh request và response trước hoặc sau servlet
Đáp án đúng: D

Câu 13. Servlet asynchronous processing giúp ích gì khi request phải chờ tác vụ lâu?
A. Tạo thêm một thread container cho mỗi lần chờ
B. Bỏ timeout và giữ connection mở tới khi client ngắt
C. Giải phóng thread ban đầu trong lúc request chờ
D. Chuyển mọi tác vụ sang event loop dùng chung của server
Đáp án đúng: C

Câu 14. Ứng dụng web có WEB-INF/classes và WEB-INF/lib dùng các thư mục này để làm gì?
A. Chứa class và thư viện riêng của web application
B. Chứa cấu hình toàn cục dùng chung cho mọi virtual host
C. Chứa log truy cập và thread dump của JVM server
D. Chứa cấu hình connector, keystore và server-wide resources
Đáp án đúng: A

Câu 15. Cơ chế classloader riêng cho từng web application chủ yếu mang lại lợi ích nào?
A. Bảo đảm tất cả ứng dụng dùng cùng phiên bản thư viện
B. Tự cập nhật class khi JAR bên ngoài thay đổi nội dung
C. Cô lập phiên bản thư viện giữa các web application
D. Chia sẻ static state giữa mọi WAR đang chạy trên server
Đáp án đúng: C

Câu 16. Khi bật delegate cho web application classloader, điều gì thay đổi?
A. Bỏ qua hoàn toàn class nằm trong WEB-INF/classes
B. Cho phép nạp class từ mọi thư mục trên máy chủ
C. Dùng chung classloader cho mọi WAR đang chạy
D. Ưu tiên parent classloader trước thư viện của ứng dụng
Đáp án đúng: D

Câu 17. WAR tên orders.war không có context descriptor ghi đè, context path mặc định là gì?
A. Context path mặc định là /orders theo tên WAR
B. Context path mặc định là /ROOT/orders trên Tomcat
C. Context path mặc định giữ nguyên phần mở rộng .war
D. Context path mặc định là /webapps/orders theo thư mục
Đáp án đúng: A

Câu 18. Tomcat 10 chuyển Servlet API từ namespace javax sang namespace nào?
A. Servlet API chuyển sang namespace org.apache.servlet
B. Servlet API chuyển sang namespace jakarta.servlet
C. Servlet API tiếp tục dùng namespace javax.servlet cũ
D. Servlet API chuyển sang namespace java.servlet chuẩn
Đáp án đúng: B

Câu 19. Sau khi người dùng đăng nhập thành công, cách nào giúp giảm nguy cơ session fixation?
A. Đưa session ID vào URL của mọi liên kết sau đăng nhập
B. Tăng thời hạn session trước khi cấp quyền truy cập
C. Đổi session ID sau khi xác thực thành công
D. Giữ session ID hiện tại để bảo toàn trạng thái đăng nhập
Đáp án đúng: C

Câu 20. JSESSIONID mặc định thường được dùng để làm gì?
A. Nhận diện session phía server qua cookie client
B. Lưu session attribute dưới dạng JSON trong cookie
C. Chọn connector xử lý request kế tiếp theo routing table
D. Xác minh chữ ký file WAR trước khi ứng dụng được deploy
Đáp án đúng: A

Câu 21. Nếu ứng dụng dùng URL rewriting để truyền session ID, rủi ro nào cần cân nhắc?
A. Cookie session luôn tự bật thuộc tính Secure
B. Session ID có thể lộ qua URL, log hoặc Referer
C. Trình duyệt sẽ không gửi lại session ID ở request tiếp theo
D. Tomcat tạo session mới cho mỗi tài nguyên tĩnh được tải
Đáp án đúng: B

Câu 22. session-timeout trong cấu hình web application thường biểu thị điều gì?
A. Thời gian cache class của web application trong JVM
B. Thời gian nhàn rỗi trước khi session hết hạn
C. Thời gian xử lý tối đa cho mỗi request của servlet
D. Thời gian chờ socket TCP trong connector sau khi accept
Đáp án đúng: B

Câu 23. Khi triển khai Tomcat sau reverse proxy TLS termination, điều gì cần cấu hình để ứng dụng nhận đúng scheme gốc?
A. Đưa private key của proxy vào cookie session người dùng
B. Ép mọi URL HTTPS thành HTTP cố định trong ứng dụng
C. Tắt xác minh TLS trên connector nội bộ của Tomcat
D. Xử lý forwarded headers từ proxy đáng tin cậy
Đáp án đúng: D

Câu 24. Một Tomcat JNDI DataSource thường được ứng dụng tra cứu qua namespace nào?
A. Dùng namespace server:resources của hệ điều hành
B. Tra cứu trực tiếp trong namespace global của operating system
C. Tra cứu qua namespace java:comp/env của web application
D. Dùng namespace catalina:jdbc cho mọi web application
Đáp án đúng: C

Câu 25. ResourceLink trong cấu hình Tomcat thường phục vụ mục đích nào?
A. Cho web application tham chiếu global resource đã khai báo
B. Tạo HTTP connector riêng cho từng ứng dụng triển khai
C. Liên kết session cookie với chứng thư TLS của client
D. Chuyển access log của servlet sang hệ thống metrics
Đáp án đúng: A

Câu 26. Ứng dụng không đóng Connection lấy từ JNDI DataSource sau khi dùng có thể gây ra vấn đề gì?
A. maxThreads tự tăng để thay thế connection JDBC bị giữ
B. Pool cạn dần vì connection không được trả lại
C. Tăng thời gian session vì connection còn được giữ
D. Tomcat tự tạo thêm database instance khi pool đầy
Đáp án đúng: B

Câu 27. TLS connector của Tomcat cần cấu hình thông tin nào để trình chứng thư máy chủ?
A. JNDI name và giới hạn connection pool của ứng dụng
B. Access log pattern và tên virtual host đang phục vụ
C. Keystore hoặc nguồn khóa cùng certificate máy chủ
D. Thư mục WAR và context path của web application
Đáp án đúng: C

Câu 28. Khi bật HTTPS, vì sao cần giữ hostname verification ở phía client?
A. Gia hạn certificate tự động trước khi hết hạn
B. Cho phép self-signed certificate mà không cần trust store
C. Xác minh certificate thuộc đúng hostname đích
D. Tăng số thread xử lý TLS handshake trên connector
Đáp án đúng: C

Câu 29. AccessLogValve thường được dùng để ghi loại thông tin nào?
A. Ghi method, path, status và thời lượng request
B. Ghi biến cục bộ và stack frame trong servlet
C. Ghi database transaction và session attribute của ứng dụng
D. Ghi stack trace của từng request vào access log
Đáp án đúng: A

Câu 30. Valve khác servlet Filter ở phạm vi hoạt động nào?
A. Filter chỉ chạy sau khi response đã gửi xong cho client
B. Valve gắn ở pipeline Engine, Host, Context hoặc Wrapper
C. Filter chỉ xử lý TCP socket trước khi HTTP được phân tích
D. Valve chỉ chạy bên trong một servlet instance cụ thể
Đáp án đúng: B

Câu 31. autoDeploy của Host trong Tomcat thường ảnh hưởng đến điều gì?
A. Tự tăng maxThreads khi CPU vượt ngưỡng tải cao
B. Tự tạo session khi client gửi cookie mới đến server
C. Tự tạo TLS certificate cho mỗi context đang hoạt động
D. Phát hiện và deploy ứng dụng thay đổi trong appBase
Đáp án đúng: D

Câu 32. Vì sao không nên để Manager application mở công khai trong production?
A. Nó làm mất access log của connector đang phục vụ
B. Nó vô hiệu hóa cô lập classloader giữa các WAR
C. Có thể lộ chức năng quản trị và triển khai ứng dụng
D. Nó buộc connector chuyển sang blocking I/O
Đáp án đúng: C

Câu 33. Một web application tạo thread nền riêng và không dừng thread khi undeploy có thể gây ra lỗi gì?
A. Xóa session của mọi ứng dụng khác trên cùng server
B. Tự động chuyển connector sang HTTP/2 sau khi undeploy
C. Tạo JNDI global resource mới mỗi lần deploy
D. Giữ tham chiếu classloader cũ và gây memory leak
Đáp án đúng: D

Câu 34. Khi nhiều Tomcat instance phục vụ cùng ứng dụng, sticky session chủ yếu giúp điều gì?
A. Bỏ qua session timeout của web application
B. Định tuyến session về cùng một Tomcat instance
C. Mã hóa cookie bằng khóa riêng của load balancer
D. Sao chép session attribute giữa tất cả instance tự động
Đáp án đúng: B

Câu 35. Tomcat clustering có thể dùng cơ chế nào để đồng bộ session giữa các node?
A. Session replication qua cấu hình cluster phù hợp
B. Dùng chung một servlet instance trên mọi node trong cluster
C. Đưa session ID vào DNS record của service
D. Chia sẻ trực tiếp heap JVM giữa các máy chủ độc lập
Đáp án đúng: A

Câu 36. HTTP/2 qua TLS thường cần cơ chế nào để thương lượng giao thức ứng dụng?
A. Thương lượng HTTP/2 qua ALPN trong TLS handshake
B. Tra cứu JNDI trước khi bind connector nhận kết nối
C. Replication session trong lúc khởi tạo socket TCP
D. URL rewriting trong servlet filter trước khi gửi response
Đáp án đúng: A

Câu 37. Khi connector hết thread xử lý request, dấu hiệu nào có thể xuất hiện?
A. WAR tự động rollback về phiên bản đã triển khai trước
B. Tomcat chuyển toàn bộ session sang chế độ stateless
C. JNDI xóa các connection đang được ứng dụng mượn
D. Request chờ lâu hoặc bị từ chối khi queue đầy
Đáp án đúng: D

Câu 38. Khi điều tra lỗi 503 dưới tải cao, nhóm chỉ số nào nên kiểm tra đầu tiên?
A. Thread pool, active connections và connector queue
B. Số resource JNDI được khai báo trong web.xml
C. Số file JSP đã biên dịch và kích thước file WAR
D. Số session cookie được tạo ra trong trình duyệt client
Đáp án đúng: A

Câu 39. Khi triển khai bản WAR mới gây lỗi, cách giảm rủi ro phục hồi nào phù hợp?
A. Xóa work và temp trên mọi node ngay lập tức
B. Tắt access log để giảm tải trong lúc điều tra
C. Giữ artifact cũ và rollback có kiểm soát
D. Tăng acceptCount để giữ bản triển khai mới hoạt động
Đáp án đúng: C

Câu 40. Khi graceful shutdown một Tomcat instance phía sau load balancer, nên thực hiện bước nào trước?
A. Xóa mọi session cookie của người dùng ngay lập tức
B. Dừng JVM trước khi cập nhật trạng thái load balancer
C. Tắt TLS connector và giữ HTTP công khai cho client
D. Ngừng nhận request mới rồi drain request đang chạy
Đáp án đúng: D
