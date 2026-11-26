Trong những bài toán nào bạn sẽ chọn RSocket để tích hợp các dịch vụ thay vì HTTP request-response truyền thống?
Bạn so sánh RSocket với WebSocket thuần về mô hình tương tác và quản lý luồng dữ liệu như thế nào?
Bạn đánh giá RSocket và gRPC streaming theo yêu cầu realtime, hai chiều và khả năng tương thích ra sao?
Bạn giải thích vai trò của giao thức RSocket trong kiến trúc ứng dụng reactive như thế nào?
Bạn phân biệt đặc điểm của RSocket với một thư viện lập trình reactive chạy trên HTTP ra sao?
Bạn xác định tiêu chí chọn RSocket cho giao tiếp nội bộ thay vì API công khai như thế nào?
Bạn phân tích những đánh đổi khi giữ một kết nối lâu dài để trao đổi nhiều request như thế nào?
Bạn mô tả vai trò của requester và responder khi một kết nối RSocket hỗ trợ giao tiếp hai chiều ra sao?
Vì sao một bên có thể đồng thời đóng vai trò requester và responder trong RSocket?
Bạn thiết kế ranh giới trách nhiệm giữa transport, protocol và logic nghiệp vụ khi dùng RSocket ra sao?
Bạn đánh giá yêu cầu của client mobile có mạng không ổn định trước khi chọn RSocket như thế nào?
Bạn xác định những trường hợp nên tiếp tục dùng HTTP hoặc message broker thay cho RSocket như thế nào?
Bạn phân biệt request-response, fire-and-forget, request-stream và request-channel bằng các bài toán nghiệp vụ nào?
Bạn thiết kế một interaction request-response để truy vấn trạng thái tài nguyên như thế nào?
Bạn lựa chọn fire-and-forget cho loại sự kiện nào và chấp nhận những giới hạn về xác nhận nào?
Vì sao fire-and-forget không tự chứng minh tác vụ nghiệp vụ đã thực hiện thành công?
Bạn dùng request-stream để cung cấp bản cập nhật liên tục cho client ra sao?
Bạn thiết kế request-stream có dữ liệu khởi tạo và các bản cập nhật tiếp theo như thế nào?
Bạn sử dụng request-channel khi cả client và server cần gửi nhiều phần tử liên tiếp ra sao?
Bạn phân biệt request-channel với hai request-stream độc lập khi thiết kế giao tiếp hai chiều như thế nào?
Bạn quyết định đặt thao tác nào trên từng interaction model để hợp đồng dễ hiểu ra sao?
Bạn đánh giá tác động của request-stream không giới hạn thời gian đối với kết nối và bộ nhớ như thế nào?
Bạn thiết kế cách báo kết thúc stream hợp lệ để client nhận biết đã hết dữ liệu ra sao?
Bạn xử lý trường hợp một request-response trả về kết quả rỗng theo hợp đồng như thế nào?
Bạn phân biệt tín hiệu hoàn tất và tín hiệu lỗi trong luồng phản hồi RSocket ra sao?
Bạn mô tả thứ tự thiết lập kết nối và gửi SETUP frame của một phiên RSocket như thế nào?
Bạn giải thích vai trò của stream ID khi nhiều luồng cùng chia sẻ một kết nối ra sao?
Bạn xử lý các frame thuộc nhiều stream đang đan xen trên cùng kết nối như thế nào?
Bạn phân biệt frame REQUEST_RESPONSE và REQUEST_STREAM qua vòng đời yêu cầu như thế nào?
Bạn giải thích frame REQUEST_FNF ảnh hưởng tới kỳ vọng phản hồi của phía gửi ra sao?
Bạn phân tích cách REQUEST_CHANNEL khởi tạo tương tác giữa hai luồng dữ liệu như thế nào?
Bạn sử dụng PAYLOAD frame để phân biệt dữ liệu, metadata và tín hiệu hoàn tất ra sao?
Bạn giải thích vai trò của REQUEST_N trong điều tiết số payload có thể gửi như thế nào?
Bạn xử lý frame CANCEL khi phía nhận không còn muốn nhận dữ liệu từ một stream ra sao?
Bạn thiết kế cách phản hồi ERROR frame cho lỗi ứng dụng và lỗi giao thức như thế nào?
Bạn giải thích sự khác nhau giữa lỗi trên một stream và lỗi làm đóng toàn bộ connection ra sao?
Bạn dùng KEEPALIVE frame để phát hiện kết nối không còn hoạt động như thế nào?
Bạn phân tích cơ chế LEASE của RSocket để giới hạn yêu cầu mới theo ngân sách cho phép ra sao?
Bạn dựa trên những yêu cầu và giới hạn thư viện nào để quyết định hỗ trợ cơ chế resume?
Bạn phân biệt RESUME với thao tác kết nối mới và đăng ký lại stream như thế nào?
Vì sao hỗ trợ resume không đồng nghĩa với bảo đảm exactly-once ở tầng nghiệp vụ?
Bạn xử lý sự khác nhau giữa fragmentation của frame RSocket và phân đoạn gói mạng ra sao?
Bạn xác định giới hạn kích thước frame và payload để tránh quá tải bộ nhớ như thế nào?
Bạn mô tả cách metadata push có thể truyền thông tin ở cấp kết nối trong trường hợp hỗ trợ ra sao?
Bạn xây dựng chính sách xử lý các frame không hợp lệ hoặc frame xuất hiện sai trạng thái giao thức như thế nào?
Bạn đánh giá tác động của nhiều stream đồng thời lên một TCP connection như thế nào?
Bạn thiết kế giao thức ứng dụng để không phụ thuộc vào thứ tự hoàn tất của các stream độc lập ra sao?
Bạn xác định trách nhiệm bảo đảm thứ tự phần tử trong một stream khi có xử lý bất đồng bộ như thế nào?
Bạn kiểm tra tính tương thích phiên bản giao thức giữa requester và responder như thế nào?
Bạn lựa chọn transport TCP hay WebSocket cho RSocket dựa trên môi trường triển khai nào?
Bạn giải thích khác biệt giữa RSocket-over-TCP và RSocket-over-WebSocket về đường truyền như thế nào?
Bạn quyết định dùng WebSocket khi client chạy trong trình duyệt dựa trên giới hạn nền tảng nào?
Bạn cấu hình địa chỉ và cổng TCP của RSocket server để phù hợp mạng nội bộ như thế nào?
Bạn thiết kế đường dẫn WebSocket cho RSocket khi ứng dụng cũng phục vụ HTTP API ra sao?
Bạn xử lý vấn đề proxy hoặc load balancer ngắt kết nối nhàn rỗi của RSocket như thế nào?
Bạn phân biệt WebSocket ping/pong với KEEPALIVE ở tầng RSocket trong giám sát kết nối như thế nào?
Bạn đánh giá chi phí handshake và thiết lập lại kết nối khi client liên tục ngắt mạng ra sao?
Bạn lựa chọn chiến lược connection pooling hay chia kết nối theo mục đích sử dụng như thế nào?
Bạn phân tích rủi ro một kết nối bị nghẽn ảnh hưởng nhiều stream đang chạy ra sao?
Bạn phân biệt tắc nghẽn TCP với backpressure ở tầng Reactive Streams như thế nào?
Bạn thiết kế timeout thiết lập kết nối và timeout nghiệp vụ cho các interaction model ra sao?
Bạn xử lý việc thay đổi địa chỉ DNS của RSocket server khi client đang giữ kết nối lâu dài như thế nào?
Bạn xác định quy tắc TLS cho RSocket chạy trực tiếp trên TCP như thế nào?
Bạn đánh giá phương án TLS termination khi RSocket được vận chuyển qua WebSocket như thế nào?
Bạn xác minh hostname và chuỗi chứng chỉ khi client kết nối tới RSocket server ra sao?
Bạn lựa chọn mTLS cho giao tiếp giữa các dịch vụ trong những tình huống nào?
Bạn thiết kế quy trình thay chứng chỉ TLS khi hàng nghìn kết nối RSocket đang mở như thế nào?
Bạn xử lý hành vi reconnect sau khi chứng chỉ server hoặc client được làm mới như thế nào?
Bạn phân biệt lỗi kết nối, lỗi protocol setup và lỗi route ứng dụng để chẩn đoán nhanh ra sao?
Bạn giới hạn số kết nối mở đồng thời để tránh server bị cạn file descriptor như thế nào?
Bạn thiết kế cơ chế phát hiện kết nối bị treo khi thiết bị di chuyển giữa các mạng như thế nào?
Bạn lựa chọn cách đóng kết nối có kiểm soát khi server chuẩn bị shutdown như thế nào?
Bạn xác định những dữ liệu nào phải đi kèm mỗi request khi kết nối được tái sử dụng lâu dài ra sao?
Bạn giải thích vai trò của data MIME type và metadata MIME type trong SETUP như thế nào?
Bạn lựa chọn định dạng payload JSON hay nhị phân theo nhu cầu throughput và tương thích nào?
Bạn tổ chức schema cho dữ liệu request và response để client/server nâng cấp độc lập ra sao?
Bạn biểu diễn lỗi nghiệp vụ bằng payload hay tín hiệu lỗi của stream theo tiêu chí nào?
Bạn xác định quy tắc bắt buộc và tùy chọn của trường trong dữ liệu reactive như thế nào?
Bạn phân biệt metadata phục vụ định tuyến với data phục vụ nghiệp vụ như thế nào?
Vì sao composite metadata hữu ích khi cùng một request cần mang nhiều loại metadata?
Bạn thiết kế metadata cho route, authentication và tracing trong một tương tác như thế nào?
Bạn xử lý MIME type hoặc metadata entry chưa được server hỗ trợ như thế nào?
Bạn lựa chọn tiêu chuẩn route naming để tránh xung đột giữa các miền nghiệp vụ ra sao?
Bạn quản lý phiên bản route và payload khi client và server triển khai lệch nhau như thế nào?
Bạn truyền correlation ID và trace context xuyên qua nhiều lời gọi RSocket ra sao?
Bạn phân chia thông tin giữa metadata của từng request và metadata cấp kết nối dựa trên tiêu chí nào?
Bạn thiết kế một route có dữ liệu subscription filter được truyền cùng request như thế nào?
Bạn hạn chế kích thước metadata để tránh việc client gửi quá nhiều thông tin như thế nào?
Bạn bảo vệ các trường metadata nhạy cảm khỏi bị ghi ra log như thế nào?
Bạn kiểm tra quyền truy cập cho từng route khi nhiều yêu cầu chia sẻ một connection ra sao?
Bạn phân biệt xác thực lúc mở kết nối với xác thực cho từng tương tác RSocket như thế nào?
Bạn lựa chọn bearer token trong composite metadata dựa trên yêu cầu triển khai nào?
Bạn xử lý access token hết hạn trong khi connection RSocket vẫn còn mở như thế nào?
Bạn thiết kế cơ chế cập nhật thông tin xác thực mà không tạo lỗ hổng giữa các stream ra sao?
Bạn bảo đảm quyền của người dùng được kiểm tra lại khi subscription kéo dài nhiều giờ như thế nào?
Bạn phân vùng dữ liệu realtime theo tenant để không gửi nhầm sự kiện qua stream khác như thế nào?
Bạn giới hạn route nhạy cảm chỉ cho các service account có quyền phù hợp ra sao?
Bạn ngăn metadata do client tự khai báo giả mạo quyền hoặc định danh người dùng như thế nào?
Bạn áp dụng kiểm soát kích thước payload và schema validation để giảm nguy cơ lạm dụng như thế nào?
Bạn lựa chọn rate limiting theo connection, route và người dùng dựa trên tiêu chí nào?
Bạn giới hạn số stream đang hoạt động trên mỗi connection để bảo vệ tài nguyên như thế nào?
Bạn phân tích nguy cơ tấn công từ một stream tạo quá nhiều yêu cầu mà không đọc response ra sao?
Bạn thiết kế chính sách chống lạm dụng request-channel khi client gửi dữ liệu liên tục như thế nào?
Bạn kiểm soát quyền sử dụng transport WebSocket trong môi trường trình duyệt như thế nào?
Bạn thiết kế logging và kiểm toán truy cập route mà không để lộ token xác thực ra sao?
Bạn giải thích vai trò của Reactive Streams và tín hiệu subscribe, request, next, error, complete trong RSocket như thế nào?
Bạn phân biệt Mono và Flux khi biểu diễn kết quả của các interaction model ra sao?
Bạn giải thích cách demand của subscriber tác động đến lượng dữ liệu publisher được phép phát như thế nào?
Bạn phân biệt backpressure với rate limiting trong một hệ thống RSocket realtime như thế nào?
Bạn lựa chọn mức request-N ban đầu và số lượng bổ sung theo đặc điểm consumer như thế nào?
Bạn kiểm tra việc thực thi không phát thêm phần tử khi subscriber chưa yêu cầu như thế nào?
Bạn thiết kế luồng request-stream để producer chậm lại khi client xử lý chậm ra sao?
Bạn xử lý tình huống publisher không thể giảm tốc độ tạo sự kiện theo downstream demand như thế nào?
Bạn quyết định khi nào buffer, drop hoặc giữ trạng thái cuối cùng để điều tiết một luồng realtime ra sao?
Bạn đánh giá nguy cơ dùng buffer không giới hạn khi client mất khả năng tiêu thụ như thế nào?
Bạn sử dụng Flux.onBackpressureBuffer với giới hạn và chính sách tràn bộ đệm như thế nào?
Bạn lựa chọn onBackpressureLatest hay onBackpressureDrop cho loại dữ liệu nghiệp vụ nào?
Bạn xác định trách nhiệm phản hồi CANCEL để dừng công việc backend không còn cần thiết ra sao?
Bạn kiểm soát backpressure ở cả hai chiều của request-channel như thế nào?
Bạn phân biệt concurrency của flatMap với demand ở tầng RSocket như thế nào?
Bạn tránh dùng block trên Netty event loop khi RSocket server xử lý một request ra sao?
Bạn tích hợp lời gọi database blocking vào luồng reactive mà không làm nghẽn event loop như thế nào?
Bạn đánh giá hiệu quả sử dụng boundedElastic và scheduler chuyên biệt cho tác vụ chặn ra sao?
Bạn xử lý đồng thời nhiều dữ liệu từ stream nhưng vẫn giữ ordering cần thiết như thế nào?
Bạn lựa chọn concatMap, flatMapSequential và flatMap theo yêu cầu thứ tự ra sao?
Bạn truyền Reactor Context qua các operator bất đồng bộ để giữ tracing như thế nào?
Bạn xử lý cancellation trong một chuỗi Flux có đang gọi tài nguyên bên ngoài như thế nào?
Bạn giải phóng tài nguyên khi một Flux kết thúc bằng lỗi, hoàn tất hoặc bị hủy ra sao?
Bạn ngăn memory leak từ DataBuffer hoặc ByteBuf khi làm việc với payload thấp tầng như thế nào?
Bạn kiểm tra giới hạn nhu cầu và bộ nhớ của nhiều subscriber đồng thời trên server như thế nào?
Bạn thiết kế cơ chế fan-out một nguồn sự kiện cho nhiều stream với tốc độ tiêu thụ khác nhau ra sao?
Bạn phân biệt cold Flux và hot Flux khi dùng nguồn dữ liệu realtime chung như thế nào?
Bạn chọn multicast sink và chính sách phát sự kiện khi không có subscriber như thế nào?
Bạn xử lý slow subscriber trên nguồn dữ liệu hot mà không ảnh hưởng tất cả người nhận như thế nào?
Bạn phân tích tác dụng phụ nếu cùng một publisher lạnh bị subscribe nhiều lần như thế nào?
Bạn lựa chọn chia sẻ hay tạo mới nguồn phát sự kiện cho từng request-stream theo tiêu chí nào?
Bạn xây dựng server RSocket thuần Java bằng các thành phần reactor-netty và rsocket-java như thế nào?
Bạn cấu hình RSocketServer để lắng nghe kết nối TCP theo nhu cầu của ứng dụng ra sao?
Bạn sử dụng RSocketConnector để tạo một client kết nối tới server như thế nào?
Bạn triển khai requestResponse trong RSocket interface để phản hồi một payload như thế nào?
Bạn triển khai requestStream để phát chuỗi dữ liệu được điều tiết theo demand ra sao?
Bạn tổ chức fireAndForget để nhận lệnh mà không tạo kỳ vọng phản hồi nghiệp vụ như thế nào?
Bạn xây dựng requestChannel để đọc và ghi các Flux payload độc lập nhưng có cùng phiên tương tác ra sao?
Bạn quản lý vòng đời Payload và việc giải phóng buffer trong rsocket-java như thế nào?
Bạn lựa chọn DefaultPayload hoặc payload tạo từ ByteBuf theo tiêu chí sử dụng bộ nhớ nào?
Bạn thiết kế serialization và deserialization ở tầng Java để không phụ thuộc chi tiết protocol ra sao?
Bạn xử lý errors từ RSocket request-response bằng Reactor operator như thế nào?
Bạn phân biệt lỗi trong stream đang chạy với lỗi đóng kết nối trong Java client ra sao?
Bạn quản lý Disposable hoặc tín hiệu onClose của kết nối RSocket khi ứng dụng shutdown như thế nào?
Bạn xây dựng reconnect strategy cho RSocketConnector khi kết nối đầu tiên không thành công ra sao?
Bạn chọn cấp độ retry một interaction và reconnect cả connection dựa trên lỗi nào?
Bạn thiết kế cách chia sẻ một RSocket connection cho nhiều request đồng thời an toàn như thế nào?
Bạn kiểm soát việc tạo lại connection trong Java khi nhiều luồng cùng phát hiện lỗi ra sao?
Bạn kiểm thử tầng Java RSocket bằng một responder giả lập để xác minh lỗi và cancellation như thế nào?
Bạn cấu hình RSocket server trong Spring Boot cho TCP hoặc WebSocket như thế nào?
Bạn sử dụng RSocketRequester.Builder để thiết lập data MIME type, metadata MIME type và transport ra sao?
Bạn xây dựng RSocketRequester cho kết nối TCP và sử dụng route trong Spring như thế nào?
Bạn kết nối RSocketRequester qua WebSocket trong môi trường Spring theo cách nào?
Bạn sử dụng @MessageMapping để ánh xạ route của RSocket tới phương thức xử lý như thế nào?
Bạn xác định kiểu Mono, Flux hoặc void phù hợp cho kết quả của @MessageMapping ra sao?
Bạn dùng @Payload để nhận body và @Header để lấy metadata trong Spring Messaging như thế nào?
Bạn truyền các thông tin request vào controller từ RSocket metadata như thế nào?
Bạn triển khai route request-response và kiểm tra dữ liệu đầu vào trong Spring như thế nào?
Bạn thiết kế route request-stream trả về Flux cập nhật trạng thái theo thời gian thực ra sao?
Bạn triển khai route request-channel nhận Flux đầu vào và trả Flux đầu ra trong Spring như thế nào?
Bạn ánh xạ một thao tác fire-and-forget tới xử lý bất đồng bộ mà vẫn ghi nhận lỗi hệ thống ra sao?
Bạn sử dụng RSocketStrategies để cấu hình encoder, decoder và metadata extractor như thế nào?
Bạn tổ chức composite metadata trong Spring để chứa routing và authentication đồng thời ra sao?
Bạn đưa route handler xuống service layer để giảm phụ thuộc giữa nghiệp vụ và Spring Messaging như thế nào?
Bạn tích hợp Spring Security RSocket để kiểm tra quyền theo route như thế nào?
Bạn tổ chức SecuritySocketAcceptorInterceptor hoặc cấu hình tương đương để chặn tương tác không hợp lệ ra sao?
Bạn truyền bearer token qua metadata trong RSocketRequester dựa trên hợp đồng bảo mật nào?
Bạn kiểm tra dữ liệu tenant và quyền của principal trong một route stream như thế nào?
Bạn xử lý exception từ @MessageMapping để client nhận lỗi có thể hiểu được ra sao?
Bạn cấu hình timeout và retry cho từng lời gọi RSocketRequester theo yêu cầu nghiệp vụ như thế nào?
Bạn thiết kế cách khởi tạo và tái sử dụng RSocketRequester trong vòng đời Spring application ra sao?
Bạn tổ chức shutdown của Spring RSocket server để dừng nhận request và giải phóng stream như thế nào?
Bạn tách cấu hình RSocket TCP/WebSocket theo các profile local, staging và production ra sao?
Bạn kết hợp một HTTP API với RSocket stream khi client cần dữ liệu khởi tạo và cập nhật liên tục như thế nào?
Bạn xây dựng một notification service dùng RSocket request-stream trong Spring như thế nào?
Bạn thiết kế ứng dụng chat realtime bằng request-channel và quản lý người tham gia ra sao?
Bạn xử lý một luồng cập nhật cảm biến khi client có tốc độ tiêu thụ khác nhau như thế nào?
Bạn lựa chọn trạng thái kết nối và cơ chế phát lại khi màn hình người dùng tạm chuyển sang nền như thế nào?
Bạn phân tích rủi ro bỏ lỡ sự kiện trong thời gian client mất kết nối như thế nào?
Bạn phân biệt reconnect, resubscribe, resume và replay sự kiện trong chiến lược phục hồi ra sao?
Bạn xác định điều kiện cần hỗ trợ resume ở cả requester và responder như thế nào?
Bạn đánh giá phạm vi dữ liệu có thể khôi phục nếu resume buffer bị giới hạn như thế nào?
Bạn xử lý trường hợp resume thất bại và cần tạo stream mới theo trình tự nào?
Bạn sử dụng cursor hoặc sequence number nghiệp vụ để lấy bù sự kiện sau khi reconnect ra sao?
Bạn thiết kế idempotent handler để xử lý phần tử có thể được gửi lại sau lỗi mạng như thế nào?
Bạn phân biệt exactly-once transport delivery với exactly-once side effect ở tầng nghiệp vụ như thế nào?
Bạn lựa chọn backoff và jitter cho nhiều client reconnect cùng lúc sau sự cố server ra sao?
Bạn ngăn nhiều luồng ứng dụng tạo kết nối mới đồng thời khi kết nối dùng chung bị đóng ra sao?
Bạn quyết định dừng reconnect và thông báo lỗi cho người dùng dựa trên những điều kiện nào?
Bạn quản lý kết nối lâu dài khi token của người dùng đã bị thu hồi hoặc hết hạn ra sao?
Bạn xử lý server restart khi còn nhiều request-stream đang chạy dở như thế nào?
Bạn thiết kế graceful reconnect khi server được triển khai rolling update như thế nào?
Bạn xác định các trường hợp phải bỏ dữ liệu cũ rồi tải snapshot mới sau khi reconnect như thế nào?
Bạn thiết kế heartbeat và ngưỡng phát hiện mất kết nối để cân bằng độ nhạy với tải mạng ra sao?
Bạn giải thích ảnh hưởng của lease budget tới số request mới khi backend đang quá tải như thế nào?
Bạn phối hợp lease, admission control và giới hạn số stream để bảo vệ server như thế nào?
Bạn phân biệt retry có thể gây tác dụng phụ trùng với cách phát lại idempotent như thế nào?
Bạn thiết kế timeout cho request-response mà không áp cùng giới hạn vào stream dài hạn như thế nào?
Bạn xử lý stream có demand nhưng backend không phát dữ liệu trong thời gian dài như thế nào?
Bạn thiết kế chính sách xử lý lỗi có thể phục hồi ở một stream mà không đóng các stream khác ra sao?
Bạn ánh xạ các tình huống unavailable, rejected, invalid và application error tới hành động client như thế nào?
Bạn xác định giới hạn tài nguyên cho mỗi connection, mỗi stream và mỗi tenant dựa trên số liệu nào?
Bạn triển khai bulkhead để một nhóm route tải nặng không chiếm hết scheduler và thread ra sao?
Bạn quản lý connection và stream khi ứng dụng thực hiện nhiều lời gọi RSocket lồng nhau như thế nào?
Bạn xây dựng metrics nào để quan sát active connections, active streams và tốc độ frame?
Bạn theo dõi request-response latency và thời gian chờ kết quả đầu tiên của request-stream như thế nào?
Bạn đo tốc độ phát, tốc độ tiêu thụ và pending demand để phát hiện bottleneck ra sao?
Bạn thiết kế cảnh báo khi tỷ lệ CANCEL hoặc ERROR frame tăng bất thường như thế nào?
Bạn phân biệt lỗi application route với lỗi transport và protocol trong log như thế nào?
Bạn quan sát thời gian reconnect, số lần reconnect và tỷ lệ phục hồi thành công như thế nào?
Bạn thiết kế distributed tracing từ RSocket requester đến responder và downstream services ra sao?
Bạn quản lý cardinality của metrics khi hệ thống có nhiều route, stream ID và tenant như thế nào?
Bạn che giấu dữ liệu nhạy cảm trong logging payload và composite metadata như thế nào?
Bạn lập dashboard về heap, direct memory và các buffer đang giữ bởi stream như thế nào?
Bạn nhận diện một stream giữ bộ nhớ tăng liên tục dù subscriber đã giảm tốc độ nhận như thế nào?
Bạn thiết kế bài kiểm thử tải cho nhiều stream đồng thời trên một connection ra sao?
Bạn sử dụng StepVerifier để kiểm tra request-response hoàn tất đúng giá trị như thế nào?
Bạn viết StepVerifier test cho Flux request-stream có demand và cancellation như thế nào?
Bạn dùng virtual time để kiểm thử timeout, backoff và retry mà không chờ thời gian thực như thế nào?
Bạn kiểm thử request-channel với hai luồng dữ liệu có tốc độ độc lập như thế nào?
Bạn tổ chức integration test Spring @MessageMapping bằng RSocketRequester thực như thế nào?
Bạn kiểm thử routing và composite metadata trên kết nối TCP hoặc WebSocket ra sao?
Bạn mô phỏng payload malformed và xác minh lỗi không làm ảnh hưởng các stream khác như thế nào?
Bạn kiểm thử token thiếu, token hết hạn và truy cập route vượt quyền như thế nào?
Bạn kiểm thử TLS handshake failure và hostname mismatch mà không tắt kiểm tra chứng chỉ như thế nào?
Bạn tạo tình huống client CANCEL giữa một stream để xác minh giải phóng tài nguyên ra sao?
Bạn mô phỏng client đọc chậm để xác minh server tuân thủ backpressure như thế nào?
Bạn kiểm tra ảnh hưởng của buffer giới hạn khi producer phát nhanh hơn consumer như thế nào?
Bạn kiểm thử ngắt kết nối đột ngột khi request-channel còn dữ liệu ở cả hai chiều ra sao?
Bạn mô phỏng reconnect sau server restart để xác minh ứng dụng đăng ký lại stream như thế nào?
Bạn kiểm chứng resume hoặc replay trong phạm vi hỗ trợ của ứng dụng mà không giả định không mất dữ liệu ra sao?
Bạn đo throughput, p95 và p99 latency của RSocket dưới nhiều mức concurrency như thế nào?
Bạn so sánh benchmark TCP và WebSocket trong cùng điều kiện mạng và kích thước payload như thế nào?
Bạn kiểm thử trường hợp proxy đóng kết nối nhàn rỗi để xác minh keepalive và reconnect ra sao?
Bạn sử dụng fault injection với latency, packet loss và connection reset để kiểm tra phục hồi như thế nào?
Bạn viết contract test cho schema payload và metadata giữa nhiều phiên bản client/server như thế nào?
Bạn xác định tiêu chí pass/fail của bài kiểm thử realtime về độ trễ, mất sự kiện và sử dụng tài nguyên như thế nào?
Nếu một client request-stream nhận dữ liệu chậm dần rồi hết bộ nhớ, bạn sẽ kiểm tra backpressure và buffering ở đâu?
Nếu server vẫn hoạt động nhưng client không nhận thêm PAYLOAD frame, bạn sẽ kiểm tra pending demand và REQUEST_N như thế nào?
Nếu request-response báo timeout nhưng backend đã xử lý thành công, bạn sẽ thiết kế retry an toàn ra sao?
Nếu một connection TCP bị đóng giữa request-channel, bạn sẽ xác định những phần dữ liệu có thể đã xử lý như thế nào?
Nếu proxy hỗ trợ WebSocket nhưng liên tục đóng phiên sau một phút, bạn sẽ kiểm tra keepalive và cấu hình nào?
Nếu một route Spring @MessageMapping không được gọi dù kết nối thành công, bạn sẽ truy vết routing metadata ra sao?
Nếu token hết hạn trong khi stream đang chạy, bạn sẽ bảo vệ quyền truy cập và khôi phục trải nghiệm client như thế nào?
Nếu nhiều client reconnect đồng loạt sau khi deploy, bạn sẽ điều chỉnh backoff và giới hạn tiếp nhận ra sao?
Nếu server dùng buffer không giới hạn để phát sự kiện, bạn sẽ giảm rủi ro mà vẫn giữ dữ liệu quan trọng như thế nào?
Nếu một client gửi REQUEST_N rất lớn rồi hủy stream sớm, bạn sẽ kiểm tra tài nguyên nào chưa được giải phóng?
Nếu request-channel bị sai thứ tự kết quả do xử lý flatMap song song, bạn sẽ sửa toán tử hoặc hợp đồng như thế nào?
Nếu client cần lấy bù dữ liệu sau mất mạng nhưng server không hỗ trợ resume, bạn sẽ thiết kế cursor và snapshot ra sao?
Nếu một thay đổi schema khiến client cũ không decode được payload, bạn sẽ triển khai tương thích và rollback như thế nào?
Nếu direct memory của RSocket server tăng sau mỗi lần CANCEL, bạn sẽ điều tra vòng đời payload như thế nào?
Nếu lưu lượng tăng khiến một số route chậm trong khi route khác ổn định, bạn sẽ phân tích scheduler và giới hạn tài nguyên ra sao?
Nếu một bên lỗi protocol làm connection đóng, bạn sẽ xác định và khôi phục các interaction còn dang dở như thế nào?
Nếu hệ thống cần nâng cấp từ kết nối WebSocket sang TCP giữa các service, bạn sẽ đánh giá và kiểm thử các ràng buộc nào?
Bạn xây dựng runbook xử lý tình huống RSocket server mất kết nối hàng loạt nhưng nhu cầu realtime vẫn tăng như thế nào?
