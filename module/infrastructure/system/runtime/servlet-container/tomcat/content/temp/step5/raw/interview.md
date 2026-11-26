Apache Tomcat đảm nhiệm vai trò gì trong kiến trúc triển khai ứng dụng web Java?
Bạn sẽ phân biệt servlet container với full Jakarta EE application server theo phạm vi dịch vụ được cung cấp như thế nào?
Bạn sẽ mô tả các thành phần Server, Service, Engine, Host, Context và Wrapper trong cấu trúc Tomcat ra sao?
Bạn sẽ giải thích mối quan hệ giữa Catalina, Coyote và Jasper trong quá trình xử lý ứng dụng web như thế nào?
Bạn sẽ xác định một HTTP request đi từ connector qua container đến servlet và quay lại client theo các bước nào?
Bạn sẽ phân biệt cấu hình toàn máy chủ trong server.xml với cấu hình riêng của một web application như thế nào?
Bạn sẽ xác định khi nào nên dùng virtual host để phục vụ nhiều website trên cùng một Tomcat instance ra sao?
Bạn sẽ mô tả vòng đời khởi động, triển khai ứng dụng và shutdown của Tomcat như thế nào?
Bạn sẽ phân biệt connector HTTP/1.1, HTTP/2 và AJP theo mục đích cùng ranh giới tin cậy ra sao?
Bạn sẽ giải thích vai trò của Coyote connector trong việc nhận kết nối và chuyển request vào container như thế nào?
Bạn sẽ lựa chọn NIO, NIO2 hoặc protocol handler phù hợp theo phiên bản Tomcat và đặc điểm tải ra sao?
Bạn sẽ phân biệt maxThreads, maxConnections và acceptCount trong cấu hình connector như thế nào?
Bạn sẽ xác định cách đặt connectionTimeout và keepAliveTimeout để cân bằng tài nguyên với trải nghiệm client ra sao?
Bạn sẽ phân tích điều gì xảy ra khi số kết nối vượt maxConnections hoặc hàng đợi accept đạt giới hạn như thế nào?
Bạn sẽ cấu hình giới hạn request header, body và upload size để giảm nguy cơ tiêu thụ tài nguyên quá mức ra sao?
Bạn sẽ phân biệt lỗi TLS handshake ở connector với lỗi xử lý HTTP bên trong servlet như thế nào?
Bạn sẽ mô tả quá trình khởi tạo servlet từ lúc container load class đến khi gọi init như thế nào?
Bạn sẽ giải thích các giai đoạn init, service và destroy trong servlet lifecycle như thế nào?
Bạn sẽ phân biệt doGet, doPost và phương thức service trong cách servlet xử lý HTTP request ra sao?
Bạn sẽ xác định khi nào Tomcat tạo instance servlet và cách nhiều request đồng thời được xử lý trên instance đó như thế nào?
Bạn sẽ phân tích rủi ro khi servlet lưu dữ liệu request vào instance field trong môi trường đa luồng ra sao?
Bạn sẽ mô tả vòng đời và thứ tự thực thi của Servlet Filter trong request và response như thế nào?
Bạn sẽ lựa chọn filter cho authentication, authorization, logging và request wrapping theo thứ tự nào?
Bạn sẽ phân biệt Filter, Servlet Listener và Servlet trong trách nhiệm xử lý vòng đời ứng dụng như thế nào?
Bạn sẽ giải thích vai trò của ServletContextListener khi ứng dụng khởi động và dừng như thế nào?
Bạn sẽ thiết kế xử lý async request bằng AsyncContext để không giữ worker thread trong lúc chờ I/O ra sao?
Bạn sẽ phân tích những điều kiện khiến async servlet vẫn tiêu thụ thread hoặc tài nguyên ngoài dự kiến như thế nào?
Bạn sẽ xác định cách xử lý exception và error dispatch để response không bị ghi dở hoặc commit quá sớm ra sao?
Bạn sẽ mô tả cách Tomcat ánh xạ context path, servlet mapping và filter mapping cho một request như thế nào?
Bạn sẽ giải thích classloader hierarchy của Tomcat và phạm vi nhìn thấy class giữa Common, System và Webapp loader ra sao?
Bạn sẽ phân tích cơ chế web application classloader ưu tiên class trong ứng dụng và các ngoại lệ parent-first như thế nào?
Bạn sẽ xác định nguyên nhân hai ứng dụng WAR dùng hai phiên bản thư viện khác nhau nhưng vẫn chạy độc lập ra sao?
Bạn sẽ xử lý lỗi ClassNotFoundException, NoClassDefFoundError và LinkageError khi deploy WAR bằng những bước nào?
Bạn sẽ đánh giá rủi ro đặt thư viện dùng chung trong thư mục lib của Tomcat thay vì WEB-INF/lib của từng ứng dụng như thế nào?
Bạn sẽ giải thích vì sao thread, ThreadLocal hoặc JDBC driver còn tham chiếu classloader có thể gây memory leak sau undeploy ra sao?
Bạn sẽ kiểm tra xung đột phiên bản thư viện servlet API hoặc Jakarta API giữa container và WAR như thế nào?
Bạn sẽ phân biệt namespace javax.servlet và jakarta.servlet khi nâng cấp ứng dụng từ Tomcat 9 lên Tomcat 10 như thế nào?
Bạn sẽ mô tả quy trình triển khai WAR vào Tomcat qua thư mục webapps và cơ chế autoDeploy như thế nào?
Bạn sẽ phân biệt deploy WAR nguyên bản với triển khai thư mục exploded về tốc độ, cập nhật và vận hành ra sao?
Bạn sẽ giải thích vai trò của unpackWARs, deployOnStartup và autoDeploy trong quy trình deploy như thế nào?
Bạn sẽ lựa chọn cấu hình context descriptor trong META-INF/context.xml hay vị trí cấu hình bên ngoài theo môi trường nào?
Bạn sẽ thiết kế quy trình deploy phiên bản mới để giảm downtime và tránh request đi vào ứng dụng đang khởi động như thế nào?
Bạn sẽ phân biệt rollback bằng WAR phiên bản trước với redeploy lại cùng artifact đã thay đổi ra sao?
Bạn sẽ xử lý xung đột context path hoặc tên ứng dụng khi nhiều WAR được triển khai trên cùng Host như thế nào?
Bạn sẽ giải thích session HTTP được tạo, nhận diện và gắn với request tiếp theo bằng cookie JSESSIONID như thế nào?
Bạn sẽ phân biệt session cookie, cookie persistent và URL rewriting trong việc duy trì trạng thái người dùng ra sao?
Bạn sẽ cấu hình session timeout và đánh giá ảnh hưởng của timeout đến bộ nhớ khi lượng người dùng tăng như thế nào?
Bạn sẽ lựa chọn session lưu trong memory, persistent store hay external session service dựa trên yêu cầu triển khai nào?
Bạn sẽ mô tả cách Tomcat xử lý session khi một instance restart hoặc người dùng được chuyển sang instance khác như thế nào?
Bạn sẽ đánh giá các phương án sticky session, session replication và external session store trong cụm Tomcat ra sao?
Bạn sẽ xác định những thuộc tính nào của session object cần serializable khi dùng cơ chế replication hoặc persistence như thế nào?
Bạn sẽ phân tích rủi ro khi lưu object lớn hoặc dữ liệu nhạy cảm trong HTTP session ra sao?
Bạn sẽ thiết kế cookie session với HttpOnly, Secure và SameSite để giảm nguy cơ đánh cắp hoặc gửi cookie sai ngữ cảnh như thế nào?
Bạn sẽ xử lý session fixation khi người dùng đăng nhập và quyền truy cập của session thay đổi ra sao?
Bạn sẽ xác định nguyên nhân session bị mất sau deploy hoặc sau khi load balancer chuyển request sang node khác như thế nào?
Bạn sẽ giải thích JNDI naming trong Tomcat giúp ứng dụng tra cứu tài nguyên dùng chung như thế nào?
Bạn sẽ cấu hình JNDI DataSource trong Tomcat và tham chiếu tài nguyên đó từ ứng dụng web ra sao?
Bạn sẽ phân biệt khai báo Resource trong server.xml, context.xml và resource-ref trong web.xml theo vai trò như thế nào?
Bạn sẽ lựa chọn Tomcat JDBC Pool hoặc DBCP2 dựa trên tính năng, khả năng giám sát và đặc điểm workload ra sao?
Bạn sẽ quản lý username, password và secret của JNDI DataSource mà không ghi trực tiếp vào WAR hoặc repository như thế nào?
Bạn sẽ xác định cách ứng dụng lấy và đóng Connection từ DataSource để trả connection về pool khi có exception ra sao?
Bạn sẽ cấu hình maxActive hoặc maxTotal, maxIdle, minIdle và maxWait dựa trên giới hạn database và concurrency như thế nào?
Bạn sẽ phân biệt connection pool exhaustion với database chậm khi request phải chờ lấy connection như thế nào?
Bạn sẽ lựa chọn validation query, testOnBorrow và eviction policy để loại connection không còn hợp lệ ra sao?
Bạn sẽ kiểm tra leak detection và abandoned connection handling để tìm code không đóng connection như thế nào?
Bạn sẽ cấu hình TLS connector trong Tomcat với keystore, certificate chain và private key theo yêu cầu nào?
Bạn sẽ lựa chọn TLS protocol và cipher suite để bảo đảm tương thích client nhưng loại bỏ cấu hình yếu như thế nào?
Bạn sẽ phân biệt TLS termination tại load balancer hoặc reverse proxy với TLS trực tiếp tại Tomcat ra sao?
Bạn sẽ cấu hình proxyName, proxyPort hoặc RemoteIpValve để Tomcat nhận diện đúng scheme, host và client IP phía trước proxy như thế nào?
Bạn sẽ kiểm soát độ tin cậy của X-Forwarded-For và các forwarded headers để tránh giả mạo địa chỉ client ra sao?
Bạn sẽ phân tích nguyên nhân redirect tạo URL HTTP thay vì HTTPS khi Tomcat chạy sau reverse proxy như thế nào?
Bạn sẽ bảo vệ AJP connector và xác định khi nào nên tắt connector này nếu không có nhu cầu sử dụng ra sao?
Bạn sẽ lựa chọn AccessLogValve pattern để ghi nhận request, status, latency và client IP mà không lưu dữ liệu nhạy cảm như thế nào?
Bạn sẽ phân biệt catalina log, localhost log, access log và application log trong quá trình điều tra sự cố ra sao?
Bạn sẽ cấu hình logging framework và JULI để kiểm soát log level, rotation và tránh ghi trùng log như thế nào?
Bạn sẽ phân tích rủi ro ghi Authorization header, cookie hoặc query string nhạy cảm vào access log như thế nào?
Bạn sẽ sử dụng JMX và Manager Status để theo dõi thread pool, connector, session và datasource pool như thế nào?
Bạn sẽ lựa chọn những JVM và Tomcat metrics cần theo dõi để phát hiện thread exhaustion, heap pressure và request latency ra sao?
Bạn sẽ thu thập thread dump khi Tomcat phản hồi chậm và xác định worker thread bị block ở đâu như thế nào?
Bạn sẽ phân biệt maxThreads đã cạn với connection backlog tăng hoặc database pool cạn bằng các chỉ số nào?
Bạn sẽ xác định nguyên nhân HTTP 404, 500, 502 và 503 từ access log, application log và connector metrics như thế nào?
Bạn sẽ chẩn đoán ứng dụng khởi động thất bại do lỗi cấu hình, thiếu class hoặc JNDI resource bằng quy trình nào?
Bạn sẽ phân tích memory leak sau nhiều lần redeploy và tìm thread hoặc static reference còn giữ Webapp classloader ra sao?
Bạn sẽ đánh giá tác động của GC pause, heap sizing và thread stack size đến latency của Tomcat như thế nào?
Bạn sẽ lựa chọn kích thước connector thread pool dựa trên thời gian xử lý request, tỷ lệ I/O wait và số CPU khả dụng ra sao?
Bạn sẽ kiểm tra slow request và xác định bottleneck ở servlet, database, downstream HTTP hoặc filesystem bằng cách nào?
Bạn sẽ thiết kế graceful shutdown để ngừng nhận request mới, hoàn tất request đang chạy và đóng tài nguyên ứng dụng ra sao?
Bạn sẽ tổ chức rolling deployment nhiều Tomcat instance để tránh downtime và kiểm soát session trong thời gian chuyển đổi như thế nào?
Bạn sẽ xây dựng bài kiểm thử tải cho Tomcat để đo throughput, p95/p99 latency, error rate, thread usage và connection pool ra sao?
Bạn sẽ thiết lập tiêu chí nghiệm thu về bảo mật TLS, classloader isolation, session, JNDI, logging, monitoring và khả năng phục hồi trước khi vận hành Tomcat production như thế nào?
