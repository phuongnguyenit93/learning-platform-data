Câu 1. Jetty đảm nhiệm vai trò nào trong một ứng dụng Java web?
A. Reverse proxy chuyên định tuyến request giữa các cụm mà không chạy ứng dụng Java.
B. Message broker để lưu request và phân phối event tới consumer.
C. Tiếp nhận HTTP và thực thi web application theo Servlet API.
D. Build tool để biên dịch servlet và đóng gói WAR khi khởi động.
Đáp án đúng: C

Câu 2. Trong bản phân phối Jetty, `jetty-home` thường chứa thành phần gì?
A. Các binary và thành phần dùng chung của bản phân phối Jetty.
B. Toàn bộ cấu hình riêng và dữ liệu runtime của một instance.
C. Các file WAR đã triển khai cùng session của người dùng.
D. Log và heap dump được tạo trong mỗi lần server khởi động.
Đáp án đúng: A

Câu 3. Vì sao nên tách `JETTY_HOME` và `JETTY_BASE` khi vận hành Jetty?
A. Để mỗi web application bắt buộc chạy một JVM riêng.
B. Để Jetty tự đồng bộ mọi cấu hình giữa các máy chủ.
C. Giữ config và runtime state riêng với phần cài đặt.
D. Để chuyển toàn bộ log runtime vào thư mục chứa binary.
Đáp án đúng: C

Câu 4. Trong Jetty standalone, `start.jar` và các module cấu hình được dùng chủ yếu để làm gì?
A. Biên dịch source code của servlet trước mỗi request.
B. Tạo session store dùng chung cho mọi node Jetty.
C. Tự động tạo WAR từ thư mục source của ứng dụng.
D. Kích hoạt module và cấu hình instance Jetty.
Đáp án đúng: D

Câu 5. Khi nhúng Jetty vào ứng dụng Java, đối tượng nào thường đại diện cho server chính?
A. `ServletContext` đại diện cho toàn bộ tiến trình JVM.
B. `HttpServletRequest` mở listener và quản lý connector.
C. `org.eclipse.jetty.server.Server` quản lý vòng đời server.
D. `WebSocketSession` khởi tạo thread pool của server.
Đáp án đúng: C

Câu 6. Phương thức `join()` trong vòng đời Jetty embedded thường phục vụ mục đích nào?
A. Chờ connector hoàn tất TLS handshake trước khi start handler.
B. Đợi toàn bộ session hết hạn rồi mới tạo server socket.
C. Chạy lại handler tree theo chu kỳ để kiểm tra health.
D. Chặn luồng main cho tới khi server kết thúc.
Đáp án đúng: D

Câu 7. `ServerConnector` đảm nhiệm phần việc nào trong Jetty?
A. Chuyển servlet mapping thành URL pattern cho ứng dụng.
B. Lưu session và đồng bộ chúng giữa các node.
C. Mở endpoint mạng và nhận kết nối đến Jetty.
D. Ghi access log sau khi response được gửi về client.
Đáp án đúng: C

Câu 8. Trong connector non-blocking, acceptor và selector có vai trò khác nhau ra sao?
A. Selector nhận socket; acceptor xử lý mọi servlet request.
B. Acceptor chạy filter; selector thực hiện authentication.
C. Selector quản lý session; acceptor ghi log request.
D. Acceptor nhận socket; selector theo dõi I/O readiness.
Đáp án đúng: D

Câu 9. `QueuedThreadPool` của Jetty chủ yếu quản lý tài nguyên nào?
A. Bảng route HTTP và danh sách virtual host của server.
B. Session store và bộ nhớ cache của web application.
C. TLS certificate cùng trust anchor của connector.
D. Worker thread và hàng đợi tác vụ xử lý của server.
Đáp án đúng: D

Câu 10. Handler tree trong Jetty được dùng để làm gì?
A. Khai báo dependency Maven và thứ tự compile servlet.
B. Đồng bộ cookie và session giữa các trình duyệt.
C. Tổ chức handler để định tuyến và xử lý request.
D. Lưu cấu hình connector vào cơ sở dữ liệu quan hệ.
Đáp án đúng: C

