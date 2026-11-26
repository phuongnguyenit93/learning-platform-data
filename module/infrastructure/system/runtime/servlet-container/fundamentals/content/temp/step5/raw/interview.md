Servlet container giải quyết những trách nhiệm nào khi chạy ứng dụng web Java theo Jakarta Servlet?
Bạn phân biệt trách nhiệm của servlet container với trách nhiệm của web framework như Spring MVC trong một request HTTP như thế nào?
Bạn mô tả đường đi của một HTTP request từ connector qua servlet mapping, filter chain và servlet đến response như thế nào?
Bạn phân biệt web server, servlet container và application server theo chức năng và phạm vi quản lý như thế nào?
Bạn giải thích vai trò của ServletContext và cách nó đại diện cho một web application trong container như thế nào?
Bạn xác định context path và servlet mapping ảnh hưởng đến URL được xử lý bởi ứng dụng như thế nào?
Bạn mô tả thứ tự ưu tiên mapping của servlet giữa exact match, longest path, extension và default mapping như thế nào?
Bạn xử lý trường hợp nhiều servlet mapping có vẻ cùng khớp một URL bằng cách áp dụng quy tắc mapping nào?
Bạn phân biệt mapping khai báo trong web.xml với mapping qua annotation và cách container hợp nhất cấu hình như thế nào?
Bạn kiểm tra vì sao request nhận 404 dù ứng dụng đã deploy thành công và servlet class có tồn tại như thế nào?
Bạn phân biệt các HTTP method được hỗ trợ bởi servlet và cách container xử lý method không được servlet triển khai như thế nào?
Bạn giải thích vai trò của HttpServlet.service và các phương thức doGet, doPost, doPut hoặc doDelete trong dispatch request như thế nào?
Bạn phân biệt request URI, context path, servlet path, path info và query string khi phân tích định tuyến như thế nào?
Bạn mô tả vòng đời Servlet từ khởi tạo, phục vụ nhiều request đồng thời đến khi container hủy servlet như thế nào?
Bạn giải thích vai trò của init, service và destroy, đồng thời xác định thời điểm container gọi từng phương thức như thế nào?
Bạn đánh giá ảnh hưởng của load-on-startup đến thời điểm khởi tạo servlet và thời gian phục vụ request đầu tiên như thế nào?
Bạn xác định vì sao một servlet instance thường phục vụ nhiều request đồng thời và thiết kế code để bảo đảm thread safety ra sao?
Bạn nhận diện trạng thái mutable dùng chung trong servlet có thể gây race condition khi nhiều request chạy đồng thời như thế nào?
Bạn phân biệt dữ liệu request-scoped, session-scoped và application-scoped để tránh chia sẻ nhầm trạng thái giữa người dùng như thế nào?
Bạn xử lý tài nguyên cần khởi tạo một lần và giải phóng khi web application dừng bằng lifecycle hook nào?
Bạn giải thích vì sao không nên tạo thread hoặc executor không được quản lý trong servlet rồi để chúng sống qua lần redeploy như thế nào?
Bạn mô tả Filter chain và vai trò của Filter trước và sau khi servlet xử lý request như thế nào?
Bạn phân biệt thứ tự filter mapping theo URL pattern và servlet name khi cấu hình nhiều filter như thế nào?
Bạn lựa chọn dispatcher type REQUEST, FORWARD, INCLUDE, ERROR hoặc ASYNC cho filter theo mục đích xử lý nào?
Bạn sử dụng Filter để thực hiện authentication, logging, CORS hoặc chuẩn hóa request mà không trộn logic nghiệp vụ như thế nào?
Bạn giải thích cách FilterChain.doFilter chuyển quyền xử lý sang filter tiếp theo hoặc servlet như thế nào?
Bạn xử lý trường hợp filter chặn request và tự tạo response mà không gọi doFilter như thế nào?
Bạn sử dụng HttpServletRequestWrapper hoặc HttpServletResponseWrapper để thay đổi hành vi request/response trong phạm vi nào?
Bạn phân biệt Filter với Spring MVC HandlerInterceptor về thời điểm chạy và phạm vi bao phủ request như thế nào?
Bạn lựa chọn Listener phù hợp để theo dõi vòng đời ServletContext, HttpSession hoặc ServletRequest như thế nào?
Bạn phân biệt context listener, session listener và request listener qua những sự kiện mà chúng nhận được như thế nào?
Bạn sử dụng attribute listener để theo dõi việc thêm, thay đổi hoặc xóa attribute trong application, session và request ra sao?
Bạn quản lý tài nguyên dùng chung của ứng dụng bằng ServletContextListener và bảo đảm giải phóng đúng lúc như thế nào?
Bạn đánh giá rủi ro khi listener tạo thread, đăng ký callback hoặc giữ tham chiếu tới classloader của web application như thế nào?
Bạn giải thích mô hình thread pool của servlet container và cách request được phân phối cho worker thread như thế nào?
Bạn phân biệt thread xử lý accept connection, xử lý I/O và xử lý servlet request trong kiến trúc connector như thế nào?
Bạn xác định ảnh hưởng của số worker thread, hàng đợi request và giới hạn kết nối đến throughput và latency như thế nào?
Bạn phân tích vì sao tăng max thread không luôn cải thiện khả năng xử lý và có thể làm cạn tài nguyên downstream như thế nào?
Bạn thiết kế xử lý request đồng thời để tránh giữ lock lâu hoặc thực hiện blocking I/O không cần thiết trên worker thread như thế nào?
Bạn đánh giá tác động của request chậm hoặc thread bị block đến các request khác khi container dùng thread pool hữu hạn như thế nào?
Bạn lựa chọn timeout cho connection, request, keep-alive và tác vụ nghiệp vụ theo SLA như thế nào?
Bạn mô tả cách HttpSession được tạo, định danh và liên kết với các request tiếp theo như thế nào?
Bạn phân biệt session tracking qua cookie JSESSIONID với URL rewriting và đánh giá ưu nhược điểm từng cách như thế nào?
Bạn thiết lập cookie session với HttpOnly, Secure và SameSite phù hợp với mô hình xác thực và triển khai HTTPS như thế nào?
Bạn giải thích session fixation và cách thay đổi session ID sau khi xác thực để giảm rủi ro như thế nào?
Bạn quản lý session timeout, invalidate và logout để thu hồi trạng thái người dùng như thế nào?
Bạn phân biệt session attribute với application attribute và đánh giá rủi ro khi lưu object mutable vào session như thế nào?
Bạn thiết kế session replication hoặc shared session store khi ứng dụng chạy nhiều container instance như thế nào?
Bạn xử lý yêu cầu sticky session và failover khi một instance chứa session state bị mất như thế nào?
Bạn đánh giá tác động của việc lưu object lớn hoặc không serialize được trong session đến bộ nhớ và khả năng cluster như thế nào?
Bạn giải thích AsyncContext cho phép servlet nhả container request thread trong khi chờ tác vụ I/O hoặc dịch vụ khác như thế nào?
Bạn mô tả vòng đời async request từ startAsync, xử lý nền, dispatch hoặc complete đến khi response kết thúc như thế nào?
Bạn xác định điều kiện async-supported cần có ở servlet và filter mapping để request có thể chạy bất đồng bộ như thế nào?
Bạn phân biệt AsyncContext.dispatch với complete và xác định khi nào mỗi thao tác phù hợp như thế nào?
Bạn sử dụng AsyncListener để xử lý timeout, error và completion của async request như thế nào?
Bạn thiết kế timeout và cancellation cho async request để tránh tác vụ nền tiếp tục chạy sau khi client đã ngắt kết nối như thế nào?
Bạn phân biệt Servlet asynchronous processing với non-blocking I/O của ServletInputStream và ServletOutputStream như thế nào?
Bạn sử dụng ReadListener và WriteListener để xử lý dữ liệu sẵn sàng đọc hoặc ghi mà không chặn thread như thế nào?
Bạn đánh giá rủi ro khi gọi blocking API hoặc chờ Future bên trong callback non-blocking của servlet như thế nào?
Bạn giải thích classloader isolation giữa web application và container, cùng quy tắc delegation khi nạp class như thế nào?
Bạn xử lý lỗi ClassNotFoundException, NoClassDefFoundError hoặc ClassCastException do thư viện trùng phiên bản giữa ứng dụng và container như thế nào?
Bạn phân biệt thư viện đặt trong WEB-INF/lib với thư viện dùng chung ở cấp container về phạm vi classloader như thế nào?
Bạn xác định nguy cơ memory leak sau redeploy do ThreadLocal, static reference, JDBC driver hoặc thread chưa dừng như thế nào?
Bạn quản lý tài nguyên JNDI như DataSource để ứng dụng dùng connection pool do container cung cấp như thế nào?
Bạn lựa chọn cấu hình deployment qua web.xml, annotation hoặc cấu hình container theo yêu cầu môi trường như thế nào?
Bạn mô tả quy trình deploy và undeploy WAR, bao gồm việc kiểm tra context path, dependency và trạng thái ứng dụng như thế nào?
Bạn phân biệt ứng dụng chạy trên external servlet container với embedded container trong Spring Boot về đóng gói, cấu hình và vận hành như thế nào?
Bạn xác định những cấu hình connector nào cần điều chỉnh khi triển khai ứng dụng sau reverse proxy hoặc load balancer như thế nào?
Bạn thiết lập xử lý forwarded headers và remote address để ứng dụng nhận đúng scheme, host và client IP mà không tin proxy không đáng tin cậy ra sao?
Bạn lựa chọn kết thúc TLS tại reverse proxy hay servlet container dựa trên yêu cầu mã hóa và ranh giới mạng như thế nào?
Bạn cấu hình giới hạn kích thước request body, multipart upload và timeout để bảo vệ container trước request quá lớn như thế nào?
Bạn xử lý multipart request và quản lý tệp tạm để tránh rò rỉ tài nguyên hoặc lưu dữ liệu ngoài ý muốn ra sao?
Bạn cấu hình error page và xử lý exception để không lộ stack trace hoặc thông tin nội bộ cho client production như thế nào?
Bạn phân biệt lỗi 400, 401, 403, 404, 405, 413, 500 và 503 trong quá trình chẩn đoán ứng dụng servlet như thế nào?
Bạn áp dụng declarative security qua security constraint, role và authentication mechanism của Jakarta Servlet như thế nào?
Bạn phân biệt container-managed authentication với xác thực do ứng dụng hoặc framework tự triển khai như thế nào?
Bạn thiết kế bảo vệ session cookie, CSRF và luồng logout trong ứng dụng web chạy trên servlet container như thế nào?
Bạn kiểm tra quyền truy cập URL theo role và xử lý trường hợp user đã xác thực nhưng không đủ quyền như thế nào?
Bạn sử dụng access log, application log, JMX metric và thread dump để điều tra request chậm hoặc container quá tải như thế nào?
Bạn nhận diện thread pool exhaustion, stuck thread, connection pool exhaustion và memory pressure từ các dấu hiệu vận hành nào?
Bạn điều tra tình huống ứng dụng trả 503 hoặc ngừng nhận request dù process container vẫn đang chạy như thế nào?
Bạn phân biệt lỗi do servlet container, filter, servlet application và framework dispatcher khi một request thất bại như thế nào?
Bạn xác định ranh giới giữa DispatcherServlet của Spring MVC và servlet container trong mapping, lifecycle, threading và exception handling như thế nào?
Bạn thiết kế kiểm thử tích hợp để xác minh servlet mapping, filter order, session, async processing và security behavior trên container thực tế như thế nào?
Bạn xây dựng checklist nghiệm thu triển khai servlet application dựa trên tính đúng đắn HTTP, an toàn, khả năng mở rộng và khả năng chẩn đoán như thế nào?
