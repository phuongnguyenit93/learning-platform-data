Bạn giải thích Reactor Netty giải quyết vấn đề gì khi xây dựng ứng dụng mạng bất đồng bộ bằng Java?
Bạn phân biệt vai trò của Project Reactor, Reactor Netty và Netty trong cùng một ứng dụng như thế nào?
Bạn lựa chọn Reactor Netty thay cho server dùng một thread cho mỗi kết nối dựa trên tiêu chí nào?
Bạn giải thích cơ chế event loop giúp xử lý nhiều kết nối với ít thread như thế nào?
Bạn phân biệt non-blocking I/O với việc thực thi đồng thời trên nhiều CPU core ra sao?
Bạn thiết kế ranh giới giữa xử lý mạng và xử lý nghiệp vụ khi dùng Reactor Netty như thế nào?
Bạn đánh giá những loại tải công việc nào không phù hợp để chạy trực tiếp trên event loop?
Bạn giải thích vai trò của Channel, EventLoop và ChannelPipeline trong Netty như thế nào?
Bạn phân biệt inbound event và outbound operation trong đường đi dữ liệu của một connection ra sao?
Bạn mô tả vòng đời của một kết nối từ lúc thiết lập đến khi đóng trong Reactor Netty như thế nào?
Bạn xác định khi nào một kết nối cần được tái sử dụng và khi nào cần đóng sau request ra sao?
Bạn tổ chức cấu hình dùng chung cho nhiều client mà không làm rò rỉ trạng thái request như thế nào?
Bạn phân tích tác động của việc tạo HttpClient hoặc TcpClient mới quá thường xuyên ra sao?
Bạn giải thích vì sao reactive API trả về Mono hoặc Flux không đồng nghĩa với việc luôn tạo một thread mới?
Bạn phân biệt cold publisher và hot publisher khi làm việc với dữ liệu mạng thời gian thực như thế nào?
Bạn xác định thời điểm kết nối mạng thực sự được khởi tạo trong một chuỗi reactive ra sao?
Bạn giải thích sự khác nhau giữa subscribe, request, onNext, onError và onComplete trong luồng dữ liệu mạng như thế nào?
Bạn phân biệt lỗi xảy ra khi tạo cấu hình client với lỗi xuất hiện sau khi subscribe như thế nào?
Bạn dùng cách nào để xử lý lỗi và giải phóng tài nguyên khi một stream bị hủy giữa chừng?
Bạn xác định khi nào nên tái sử dụng một pipeline reactive và khi nào phải tạo pipeline riêng cho từng request?
Bạn đánh giá các rủi ro của việc gọi block trên thread xử lý I/O của Reactor Netty như thế nào?
Bạn tích hợp thư viện JDBC blocking vào một ứng dụng Reactor Netty mà không chặn event loop ra sao?
Bạn lựa chọn boundedElastic hoặc scheduler tùy chỉnh để cô lập thao tác blocking dựa trên yếu tố nào?
Bạn phân biệt publishOn và subscribeOn khi một luồng HTTP cần chuyển điểm thực thi giữa các scheduler ra sao?
Bạn phân tích tác động của flatMap concurrency lên số request hoặc connection đồng thời như thế nào?
Bạn giữ thứ tự kết quả khi một Flux xử lý dữ liệu mạng song song bằng những toán tử nào?
Bạn xác định những tác vụ CPU-bound nào cần được giới hạn hoặc chuyển sang scheduler riêng ra sao?
Bạn tổ chức cancellation từ client tới công việc backend để tránh xử lý tiếp dữ liệu không ai nhận như thế nào?
Bạn dùng doOnError, doFinally và các cơ chế quản lý tài nguyên reactive để quan sát kết thúc luồng như thế nào?
Bạn phát hiện một publisher bị subscribe nhiều lần dẫn đến gửi request HTTP lặp ngoài ý muốn ra sao?
Bạn phân biệt backpressure ở Reactive Streams với giới hạn số connection tại tầng transport như thế nào?
Bạn giải thích demand từ subscriber có thể ảnh hưởng tới việc đọc dữ liệu mạng như thế nào?
Bạn xử lý nguồn dữ liệu đẩy nhanh hơn consumer và không thể giảm tốc độ như thế nào?
Bạn chọn buffer, drop hoặc latest-value strategy cho loại dữ liệu mạng nào?
Bạn đánh giá rủi ro memory leak hoặc tăng latency khi dùng buffer không giới hạn trong Flux như thế nào?
Bạn kiểm soát kích thước batch và concurrency khi gửi một lượng lớn request HTTP ra sao?
Bạn thiết kế cơ chế giới hạn số stream đang xử lý để tránh một tenant chiếm hết tài nguyên như thế nào?
Bạn xây dựng HTTP server bằng HttpServer.create và xác định địa chỉ lắng nghe như thế nào?
Bạn cấu hình port và host của HTTP server theo môi trường local, test và production ra sao?
Bạn thiết kế route GET và POST với HttpServer.route để tách tầng HTTP và nghiệp vụ ra sao?
Bạn đọc path parameter và query parameter trong HTTP server mà vẫn kiểm soát dữ liệu đầu vào như thế nào?
Bạn nhận request body dạng stream mà không phải giữ toàn bộ payload trong bộ nhớ như thế nào?
Bạn quyết định khi nào nên aggregate request body và khi nào phải xử lý từng chunk ra sao?
Bạn thiết kế phản hồi HTTP dạng chuỗi hoặc ByteBuf với nội dung và Content-Type phù hợp như thế nào?
Bạn lựa chọn HTTP status code dựa trên kết quả xử lý nghiệp vụ trong Reactor Netty server ra sao?
Bạn xử lý HTTP request thiếu header bắt buộc hoặc body không hợp lệ ở tầng nào?
Bạn phân biệt việc đọc request body rỗng với request body chưa gửi đủ dữ liệu như thế nào?
Bạn xử lý trường hợp client gửi body chậm rồi ngắt kết nối giữa chừng ra sao?
Bạn giới hạn kích thước HTTP request để ngăn một client dùng hết bộ nhớ như thế nào?
Bạn kiểm soát kích thước response và cơ chế streaming khi trả một tệp lớn ra sao?
Bạn thiết kế xử lý upload và download sao cho cancellation giải phóng tài nguyên đúng thời điểm như thế nào?
Bạn xác định chính sách keep-alive cho HTTP server dựa trên loại tải và gateway phía trước ra sao?
Bạn mô tả các trường hợp server phải đóng connection sau khi gửi HTTP response như thế nào?
Bạn phân biệt HTTP/1.1 pipelining và HTTP/2 multiplexing về khả năng xử lý nhiều request ra sao?
Bạn đánh giá chi phí hỗ trợ HTTP/2 trên một server có nhiều kết nối lâu dài như thế nào?
Bạn lựa chọn cấu hình compression response dựa trên kích thước payload và chi phí CPU ra sao?
Bạn thiết kế cách phản hồi client đã hủy request mà không tiếp tục gửi dữ liệu vô ích như thế nào?
Bạn thực hiện graceful shutdown HTTP server khi còn request đang xử lý như thế nào?
Bạn phân biệt bind và bindNow trong vòng đời khởi động HTTP server ra sao?
Bạn xử lý trường hợp không thể bind port vì địa chỉ đã được sử dụng như thế nào?
Bạn cấu hình timeout đọc request HTTP để chống kết nối gửi dữ liệu quá chậm ra sao?
Bạn thiết kế middleware hoặc handler dùng chung để gắn trace ID vào phản hồi như thế nào?
Bạn ngăn thao tác blocking trong handler HTTP làm chậm các connection khác như thế nào?
Bạn xử lý trường hợp một exception xuất hiện sau khi response headers đã được gửi ra sao?
Bạn kiểm soát việc gửi response duy nhất một lần khi nhiều nhánh reactive cùng có khả năng trả lỗi như thế nào?
Bạn xác định tiêu chí chọn Reactor Netty HTTP server trực tiếp so với Spring WebFlux framework như thế nào?
Bạn tạo HttpClient dùng chung và thiết lập base URI hoặc địa chỉ đích theo cấu hình như thế nào?
Bạn lựa chọn cách xây dựng URI có path và query parameter để tránh double encoding ra sao?
Bạn xác định method, request headers và body của một HTTP request bất đồng bộ như thế nào?
Bạn truyền authentication header vào từng request mà không lộ secret qua log ra sao?
Bạn đọc HTTP status và response headers trước khi quyết định giải mã nội dung như thế nào?
Bạn phân biệt responseSingle với responseContent khi xử lý phản hồi nhỏ và lớn ra sao?
Bạn giải mã response body thành văn bản hoặc JSON mà vẫn tôn trọng charset như thế nào?
Bạn xử lý một HTTP response thành công nhưng payload không đúng schema hợp đồng như thế nào?
Bạn phân loại lỗi HTTP 4xx, 5xx và lỗi kết nối trong một client adapter ra sao?
Bạn xây dựng cơ chế retry cho request idempotent mà không tự động retry thao tác có side effect như thế nào?
Bạn xử lý trường hợp server đã thực thi POST nhưng kết nối mất trước khi response đến ra sao?
Bạn áp dụng Retry-After và backoff có jitter khi upstream trả 429 như thế nào?
Bạn phân biệt redirect HTTP với kết nối lại khi TCP bị mất trong ứng dụng client ra sao?
Bạn kiểm soát việc gửi Authorization header qua redirect sang origin khác như thế nào?
Bạn quyết định có nén request body hoặc chấp nhận compressed response dựa trên tiêu chí nào?
Bạn thiết kế cách upload file lớn qua HttpClient mà không giữ toàn bộ tệp trong heap ra sao?
Bạn xử lý download bị hủy giữa chừng để không giữ connection hoặc file handle như thế nào?
Bạn quản lý request body chỉ đọc một lần khi retry có thể kích hoạt subscribe lại như thế nào?
Bạn phân biệt giới hạn số HTTP request đồng thời với giới hạn connection pool như thế nào?
Bạn thiết kế client gọi nhiều upstream với timeout và pool riêng để tránh lan truyền sự cố ra sao?
Bạn đánh giá tác động của DNS resolution khi một hostname của upstream đổi địa chỉ như thế nào?
Bạn xác định cách cấu hình proxy HTTP hoặc SOCKS dựa trên yêu cầu mạng doanh nghiệp ra sao?
Bạn xử lý yêu cầu truy cập endpoint từ dữ liệu người dùng để giảm nguy cơ SSRF như thế nào?
Bạn kiểm soát redirect và DNS khi host đích bị lợi dụng truy cập mạng nội bộ ra sao?
Bạn triển khai circuit breaker ở tầng ứng dụng khi dùng Reactor Netty HttpClient theo cơ chế nào?
Bạn phối hợp retry, concurrency limit và timeout để tránh khuếch đại tải lên upstream như thế nào?
Bạn thiết lập giới hạn kích thước response khi upstream có thể trả một payload bất thường ra sao?
Bạn tổ chức lifecycle của HttpClient để không tạo tài nguyên mạng mới trong mỗi lời gọi ra sao?
Bạn xác định những trường hợp nên dùng WebSocket thay cho polling HTTP khi xây dựng ứng dụng realtime như thế nào?
Bạn thiết kế cơ chế nhận và gửi WebSocket frame khi ứng dụng sử dụng Reactor Netty như thế nào?
Bạn xử lý WebSocket ping, pong và close để phát hiện peer đã ngắt kết nối ra sao?
Bạn phân biệt fragmentation của WebSocket với việc chia nhỏ dữ liệu TCP như thế nào?
Bạn giới hạn kích thước WebSocket message và số kết nối mở để tránh quá tải như thế nào?
Bạn xây dựng TCP server bất đồng bộ bằng TcpServer và xác định điểm lắng nghe ra sao?
Bạn tạo TCP client bằng TcpClient và quản lý phiên kết nối tới server như thế nào?
Bạn phân biệt TCP stream với message có ranh giới rõ ràng khi thiết kế giao thức ứng dụng ra sao?
Bạn lựa chọn length-prefix framing, delimiter hoặc fixed-length framing theo yêu cầu dữ liệu nào?
Bạn xử lý trường hợp một message TCP bị chia thành nhiều lần nhận như thế nào?
Bạn xử lý hai message ứng dụng bị gộp trong một lần đọc TCP như thế nào?
Bạn thiết kế encoder và decoder Netty cho một giao thức TCP nhị phân như thế nào?
Bạn xác định khi nào cần thêm ChannelHandler tùy chỉnh vào pipeline ra sao?
Bạn phân biệt handler inbound và outbound khi thao tác với ChannelPipeline như thế nào?
Bạn sử dụng Netty channel attributes hoặc connection context để giữ trạng thái phiên theo giới hạn nào?
Bạn xử lý half-close của TCP khi một phía ngừng gửi nhưng vẫn cần nhận như thế nào?
Bạn phát hiện một TCP connection nhàn rỗi quá lâu mà vẫn chưa có EOF bằng cách nào?
Bạn cấu hình TCP keepalive và heartbeat ở tầng ứng dụng theo những yêu cầu nào?
Bạn phân biệt TCP_NODELAY với cơ chế gom dữ liệu trong ứng dụng và ảnh hưởng tới latency như thế nào?
Bạn giải thích receive window và send buffer ở TCP ảnh hưởng throughput như thế nào?
Bạn xử lý lỗi connection reset trong lúc gửi dữ liệu mà không biết peer đã nhận bao nhiêu byte ra sao?
Bạn thiết kế reconnect cho TcpClient khi upstream restart mà không gây vòng lặp kết nối quá nhanh như thế nào?
Bạn đánh giá cần hay không cần application-level acknowledgment trên TCP cho dữ liệu nghiệp vụ ra sao?
Bạn phân biệt việc ghi thành công vào socket buffer với việc phía nhận đã xử lý message như thế nào?
Bạn tổ chức tuần tự các lần write trên cùng một TCP connection khi dữ liệu phụ thuộc thứ tự như thế nào?
Bạn xử lý trạng thái tồn đọng outbound khi client chậm đọc mà producer vẫn gửi liên tục ra sao?
Bạn áp dụng giới hạn số TCP connection và pending work để ngăn quá tải server như thế nào?
Bạn thiết kế graceful shutdown của TCP server khi một số client đang trao đổi dữ liệu dang dở ra sao?
Bạn chọn UDP thay vì TCP cho luồng telemetry hoặc sự kiện realtime dựa trên những tiêu chí nào?
Bạn tạo UDP server hoặc client bằng Reactor Netty và quản lý địa chỉ local/remote ra sao?
Bạn phân biệt socket UDP dạng datagram với TCP connection stream về cách nhận dữ liệu như thế nào?
Bạn xác định ranh giới message dựa trên datagram thay vì tự dựng framing như TCP ra sao?
Bạn xử lý datagram bị mất, trùng hoặc đến sai thứ tự trong ứng dụng nghiệp vụ như thế nào?
Bạn thiết kế sequence number và logic deduplication cho một luồng dữ liệu chạy trên UDP ra sao?
Bạn cân nhắc kích thước datagram để hạn chế IP fragmentation bằng cách nào?
Bạn đánh giá hành vi của ứng dụng khi một datagram vượt kích thước buffer nhận như thế nào?
Bạn thiết kế cơ chế timeout và retry riêng của ứng dụng khi UDP không xác nhận delivery ra sao?
Bạn xác định lúc nào nên bổ sung acknowledgment trên UDP và chi phí kéo theo là gì?
Bạn phân biệt unicast, multicast và broadcast khi chọn mô hình phát UDP ra sao?
Bạn quản lý thành viên nhóm multicast và cấu hình mạng để nhận datagram như thế nào?
Bạn cân nhắc vấn đề UDP packet loss do quá tải NIC hoặc socket receive buffer ra sao?
Bạn áp dụng giới hạn tốc độ gửi để tránh làm tràn buffer của bên nhận UDP như thế nào?
Bạn đánh giá những ràng buộc về bảo mật và xác thực payload khi sử dụng UDP như thế nào?
Bạn kiểm thử độ trễ, packet loss và jitter của UDP trong những điều kiện mạng nào?
Bạn lựa chọn phương thức chuyển một thông điệp từ UDP sang xử lý reactive phía backend như thế nào?
Bạn đánh giá tác động khi xử lý CPU-bound ngay trong callback nhận datagram UDP như thế nào?
Bạn theo dõi các metric nào để nhận diện mất gói và xử lý chậm trong một dịch vụ UDP?
Bạn giải thích mục đích của ByteBuf trong Netty và sự khác nhau với byte array Java như thế nào?
Bạn phân biệt heap buffer và direct buffer trong những đường truyền dữ liệu nào?
Bạn đánh giá lợi ích của pooled allocator so với cấp phát buffer mới cho mỗi message ra sao?
Bạn giải thích cơ chế reference counting của ByteBuf và trách nhiệm release như thế nào?
Bạn xác định khi nào retain cần thiết nếu chuyển ByteBuf sang xử lý bất đồng bộ ngoài callback ra sao?
Bạn phân biệt slice, duplicate và copy ByteBuf về việc chia sẻ vùng nhớ như thế nào?
Bạn xử lý ByteBuf được chuyển qua nhiều operator reactive mà vẫn tránh use-after-release như thế nào?
Bạn phát hiện rò rỉ ByteBuf bằng các công cụ hoặc dấu hiệu runtime nào?
Bạn quyết định chuyển ByteBuf sang String, byte[] hoặc ByteBuffer dựa trên yêu cầu nào?
Bạn đánh giá chi phí copy dữ liệu khi nhiều tầng codec cùng serialize và deserialize ra sao?
Bạn sử dụng ByteBufFlux hoặc ByteBufMono để nhận và chuyển đổi nội dung với lưu ý gì về vòng đời buffer?
Bạn tổ chức write của ByteBuf ở outbound sao cho không double-release hoặc ghi sau khi giải phóng ra sao?
Bạn giới hạn mức aggregate nội dung khi payload đến dưới dạng nhiều buffer nhỏ như thế nào?
Bạn phân biệt ByteBuf ref-count leak với heap memory leak qua các chỉ số nào?
Bạn xử lý lỗi xảy ra giữa quá trình decode một message để không để sót buffer chưa release như thế nào?
Bạn thiết kế unit test kiểm tra vòng đời buffer và nhánh cancellation như thế nào?
Bạn phân biệt Netty ChannelOption với cấu hình Reactor Netty ở cấp client/server ra sao?
Bạn lựa chọn LoopResources để quản lý thread event loop theo đặc điểm tải như thế nào?
Bạn xác định cách chia sẻ hoặc cô lập LoopResources giữa nhiều client và server như thế nào?
Bạn đánh giá hệ quả của việc tạo quá nhiều event loop hoặc tùy chỉnh số worker không phù hợp ra sao?
Bạn quản lý vòng đời LoopResources khi ứng dụng khởi động lại các thành phần mạng như thế nào?
Bạn sử dụng ConnectionProvider để giải quyết những vấn đề gì về quản lý kết nối HTTP client?
Bạn cấu hình maxConnections và pendingAcquireMaxCount theo throughput và latency ra sao?
Bạn điều chỉnh pendingAcquireTimeout khi pool hết connection dựa trên ngân sách thời gian nào?
Bạn phân biệt connection acquire timeout với TCP connect timeout khi chẩn đoán lỗi như thế nào?
Bạn lựa chọn maxIdleTime và maxLifeTime của connection pool dựa trên chính sách upstream ra sao?
Bạn phát hiện connection stale do proxy đóng kết nối nhàn rỗi và xử lý như thế nào?
Bạn xác định khi nào nên bật background eviction cho các connection nhàn rỗi ra sao?
Bạn kiểm soát số pool riêng theo remote host để không vượt tài nguyên máy như thế nào?
Bạn phân tích cách HTTP/2 multiplexing ảnh hưởng tới nhu cầu số physical connections ra sao?
Bạn đánh giá tác động của một connection pool dùng chung khi nhiều dịch vụ upstream có chất lượng khác nhau như thế nào?
Bạn xử lý pending acquire queue tăng nhanh dù CPU ứng dụng vẫn thấp như thế nào?
Bạn phân tích ảnh hưởng của response body không được tiêu thụ hoặc giải phóng đúng cách tới tái sử dụng connection như thế nào?
Bạn xác định điểm đóng ConnectionProvider và các tài nguyên dùng chung khi shutdown như thế nào?
Bạn tính toán tổng số connection khi nhiều instance cùng cấu hình pool lớn như thế nào?
Bạn phân biệt connect timeout, response timeout và read timeout theo từng giai đoạn của request như thế nào?
Bạn cấu hình CONNECT_TIMEOUT_MILLIS và responseTimeout để bảo vệ hai loại thời gian chờ nào?
Bạn thêm ReadTimeoutHandler hoặc WriteTimeoutHandler trong trường hợp nào và cần chú ý gì về phạm vi handler?
Bạn xác định ngân sách end-to-end deadline khi một request qua nhiều upstream như thế nào?
Bạn phân tích tác động của timeout quá ngắn đến retry storm và tải backend ra sao?
Bạn xử lý trường hợp response streaming có khoảng im lặng dài nhưng connection vẫn hợp lệ như thế nào?
Bạn phân biệt idle timeout của TCP connection với deadline xử lý nghiệp vụ ra sao?
Bạn thiết kế cấu hình timeout riêng cho upload lớn và request JSON ngắn như thế nào?
Bạn quản lý giới hạn concurrent requests và connection pool để không đẩy latency vào hàng chờ vô hạn ra sao?
Bạn kết hợp graceful cancellation với timeout để giải phóng công việc backend như thế nào?
Bạn áp dụng TLS cho HttpServer hoặc TcpServer bằng cấu hình secure như thế nào?
Bạn quản lý certificate chain và private key trong Reactor Netty server theo môi trường ra sao?
Bạn cấu hình trust manager để client xác minh chứng chỉ server mà không tắt kiểm tra bảo mật như thế nào?
Bạn kiểm tra hostname verification của Reactor Netty client và phát hiện cấu hình thiếu an toàn ra sao?
Bạn lựa chọn giao thức TLS và cipher suite phù hợp với yêu cầu tương thích như thế nào?
Bạn phân tích chi phí TLS handshake khi mở và đóng nhiều connection liên tục ra sao?
Bạn đánh giá lợi ích và giới hạn của TLS session resumption khi client reconnect như thế nào?
Bạn thiết kế quy trình xoay vòng chứng chỉ khi server còn nhiều connection đang mở như thế nào?
Bạn cấu hình mTLS cho kết nối giữa dịch vụ và xác minh quyền từ client certificate ra sao?
Bạn quản lý secret hoặc khóa TLS để không xuất hiện trong wiretap và log debug như thế nào?
Bạn phân biệt lỗi SSL handshake với lỗi TCP connect và lỗi HTTP status như thế nào?
Bạn thiết kế thử nghiệm chứng chỉ hết hạn hoặc hostname mismatch mà không bỏ qua TLS verification ra sao?
Bạn đánh giá rủi ro của việc bật debug wiretap trên môi trường chứa dữ liệu nhạy cảm như thế nào?
Bạn chọn điểm thu thập metrics của server/client Reactor Netty để theo dõi số connection ra sao?
Bạn giám sát active connections, pending connections và số lần acquire timeout như thế nào?
Bạn thiết kế metric về DNS resolution, TCP connect, TLS handshake và HTTP response latency ra sao?
Bạn phân biệt độ trễ upstream xử lý với độ trễ do chờ pool và mạng bằng trace như thế nào?
Bạn sử dụng wiretap logging để chẩn đoán lỗi giao thức nhưng giới hạn nội dung nhạy cảm ra sao?
Bạn lựa chọn sampling và structured logging để tránh bùng nổ dung lượng khi traffic lớn như thế nào?
Bạn xây dựng distributed tracing cho HTTP outbound calls từ Reactor Netty như thế nào?
Bạn truyền trace context khi HTTP client gửi request tới dịch vụ khác như thế nào?
Bạn quản lý metrics tags theo URI template để tránh cardinality cao từ path ID như thế nào?
Bạn phát hiện lỗi đột ngột tăng sau khi thay timeout hoặc connection pool bằng metric nào?
Bạn dùng heap, direct memory, GC và event-loop utilization để phân tích memory pressure như thế nào?
Bạn sử dụng những dấu hiệu nào để xác định blocked event loop là nguyên nhân khiến độ trễ p99 tăng cao?
Bạn phát hiện sự cố DNS hoặc proxy từ log và metrics của Reactor Netty HttpClient như thế nào?
Bạn thiết kế dashboard để so sánh throughput, p95, p99 và error rate của server ra sao?
Bạn lập runbook khi pending acquire tăng, connection mở tối đa và request timeouts dồn dập như thế nào?
Bạn tích hợp Reactor Netty HttpClient với Spring WebClient qua ReactorClientHttpConnector như thế nào?
Bạn cấu hình WebClient dùng chung với ConnectionProvider tùy chỉnh trong ứng dụng Spring như thế nào?
Bạn tách HttpClient config cho từng upstream service khi dùng nhiều WebClient như thế nào?
Bạn đánh giá vai trò của Reactor Netty khi Spring WebFlux chạy trên embedded Netty server ra sao?
Bạn kiểm tra tác động của việc gọi block trong controller WebFlux sử dụng Reactor Netty như thế nào?
Bạn áp dụng cấu hình Netty server trong Spring Boot mà vẫn giữ quyền kiểm soát vòng đời tài nguyên ra sao?
Bạn truyền Reactor Context và trace IDs qua WebClient filter và Reactor Netty như thế nào?
Bạn thiết kế response timeout trong WebClient và HttpClient để không chồng chéo khó đoán ra sao?
Bạn kiểm thử một HttpClient Reactor Netty bằng HTTP server giả lập thay vì mock trực tiếp Mono như thế nào?
Bạn sử dụng StepVerifier để kiểm tra chuỗi response, lỗi và cancellation trong client như thế nào?
Bạn dùng virtual time để kiểm thử retry/backoff trong pipeline không phụ thuộc thời gian thực như thế nào?
Bạn tạo integration test TCP server/client để kiểm tra framing khi gói dữ liệu bị tách ra sao?
Bạn mô phỏng UDP loss, duplicate hoặc reorder để xác minh logic ứng dụng như thế nào?
Bạn kiểm thử server đang streaming mà client hủy request để phát hiện rò rỉ tài nguyên ra sao?
Bạn xây dựng load test với kích thước payload và số connection tăng dần như thế nào?
Bạn phân biệt throughput benchmark và latency benchmark khi đo hiệu năng Reactor Netty ra sao?
Bạn dùng profile CPU và thread dump để tìm tác vụ blocking trên event loop như thế nào?
Bạn đo thời gian phản hồi khi pool đạt maxConnections và hàng đợi pending tăng ra sao?
Bạn kiểm thử ảnh hưởng của cấu hình HTTP keep-alive và TLS đến chi phí thiết lập connection như thế nào?
Bạn mô phỏng upstream đóng idle connection để đánh giá độ bền của pooling như thế nào?
Bạn thiết kế fault injection tạo connection reset, slow response và handshake failure để kiểm chứng resilience ra sao?
Bạn xác định tiêu chí pass/fail về bộ nhớ, latency, thông lượng và tỉ lệ lỗi cho service Reactor Netty như thế nào?
Nếu một endpoint HTTP bị chậm dù CPU thấp, bạn sẽ kiểm tra event loop, pool và thời gian upstream theo thứ tự nào?
Nếu WebClient đôi khi báo PrematureCloseException, bạn sẽ kiểm tra những tình huống đóng connection nào?
Nếu một request JSON nhanh nhưng request streaming thường hết timeout, bạn sẽ điều chỉnh các giới hạn thời gian như thế nào?
Nếu tăng maxConnections làm throughput không tăng mà p99 xấu đi, bạn sẽ tìm bottleneck ở đâu?
Nếu một handler gọi JDBC và làm nhiều connection đứng chờ, bạn sẽ đổi cách thực thi trên scheduler như thế nào?
Nếu direct memory tăng liên tục sau khi client hủy upload, bạn sẽ điều tra vòng đời ByteBuf ra sao?
Nếu một HTTP client nhận response thành công nhưng còn connection không được trả về pool, bạn sẽ kiểm tra phần tiêu thụ body nào?
Nếu toàn bộ client cùng retry sau upstream restart, bạn sẽ điều chỉnh jitter, pool và concurrency ra sao?
Nếu một TCP server đọc được nửa thông điệp rồi giải mã sai, bạn sẽ kiểm tra framing ở tầng nào?
Nếu UDP telemetry báo thiếu bản tin trong giờ cao điểm, bạn sẽ so sánh packet loss, buffer và CPU như thế nào?
Nếu TLS hoạt động trên máy local nhưng thất bại trong production, bạn sẽ phân biệt truststore, hostname và proxy ra sao?
Nếu proxy đóng kết nối HTTP idle nhưng pool vẫn tái dùng, bạn sẽ xác định nguyên nhân và chỉnh cấu hình nào?
Nếu một thay đổi cấu hình khiến tạo quá nhiều event-loop threads, bạn sẽ đo ảnh hưởng và khôi phục như thế nào?
Nếu bật wiretap giúp tìm lỗi nhưng làm lộ token trong log, bạn sẽ xử lý và thay cách quan sát ra sao?
Nếu service WebFlux hoạt động bình thường nhưng một upstream cạn connection, bạn sẽ ngăn sự cố lan sang upstream khác bằng cách nào?
Nếu dữ liệu TCP bị gửi lặp sau retry dù phía nhận đã xử lý, bạn sẽ bổ sung cơ chế nào ở tầng ứng dụng?
Nếu client muốn ngắt download giữa chừng nhưng worker backend vẫn làm việc, bạn sẽ kiểm tra propagation của cancellation ra sao?
Nếu kết nối UDP multicast không nhận dữ liệu dù server gửi thành công, bạn sẽ kiểm tra group membership và mạng như thế nào?
Bạn thiết kế kế hoạch khôi phục Reactor Netty service sau sự cố tổng hợp gồm DNS, pool exhaustion và blocking event loop ra sao?