Câu 11. `ServletContextHandler` cung cấp chức năng gì cho ứng dụng web?
A. Quản lý TLS certificate và thuật toán mã hóa connector.
B. Gắn servlet, filter, listener và cấu hình context cho ứng dụng.
C. Tạo JDBC connection pool cho mọi servlet trong context.
D. Tự động cân bằng tải giữa nhiều Jetty instance.
Đáp án đúng: B

Câu 12. `WebAppContext` thường được dùng để triển khai loại ứng dụng nào?
A. Một tập tin cấu hình TLS dùng chung cho mọi connector.
B. Triển khai web application từ WAR hoặc thư mục.
C. Một bộ plugin Maven chạy trong giai đoạn compile.
D. Một kho lưu trữ log được truy vấn qua JMX.
Đáp án đúng: B

Câu 13. Context path và servlet mapping khác nhau ở điểm nào?
A. Context path chọn webapp; servlet mapping chọn servlet.
B. Context path chọn servlet; servlet mapping chọn virtual host của server.
C. Context path chỉ áp dụng cho static file; servlet mapping chỉ cho WebSocket.
D. Hai cấu hình cùng xác định port TCP mà connector sẽ mở.
Đáp án đúng: A

Câu 14. Servlet mapping quyết định điều gì khi Jetty nhận HTTP request?
A. Chọn servlet hoặc resource handler theo request path.
B. Thread nào sẽ nhận TCP connection trước khi TLS handshake.
C. Session nào được chia sẻ với các node trong cluster.
D. Certificate nào được chọn cho mọi host header.
Đáp án đúng: A

Câu 15. Khi WAR chứa thư viện trong `WEB-INF/lib`, Jetty sử dụng chúng theo cách nào?
A. Các thư viện được tự động thêm vào classpath của mọi JVM trên host.
B. Các JAR được gửi về client để trình duyệt thực thi servlet.
C. Các thư viện được biên dịch lại thành module Jetty khi request đến.
D. Các class trong WAR được nạp theo cơ chế classloader của web application.
Đáp án đúng: D

Câu 16. Filter trong Servlet pipeline thường được thực thi ở đâu?
A. Trong connector trước khi socket TCP được accept.
B. Bao quanh xử lý request và response của servlet.
C. Trong storage backend sau khi response đã được ghi log.
D. Trong classloader trước khi WAR được giải nén.
Đáp án đúng: B

Câu 17. Thiết lập connector idle timeout nhằm kiểm soát điều gì?
A. Giới hạn thời gian connection ở trạng thái idle.
B. Thời gian tối đa để một WAR được giải nén vào context.
C. Thời gian lưu session sau lần truy cập cuối cùng.
D. Thời gian chờ Maven tải dependency khi server start.
Đáp án đúng: A

Câu 18. Để cấu hình HTTPS cho Jetty, thành phần nào thường cung cấp TLS context phía server?
A. `QueuedThreadPool` cùng cấu hình HTTPS connector.
B. `WebAppContext` cùng cấu hình HTTPS connector.
C. `SessionHandler` cùng cấu hình HTTPS connector.
D. Dùng `SslContextFactory.Server` cho TLS server.
Đáp án đúng: D

Câu 19. Keystore của HTTPS connector thường chứa loại thông tin nào?
A. Danh sách CA client được tin cậy khi xác thực mutual TLS.
B. Danh sách servlet role được phép truy cập endpoint HTTPS.
C. Các session cookie đã mã hóa của người dùng đang đăng nhập.
D. Chứng chỉ cùng private key của Jetty server.
Đáp án đúng: D

Câu 20. Truststore có vai trò gì khi Jetty xác thực chứng chỉ client?
A. Private key và server certificate dùng để trình bày danh tính server.
B. Tin cậy CA/chứng chỉ client khi xác thực mutual TLS.
C. Danh sách cipher suite mà trình duyệt hỗ trợ khi kết nối.
D. Các khóa ký session cookie được dùng cho mọi web application.
Đáp án đúng: B

Câu 21. ALPN được dùng trong cấu hình HTTP/2 qua TLS để làm gì?
A. Mã hóa HTTP header bằng certificate của server trước khi gửi.
B. Chọn servlet mapping dựa trên phiên bản HTTP của client.
C. Thương lượng HTTP/2 hoặc HTTP/1.1 trong TLS.
D. Đồng bộ session state giữa các connector trong cùng server.
Đáp án đúng: C

