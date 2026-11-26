Bạn giải thích vị trí của Reactor Netty trong kiến trúc ứng dụng Java reactive và mối liên hệ với Reactor Core cùng Netty như thế nào?
Bạn phân biệt Reactor Netty với Netty thuần về mô hình lập trình và cách tích hợp Reactor như thế nào?
Bạn xác định những trường hợp phù hợp để dùng Reactor Netty thay cho client hoặc server I/O đồng bộ ra sao?
Bạn mô tả luồng xử lý một HTTP request từ socket đến publisher và subscriber trong Reactor Netty như thế nào?
Bạn phân biệt API HTTP client, HTTP server và TCP client/server của Reactor Netty theo mục tiêu sử dụng ra sao?
Bạn giải thích event loop và vai trò của nó trong việc xử lý nhiều kết nối đồng thời như thế nào?
Bạn phân biệt event loop thread với worker thread hoặc thread xử lý nghiệp vụ trong ứng dụng reactive ra sao?
Bạn xác định vì sao một event loop có thể phục vụ nhiều channel và hệ quả khi một callback chạy quá lâu như thế nào?
Bạn phân tích dấu hiệu event loop bị block từ độ trễ, queue công việc và thread dump như thế nào?
Bạn lựa chọn cách chuyển một thao tác blocking sang scheduler phù hợp mà không làm nghẽn event loop ra sao?
Bạn đánh giá rủi ro dùng boundedElastic hoặc thread pool riêng cho mọi thao tác thay vì tìm cách loại bỏ blocking như thế nào?
Bạn giải thích cách Reactor Netty quản lý và tái sử dụng event loop resources giữa nhiều client hoặc server như thế nào?
Bạn xác định khi nào nên dùng tài nguyên loop dùng chung và khi nào cần cấu hình LoopResources riêng như thế nào?
Bạn đánh giá ảnh hưởng của việc tạo nhiều HttpClient hoặc TcpClient với tài nguyên event loop riêng tới số thread và bộ nhớ ra sao?
Bạn thiết kế vòng đời khởi tạo và dispose tài nguyên Reactor Netty khi ứng dụng Spring khởi động hoặc dừng như thế nào?
Bạn xác định dấu hiệu tài nguyên event loop hoặc connection provider không được giải phóng sau khi ứng dụng redeploy ra sao?
Bạn mô tả cách Reactor Netty xây dựng HTTP server và xử lý request bất đồng bộ qua route hoặc handler như thế nào?
Bạn phân biệt xử lý request bằng Reactor Netty trực tiếp với tích hợp qua Spring WebFlux như thế nào?
Bạn thiết kế HTTP client gọi nhiều dịch vụ downstream và tổng hợp kết quả reactive mà không chặn thread ra sao?
Bạn giải thích cách TCP client và server xử lý inbound/outbound data theo dạng Flux hoặc ByteBuf như thế nào?
Bạn xác định khi nào nên dùng TCP thuần thay cho HTTP trong một giao thức ứng dụng riêng như thế nào?
Bạn lựa chọn cấu hình HTTP keep-alive và connection reuse để giảm chi phí thiết lập kết nối như thế nào?
Bạn phân tích tác động của connection churn và đóng mở socket liên tục tới CPU, latency và cổng ephemeral ra sao?
Bạn giải thích connection pool của Reactor Netty quản lý kết nối đang dùng, kết nối nhàn rỗi và yêu cầu chờ như thế nào?
Bạn lựa chọn maxConnections dựa trên concurrency, giới hạn downstream và năng lực hệ thống như thế nào?
Bạn xác định pending acquire queue và pendingAcquireMaxCount ảnh hưởng đến hành vi khi pool cạn kết nối ra sao?
Bạn phân biệt pending acquire timeout với connect timeout và response timeout trong quá trình gửi request như thế nào?
Bạn lựa chọn maxIdleTime và maxLifeTime để hạn chế kết nối stale hoặc quá lâu mà không tạo churn không cần thiết ra sao?
Bạn đánh giá eviction interval và chiến lược tái sử dụng kết nối theo đặc điểm backend như thế nào?
Bạn kiểm tra pool metrics để phân biệt thiếu kết nối với downstream phản hồi chậm như thế nào?
Bạn xác định nguy cơ connection pool exhaustion khi concurrency tăng nhưng thời gian giữ kết nối cũng tăng ra sao?
Bạn thiết kế giới hạn pool riêng theo từng host hoặc dịch vụ để một downstream không chiếm hết tài nguyên như thế nào?
Bạn đánh giá ảnh hưởng của HTTP/2 multiplexing tới số connection và số request đồng thời trong pool như thế nào?
Bạn xác định cách kiểm tra connection reuse và keep-alive thực tế bằng log hoặc metrics ra sao?
Bạn giải thích các lớp timeout khác nhau trong Reactor Netty và cách chúng bao phủ từng giai đoạn I/O như thế nào?
Bạn cấu hình connect timeout để giới hạn thời gian thiết lập TCP connection theo đặc điểm mạng như thế nào?
Bạn lựa chọn response timeout phù hợp với SLA của từng downstream thay vì một giá trị chung cho mọi request ra sao?
Bạn phân biệt read timeout và write timeout với timeout tổng thể của một nghiệp vụ như thế nào?
Bạn xác định cách đặt timeout cho thao tác chờ connection từ pool để request không xếp hàng vô hạn ra sao?
Bạn thiết kế deadline end-to-end khi một request gọi nối tiếp nhiều dịch vụ có timeout riêng như thế nào?
Bạn đánh giá ảnh hưởng của timeout quá ngắn gây retry storm và timeout quá dài làm cạn pool ra sao?
Bạn phân tích cách hủy request khi subscriber cancel và ảnh hưởng tới socket hoặc response đang truyền như thế nào?
Bạn giải thích cách cấu hình TLS cho Reactor Netty HTTP client và server như thế nào?
Bạn phân biệt trust configuration, certificate identity và hostname verification khi thiết lập TLS ra sao?
Bạn thiết kế mutual TLS để xác thực cả client lẫn server trong kết nối nội bộ như thế nào?
Bạn kiểm tra lỗi handshake, certificate expiry và trust chain khi kết nối TLS thất bại ra sao?
Bạn đánh giá ảnh hưởng của TLS handshake và session reuse tới CPU, latency và connection pooling như thế nào?
Bạn lựa chọn cấu hình protocol và cipher phù hợp với yêu cầu tương thích và bảo mật ra sao?
Bạn xác định cách reload hoặc xoay vòng certificate mà không gây gián đoạn các kết nối đang hoạt động như thế nào?
Bạn giải thích backpressure trong Reactor và cách nó điều tiết demand giữa publisher với subscriber như thế nào?
Bạn phân biệt backpressure ở tầng Reactor với TCP flow control và giới hạn buffer trong Netty ra sao?
Bạn xác định điều gì xảy ra khi producer phát dữ liệu nhanh hơn consumer có thể xử lý như thế nào?
Bạn lựa chọn buffer, batch hoặc giới hạn concurrency để kiểm soát luồng dữ liệu lớn ra sao?
Bạn đánh giá các chiến lược xử lý khi buffer đầy như drop, error hoặc giữ dữ liệu chờ theo yêu cầu nghiệp vụ nào?
Bạn thiết kế truyền file hoặc stream lớn qua HTTP mà tránh gom toàn bộ nội dung vào bộ nhớ như thế nào?
Bạn xác định rủi ro tích lũy DataBuffer hoặc ByteBuf khi ứng dụng giữ tham chiếu lâu hơn vòng đời request ra sao?
Bạn giải thích reference counting của Netty ByteBuf và trách nhiệm release trong pipeline như thế nào?
Bạn chẩn đoán memory leak liên quan ByteBuf khi ứng dụng dùng custom handler hoặc thao tác buffer thủ công như thế nào?
Bạn phân biệt heap memory với direct memory và đánh giá ảnh hưởng của pooled allocator tới bộ nhớ tiến trình ra sao?
Bạn kiểm tra leak detection và các dấu hiệu direct memory tăng bất thường khi tải cao như thế nào?
Bạn đánh giá nguy cơ copy buffer không cần thiết giữa các bước decode, transform và encode ra sao?
Bạn lựa chọn cấu hình allocator hoặc pooled buffer dựa trên workload và kết quả benchmark như thế nào?
Bạn xác định cách giới hạn kích thước request body và số byte được buffer để bảo vệ server như thế nào?
Bạn thiết kế xử lý lỗi reactive với onError, retry và fallback mà không che giấu lỗi downstream ra sao?
Bạn xác định điều kiện retry an toàn cho HTTP request dựa trên idempotency và trạng thái đã gửi dữ liệu như thế nào?
Bạn đánh giá rủi ro retry khi request đã được server xử lý nhưng client mất kết nối trước khi nhận response ra sao?
Bạn phân biệt lỗi connect, timeout, reset và HTTP error response khi xây dựng chính sách retry như thế nào?
Bạn thiết kế circuit breaker và bulkhead quanh Reactor Netty client để cô lập downstream không ổn định ra sao?
Bạn xác định cách giới hạn concurrency của các request outbound để tránh quá tải dịch vụ đích như thế nào?
Bạn lựa chọn cách xử lý cancellation và timeout để giải phóng connection pool capacity kịp thời ra sao?
Bạn giải thích cách bật metrics Reactor Netty và tích hợp Micrometer để theo dõi connection pool, event loop và HTTP request như thế nào?
Bạn lựa chọn các chỉ số active, idle, pending connections, connect time và response time để nhận diện pool pressure ra sao?
Bạn phân biệt latency ở giai đoạn pool acquire, connect, TLS handshake và response bằng những dữ liệu nào?
Bạn thiết kế dashboard theo dõi event loop utilization, pending tasks, connection pool và request latency như thế nào?
Bạn xác định tác động của metric cardinality khi gắn URL đầy đủ hoặc ID động vào tag như thế nào?
Bạn tổ chức tên metric và tag service, remote host, method, status theo quy ước ổn định ra sao?
Bạn kết hợp distributed tracing với Reactor context propagation để liên kết request xuyên dịch vụ như thế nào?
Bạn kiểm tra trace context có bị mất khi chuyển scheduler hoặc chạy callback bất đồng bộ như thế nào?
Bạn xác định cách log lỗi outbound request mà không ghi token, header hoặc payload nhạy cảm ra sao?
Bạn thiết kế kiểm thử HTTP client/server với timeout, cancellation, TLS và connection reuse như thế nào?
Bạn sử dụng StepVerifier hoặc công cụ test phù hợp để kiểm chứng hành vi reactive và backpressure ra sao?
Bạn tạo kịch bản tải đồng thời để phát hiện event loop blocking, pool exhaustion và direct memory leak như thế nào?
Bạn phân biệt lỗi do Reactor Netty với lỗi do DNS, proxy, firewall hoặc downstream service bằng bằng chứng nào?
Bạn điều tra trường hợp request latency tăng dù CPU thấp bằng cách phân tích pool pending, connect time và response time như thế nào?
Bạn xây dựng runbook xác minh nguyên nhân gốc và hiệu quả khắc phục khi ứng dụng Reactor Netty bị timeout hoặc cạn kết nối ra sao?
