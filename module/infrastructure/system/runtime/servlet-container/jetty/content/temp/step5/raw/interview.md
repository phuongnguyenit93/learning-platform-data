Bạn phân biệt Eclipse Jetty với Java application server đầy đủ về phạm vi dịch vụ nền tảng được cung cấp như thế nào?
Bạn mô tả kiến trúc Jetty gồm Server, Connector, Handler và ServletContext liên kết với nhau ra sao?
Bạn lựa chọn Jetty chạy độc lập hay nhúng trong ứng dụng dựa trên yêu cầu triển khai nào?
Bạn đánh giá lợi ích và giới hạn của embedded Jetty khi ứng dụng cần kiểm soát vòng đời HTTP server như thế nào?
Bạn xác định phiên bản Jetty phù hợp với JDK, Servlet API và Jakarta EE namespace của ứng dụng ra sao?
Bạn phân tích tác động chuyển từ javax.servlet sang jakarta.servlet khi nâng cấp Jetty như thế nào?
Bạn phân biệt các môi trường hoặc module hỗ trợ Jakarta EE của Jetty theo phiên bản như thế nào?
Bạn xác định những dịch vụ như EJB hoặc JTA cần nền tảng bổ sung khi chạy ứng dụng trên Jetty ra sao?
Bạn tổ chức cấu hình Jetty tách khỏi mã ứng dụng để cùng artifact chạy trên nhiều môi trường như thế nào?
Bạn thiết kế vòng đời khởi động, dừng và giải phóng tài nguyên Jetty trong ứng dụng nhúng ra sao?
Bạn giải thích vai trò của Server và Handler tree trong việc định tuyến request tới thành phần xử lý như thế nào?
Bạn phân biệt Handler, ContextHandler, ServletContextHandler và WebAppContext theo trách nhiệm ra sao?
Bạn lựa chọn Handler trực tiếp hay Servlet API cho một endpoint dựa trên nhu cầu tương thích và khả năng bảo trì như thế nào?
Bạn tổ chức nhiều context path và virtual host trên cùng một Jetty server như thế nào?
Bạn xác định thứ tự handler ảnh hưởng tới routing, authentication và xử lý lỗi như thế nào?
Bạn cấu hình Connector và ConnectionFactory để phục vụ HTTP/1.1, HTTP/2 hoặc giao thức khác ra sao?
Bạn phân biệt acceptor thread với selector thread trong quá trình Jetty nhận và điều phối kết nối như thế nào?
Bạn lựa chọn số acceptors và selectors dựa trên số CPU, số kết nối và workload ra sao?
Bạn đánh giá ảnh hưởng của QueuedThreadPool tới xử lý request và các tác vụ nội bộ của Jetty như thế nào?
Bạn xác định dấu hiệu thread pool cạn hoặc queue tăng khi Jetty vẫn nhận được kết nối mới như thế nào?
Bạn cấu hình giới hạn thread pool và queue để tránh một đợt tải lớn làm cạn tài nguyên máy chủ ra sao?
Bạn phân biệt giới hạn số kết nối với giới hạn số request đang xử lý đồng thời trong Jetty như thế nào?
Bạn cấu hình idle timeout và request timeout để giải phóng kết nối nhàn rỗi mà không cắt request hợp lệ ra sao?
Bạn lựa chọn giới hạn header size, request body size và form content size để bảo vệ server như thế nào?
Bạn kiểm tra hành vi Jetty khi client gửi request chậm hoặc giữ kết nối mở quá lâu ra sao?
Bạn thiết kế xử lý graceful shutdown để ngừng nhận request mới và hoàn tất request đang chạy như thế nào?
Bạn mô tả cách triển khai WAR trên Jetty và các thành phần cần có để ứng dụng được khởi tạo như thế nào?
Bạn phân biệt deploy WAR trong standalone Jetty với đăng ký WebAppContext trong ứng dụng nhúng ra sao?
Bạn kiểm tra nguyên nhân WAR không deploy do descriptor, annotation scan hoặc thiếu class như thế nào?
Bạn giải thích cách WebAppClassLoader cô lập thư viện ứng dụng với thư viện server như thế nào?
Bạn xác định nguyên nhân xung đột dependency hoặc NoSuchMethodError khi WAR chạy trên Jetty ra sao?
Bạn đánh giá ảnh hưởng của parent-first và webapp-first classloading tới khả năng tương thích thư viện như thế nào?
Bạn kiểm tra classloader leak sau nhiều lần redeploy bằng thread, static reference và heap dump ra sao?
Bạn cấu hình context attributes, init parameters và environment entries để truyền cấu hình cho web application như thế nào?
Bạn tổ chức session và tài nguyên ứng dụng để tránh giữ tham chiếu tới classloader sau undeploy ra sao?
Bạn mô tả vòng đời Servlet, Filter và Listener trong ServletContext như thế nào?
Bạn xác định thứ tự Filter mapping ảnh hưởng tới authentication, logging và xử lý request ra sao?
Bạn lựa chọn async servlet processing khi request phụ thuộc vào một tác vụ I/O kéo dài như thế nào?
Bạn phân biệt Servlet async API với non-blocking ReadListener và WriteListener về cách xử lý dữ liệu như thế nào?
Bạn thiết kế streaming response để gửi dữ liệu lớn mà không buffer toàn bộ nội dung trong bộ nhớ ra sao?
Bạn xác định rủi ro blocking operation trong callback hoặc thread xử lý của Jetty như thế nào?
Bạn kiểm soát backpressure khi producer tạo response nhanh hơn client có thể đọc như thế nào?
Bạn giải thích cách Jetty xử lý HTTP/2 multiplexing và tác động tới luồng request đồng thời như thế nào?
Bạn cấu hình TLS connector với keystore, truststore và chứng chỉ phù hợp cho HTTP server như thế nào?
Bạn phân biệt TLS termination tại reverse proxy với TLS trực tiếp tại Jetty về trách nhiệm bảo mật ra sao?
Bạn xác định cách bật HTTP/2 cần ALPN và cấu hình TLS phù hợp theo phiên bản Jetty như thế nào?
Bạn kiểm tra lỗi handshake, certificate chain và hostname mismatch khi client không kết nối được ra sao?
Bạn thiết kế mutual TLS để xác thực client cho endpoint nội bộ trên Jetty như thế nào?
Bạn cấu hình forwarded headers hoặc proxy customizer để ứng dụng nhận đúng scheme, host và client address phía sau load balancer ra sao?
Bạn đánh giá rủi ro tin cậy header X-Forwarded-* từ client không nằm trong proxy tin cậy như thế nào?
Bạn phân tích lỗi 400, 404, 413, 429 và 5xx bằng access log cùng cấu hình Connector như thế nào?
Bạn giải thích session management trong Servlet Container và cách Jetty tạo, lưu và khôi phục HttpSession như thế nào?
Bạn lựa chọn session cookie name, path, Secure, HttpOnly và SameSite dựa trên mô hình truy cập nào?
Bạn xác định session timeout và chính sách invalidation phù hợp với nghiệp vụ và bảo mật ra sao?
Bạn đánh giá các lựa chọn session persistence hoặc distributed session cho nhiều Jetty node như thế nào?
Bạn phân biệt sticky session với session replication hoặc shared session store khi triển khai cluster ra sao?
Bạn kiểm tra khả năng serialize session attributes và rủi ro khi các node chạy phiên bản ứng dụng khác nhau như thế nào?
Bạn xử lý session fixation và session hijacking bằng cấu hình cookie cùng quy trình xác thực như thế nào?
Bạn giải thích WebSocket upgrade và cách Jetty quản lý kết nối hai chiều kéo dài như thế nào?
Bạn lựa chọn WebSocket endpoint hoặc handler theo phiên bản Jetty và API đang sử dụng ra sao?
Bạn xác định giới hạn idle timeout, message size và số kết nối WebSocket để bảo vệ tài nguyên như thế nào?
Bạn thiết kế heartbeat và xử lý reconnect cho WebSocket client khi node Jetty restart ra sao?
Bạn đánh giá ảnh hưởng của nhiều WebSocket session lâu dài tới memory, thread và connection capacity như thế nào?
Bạn cấu hình authentication và authorization cho Servlet endpoint và WebSocket endpoint trên Jetty như thế nào?
Bạn phân biệt constraint-based security, authenticator và security handler trong chuỗi xử lý request ra sao?
Bạn tổ chức tích hợp identity provider hoặc reverse proxy authentication với Jetty theo ranh giới tin cậy nào?
Bạn bảo vệ management endpoint, JMX và console quản trị Jetty khỏi truy cập trái phép như thế nào?
Bạn xác định những cấu hình HTTP security headers cần áp dụng tại Jetty hoặc tầng proxy ra sao?
Bạn theo dõi request rate, response status, latency và active connections để đánh giá sức khỏe Jetty như thế nào?
Bạn sử dụng JMX hoặc metrics integration để quan sát thread pool, connector và session statistics ra sao?
Bạn thiết kế access log có correlation ID mà không ghi cookie, token hoặc dữ liệu nhạy cảm như thế nào?
Bạn kết hợp log Jetty, application logs và distributed traces để điều tra một request chậm như thế nào?
Bạn xác định nguyên nhân latency tăng do thread pool, downstream, TLS handshake hay client đọc chậm bằng số liệu nào?
Bạn kiểm tra heap, direct buffer, garbage collection và số lượng session khi bộ nhớ Jetty tăng liên tục như thế nào?
Bạn phân biệt thread starvation với connection saturation khi request bắt đầu timeout như thế nào?
Bạn xây dựng health check để phân biệt tiến trình Jetty đang sống với ứng dụng đã sẵn sàng nhận traffic ra sao?
Bạn lựa chọn các chỉ số và ngưỡng cảnh báo cho thread utilization, request latency, error rate và connection count như thế nào?
Bạn thiết kế load test để đánh giá throughput, p95/p99 latency và khả năng phục hồi sau burst trên Jetty như thế nào?
Bạn xác định nguyên nhân một Jetty server có CPU thấp nhưng response time cao bằng thread dump và access log như thế nào?
Bạn điều tra memory leak hoặc classloader leak sau nhiều lần deploy và undeploy như thế nào?
Bạn phân tích lỗi connection reset hoặc client disconnect trong khi server đang ghi response như thế nào?
Bạn xây dựng quy trình nâng cấp Jetty và xác minh tương thích WAR, Servlet API, TLS và plugin sau nâng cấp ra sao?
Bạn thiết kế runbook xác minh nguyên nhân gốc và hiệu quả khắc phục khi Jetty gặp lỗi deploy, timeout hoặc cạn tài nguyên như thế nào?