Câu 22. Servlet asynchronous processing với `startAsync()` giúp ích gì?
A. Chuyển mọi servlet request sang một JVM khác để chạy nền.
B. Xử lý bất đồng bộ mà không giữ request thread lúc chờ.
C. Bỏ qua response lifecycle để client tự đóng socket.
D. Tự động biến servlet đồng bộ thành WebSocket endpoint.
Đáp án đúng: B

Câu 23. Khi một async servlet operation hoàn tất, ứng dụng cần thực hiện thao tác nào?
A. Gọi `AsyncContext.complete()` khi xử lý async đã hoàn tất.
B. Gọi `Server.stop()` để giải phóng request thread.
C. Gọi `HttpSession.invalidate()` để kết thúc async context.
D. Gọi `ServletContext.destroy()` sau mỗi async response.
Đáp án đúng: A

Câu 24. Async timeout trong Servlet API nên được xử lý ra sao?
A. Tăng timeout vô hạn để tránh mọi async request bị kết thúc.
B. Đăng ký xử lý timeout và hoàn tất hoặc hủy tác vụ phù hợp.
C. Bỏ qua timeout vì Jetty tự tạo response hợp lệ cho ứng dụng.
D. Khởi động lại connector mỗi khi async request hết thời gian.
Đáp án đúng: B

Câu 25. Session HTTP mặc định thường được liên kết với client bằng cách nào?
A. Cookie session ID như `JSESSIONID` thường được gửi lại trong request.
B. Cookie lưu toàn bộ object session phía server trong trình duyệt.
C. Header `Host` chứa session ID và được Jetty dùng để tra session.
D. TCP source port được dùng làm session ID ổn định cho người dùng.
Đáp án đúng: A

Câu 26. Trong triển khai nhiều Jetty node, điều gì giúp session tồn tại khi request chuyển node hoặc node lỗi?
A. Chỉ tăng connector acceptor để session tự chia sẻ giữa các node.
B. Dùng chung một port TCP để Jetty tự đồng bộ mọi session.
C. Dùng session store/replication phù hợp và cấu hình routing có chủ đích.
D. Đổi context path giống nhau để các node tự đọc session của nhau.
Đáp án đúng: C

Câu 27. Sau khi người dùng đăng nhập thành công, biện pháp nào giúp giảm session fixation?
A. Giữ nguyên session ID trước và sau đăng nhập để không mất trạng thái.
B. Đổi session ID sau khi xác thực và cấu hình cookie an toàn.
C. Đưa session ID vào URL để trình duyệt luôn gửi lại chính xác.
D. Tắt HttpOnly để JavaScript cập nhật session ID sau đăng nhập.
Đáp án đúng: B

Câu 28. WebSocket khác HTTP request-response thông thường ở điểm nào?
A. WebSocket tạo một kết nối TCP mới cho từng message gửi đi.
B. WebSocket duy trì kết nối hai chiều sau bước HTTP Upgrade.
C. WebSocket chỉ cho phép server gửi dữ liệu sau HTTP response.
D. WebSocket thay thế TLS và không thể chạy trên HTTPS.
Đáp án đúng: B

Câu 29. Khi vận hành WebSocket lâu dài, vì sao cần heartbeat và xử lý backpressure?
A. Heartbeat phát hiện peer lỗi; backpressure kiểm soát tốc độ gửi.
B. Tự tăng số thread Jetty mỗi khi client gửi một frame mới.
C. Bảo đảm mọi message luôn được lưu bền vững trong session store.
D. Thay thế xác thực handshake bằng ping frame định kỳ.
Đáp án đúng: A

Câu 30. Servlet security constraint có thể dùng để khai báo điều gì?
A. Số lượng acceptor, selector và worker thread của connector.
B. Thứ tự load class trong `WEB-INF/lib` của từng WAR.
C. URL security theo role, authentication và transport.
D. Thời gian retention của access log và heap dump.
Đáp án đúng: C

Câu 31. JMX trong Jetty hỗ trợ người vận hành công việc nào?
A. Tự động sửa source servlet khi phát hiện request trả về 500.
B. Phân phối WAR và dependency giữa các Jetty node.
C. Quan sát MBeans và runtime statistics của Jetty.
D. Thay thế TLS certificate mà không cần cấu hình connector.
Đáp án đúng: C

Câu 32. Jetty request log thường cung cấp bằng chứng gì khi điều tra request chậm?
A. Nội dung đầy đủ của mọi request body cùng mật khẩu người dùng.
B. Heap snapshot của từng thread trong lúc xử lý request.
C. Danh sách toàn bộ session attribute sau mỗi response.
D. Ghi method, path, status, latency và response size.
Đáp án đúng: D

Câu 33. Muốn theo dõi tình trạng thread pool và connector theo thời gian, nguồn nào hữu ích?
A. Danh sách file WAR và manifest trong thư mục deploy.
B. DNS zone cùng certificate chain của máy client.
C. Dùng Jetty MBeans và exported runtime metrics.
D. Cookie jar của trình duyệt đang gửi request.
Đáp án đúng: C

Câu 34. Jetty trả 503 khi tải tăng mạnh; hướng điều tra nào phù hợp?
A. Đo queue, thread utilization, connector và downstream wait.
B. Tăng max threads ngay mà không kiểm tra tài nguyên hoặc dependency.
C. Tắt access log để Jetty không phải ghi status response.
D. Tăng idle timeout cho mọi connection để loại bỏ overload.
Đáp án đúng: A

Câu 35. Ứng dụng WAR trả 404 sau khi deploy; nên xác minh điều gì trước?
A. Chỉ đổi port connector vì 404 luôn do port HTTP sai.
B. Tăng thread pool vì Jetty trả 404 khi hết worker.
C. Tạo lại TLS keystore vì 404 biểu thị certificate không hợp lệ.
D. Kiểm tra context path, deploy state, WAR và mapping.
Đáp án đúng: D

Câu 36. Graceful shutdown của Jetty hướng tới mục tiêu nào?
A. Ngừng nhận request mới và cho request đang chạy thời gian hoàn tất.
B. Đóng JVM ngay lập tức để mọi request được retry từ đầu.
C. Xóa session store và access log trước khi đóng connector.
D. Giữ connector mở vô hạn cho tới khi mọi client đóng trình duyệt.
Đáp án đúng: A

Câu 37. Khi thread pool thường xuyên cạn worker, cách xử lý nào có cơ sở nhất?
A. Tăng max threads liên tục cho tới khi queue không còn tăng.
B. Giảm số selector để worker thread có thêm thời gian chạy.
C. Tắt async processing và tăng idle timeout cho tất cả request.
D. Đo queue, thread dump và downstream trước khi tăng pool.
Đáp án đúng: D

Câu 38. Để điều tra thread bị kẹt hoặc request chậm kéo dài, bằng chứng runtime nào hữu ích?
A. Chỉ xem file cấu hình WAR sau khi process đã restart.
B. Thread dump và JMX/runtime metrics tại thời điểm bị chậm.
C. Danh sách cookie trong trình duyệt của người dùng bị ảnh hưởng.
D. Mã nguồn servlet mà không đối chiếu với thread đang chạy.
Đáp án đúng: B

Câu 39. Biện pháp nào giúp giảm rủi ro khi Jetty phục vụ endpoint quản trị hoặc nội dung nhạy cảm?
A. Công khai JMX và admin endpoint để dễ giám sát từ mọi mạng.
B. Giới hạn quyền và mạng truy cập endpoint quản trị.
C. Ghi token và session ID vào access log để hỗ trợ audit.
D. Cho phép mọi HTTP method trên admin path để tránh lỗi tương thích.
Đáp án đúng: B

Câu 40. Khi latency tăng nhưng Jetty vẫn nhận request, cách khoanh vùng nào hiệu quả?
A. Tách thời gian queue, xử lý servlet, downstream I/O và GC bằng metrics cùng log.
B. Tăng connector idle timeout vì mọi latency đều do socket đóng sớm.
C. Đổi context path để request được phân phối sang handler khác.
D. Tắt request logging để giảm latency mà không đo lại hiệu năng.
Đáp án đúng: A
