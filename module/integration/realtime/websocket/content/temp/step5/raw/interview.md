Bạn giải thích WebSocket giải quyết nhu cầu giao tiếp thời gian thực nào mà HTTP request-response thông thường khó đáp ứng hiệu quả?
Bạn so sánh WebSocket, HTTP polling, long polling và Server-Sent Events theo hướng truyền dữ liệu và chi phí kết nối như thế nào?
Bạn sẽ chọn WebSocket hay Server-Sent Events cho ứng dụng chỉ cần máy chủ đẩy thông báo đến trình duyệt dựa trên những tiêu chí nào?
Bạn mô tả vòng đời một kết nối WebSocket từ lúc khởi tạo đến khi đóng hoàn toàn như thế nào?
Bạn giải thích quan hệ giữa HTTP và WebSocket trong quá trình thiết lập kết nối ban đầu ra sao?
Bạn mô tả một HTTP/1.1 WebSocket opening handshake hợp lệ gồm những header quan trọng nào?
Bạn giải thích ý nghĩa của Upgrade, Connection, Sec-WebSocket-Key và Sec-WebSocket-Accept trong handshake như thế nào?
Bạn sẽ kiểm tra phản hồi HTTP 101 Switching Protocols để xác định máy chủ chấp nhận nâng cấp kết nối ra sao?
Bạn phân biệt địa chỉ ws và wss với http và https về kết nối và bảo mật truyền tải như thế nào?
Bạn xử lý trường hợp proxy hoặc load balancer chặn header Upgrade khiến WebSocket handshake thất bại ra sao?
Bạn phân biệt handshake thất bại ở tầng HTTP với kết nối WebSocket đã thiết lập rồi bị đóng như thế nào?
Bạn giải thích vai trò của Sec-WebSocket-Protocol khi client và server cần thống nhất một subprotocol ra sao?
Bạn lựa chọn subprotocol ứng dụng và xử lý trường hợp hai bên không hỗ trợ giao thức chung như thế nào?
Bạn giải thích WebSocket extension được thương lượng trong handshake và ảnh hưởng đến xử lý frame ra sao?
Bạn sẽ kiểm tra rủi ro của permessage-deflate khi bật nén cho thông điệp chứa dữ liệu nhạy cảm như thế nào?
Bạn so sánh một kết nối WebSocket lâu dài với nhiều kết nối HTTP ngắn về tài nguyên, độ trễ và vận hành ra sao?
Bạn phân biệt WebSocket frame và message để giải thích cách truyền một thông điệp lớn như thế nào?
Bạn mô tả các trường FIN, opcode, MASK và payload length trong WebSocket frame và mục đích của chúng ra sao?
Bạn giải thích vì sao frame từ browser client đến server cần được mask và máy chủ xử lý masking như thế nào?
Bạn phân biệt text frame và binary frame khi cần truyền JSON, ảnh hoặc dữ liệu nhị phân như thế nào?
Bạn lựa chọn định dạng JSON, Protobuf hoặc dữ liệu nhị phân cho WebSocket message theo những đánh đổi nào?
Bạn xử lý trường hợp một WebSocket message được chia thành nhiều frame và gửi xen kẽ control frame như thế nào?
Bạn giải thích vai trò của continuation frame và cách xác định thời điểm một fragmented message đã hoàn tất ra sao?
Bạn quyết định giới hạn kích thước frame, message và buffer để ngăn kết nối chiếm quá nhiều bộ nhớ như thế nào?
Bạn xử lý một text message có dữ liệu UTF-8 không hợp lệ theo quy tắc giao thức và chính sách ứng dụng ra sao?
Bạn phân biệt Ping, Pong và Close control frame với dữ liệu ứng dụng thông thường như thế nào?
Bạn dùng Ping/Pong để phát hiện kết nối không còn hoạt động khi client hoặc server im lặng lâu như thế nào?
Bạn giải thích vì sao trình duyệt dùng WebSocket API không trực tiếp gửi protocol Ping frame và chọn cơ chế heartbeat ứng dụng ra sao?
Bạn xác định khoảng heartbeat và timeout dựa trên độ trễ mạng, thiết bị di động và tải hệ thống như thế nào?
Bạn mô tả quá trình đóng kết nối đúng giao thức với Close frame và Close handshake như thế nào?
Bạn phân biệt WebSocket close code 1000, 1001, 1002, 1008 và 1011 theo tình huống sử dụng ra sao?
Bạn giải thích cách client nhận biết kết nối đóng bất thường khi không nhận được Close frame như thế nào?
Bạn thiết kế chính sách dọn dẹp tài nguyên khi một phía mất mạng mà không gửi thông điệp đóng kết nối ra sao?
Bạn xử lý trường hợp client gửi message trong lúc kết nối đang chuyển từ OPEN sang CLOSING như thế nào?
Bạn phân biệt trạng thái CONNECTING, OPEN, CLOSING và CLOSED của WebSocket trong trình duyệt và tổ chức UI tương ứng ra sao?
Bạn sẽ xác định những metadata nào cần lưu cho một WebSocket session để phục vụ nghiệp vụ và quản trị kết nối?
Bạn thiết kế ánh xạ giữa tài khoản người dùng, session và kết nối khi một người đăng nhập trên nhiều thiết bị như thế nào?
Bạn xử lý việc mở nhiều tab trình duyệt tạo nhiều kết nối WebSocket cho cùng một người dùng ra sao?
Bạn xây dựng cơ chế giới hạn số kết nối đồng thời trên mỗi người dùng hoặc mỗi tenant như thế nào?
Bạn phân biệt cách quản lý trạng thái kết nối WebSocket lâu dài với vòng đời của một HTTP request ngắn hạn như thế nào?
Bạn lựa chọn xác thực người dùng tại handshake hay ở cấp message dựa trên mô hình bảo mật nào?
Bạn phân biệt việc trình duyệt tự gửi cookie khi handshake với việc sử dụng bearer token từ client WebSocket như thế nào?
Bạn thiết kế xác thực WebSocket cho ứng dụng browser khi API JavaScript không cho tùy ý đặt Authorization header trong opening handshake ra sao?
Bạn xác minh và giới hạn Origin trong handshake để giảm nguy cơ Cross-Site WebSocket Hijacking như thế nào?
Bạn phân biệt vai trò của TLS, authentication và authorization trong một hệ thống dùng WebSocket ra sao?
Bạn bảo đảm client chỉ đăng ký nhận message thuộc phòng chat hoặc tài khoản mà họ được phép truy cập như thế nào?
Bạn thiết kế kiểm tra phân quyền cho từng loại message khi quyền truy cập của người dùng có thể thay đổi giữa phiên kết nối ra sao?
Bạn xử lý token hoặc phiên đăng nhập hết hạn trong khi WebSocket vẫn còn mở như thế nào?
Bạn xây dựng cơ chế thu hồi quyền truy cập ngay khi người dùng bị khóa tài khoản nhưng vẫn đang giữ kết nối như thế nào?
Bạn bảo vệ thông tin nhạy cảm khỏi query string, access log và message log khi thiết kế xác thực WebSocket ra sao?
Bạn xác định giới hạn tốc độ gửi message và kích thước payload để giảm nguy cơ spam hoặc tấn công từ client như thế nào?
Bạn thiết kế schema và validation cho message đầu vào để phân biệt lỗi cú pháp, lỗi nghiệp vụ và lỗi phân quyền ra sao?
Bạn tạo message envelope với type, messageId, timestamp và correlationId để client-server xử lý nhất quán như thế nào?
Bạn chọn cách phân biệt command, event và response trong một kết nối WebSocket truyền nhiều loại message ra sao?
Bạn thiết kế cơ chế trả lỗi ở tầng ứng dụng khi giao thức WebSocket không có HTTP status cho từng message như thế nào?
Bạn dùng correlationId để ghép phản hồi với yêu cầu khi một client gửi nhiều message bất đồng bộ cùng lúc ra sao?
Bạn xử lý trường hợp server phát lại cùng một event khiến client cập nhật giao diện hai lần như thế nào?
Bạn lựa chọn quy tắc idempotency khi một message từ client có thể được gửi lại sau reconnect ra sao?
Bạn giải thích mức bảo đảm thứ tự message trên một kết nối WebSocket và những giới hạn khi có nhiều nguồn sự kiện như thế nào?
Bạn dùng sequence number hoặc version để phát hiện thông điệp mất, trùng hoặc cũ trên client như thế nào?
Bạn thiết kế cơ chế xác nhận ứng dụng đã xử lý message khi giao thức WebSocket chỉ bảo đảm việc truyền qua kết nối như thế nào?
Bạn chọn cách lưu và phát lại message để client không bỏ lỡ sự kiện khi mất kết nối trong thời gian ngắn ra sao?
Bạn xác định điểm bắt đầu đồng bộ lại dữ liệu sau reconnect dựa trên eventId, cursor hoặc phiên bản trạng thái như thế nào?
Bạn quyết định khi nào phải tải snapshot trạng thái hiện tại thay vì phát lại toàn bộ sự kiện đã bỏ lỡ như thế nào?
Bạn thiết kế luồng cập nhật UI theo snapshot cộng với incremental events để tránh mất dữ liệu tại thời điểm nối lại như thế nào?
Bạn xử lý xung đột giữa thao tác người dùng chưa được xác nhận và bản cập nhật mới từ server như thế nào?
Bạn phân biệt reconnect mạng với đăng ký lại subscription và xác thực lại phiên trong hành vi client ra sao?
Bạn xây dựng thuật toán reconnect có exponential backoff và jitter để tránh nhiều client kết nối lại đồng loạt như thế nào?
Bạn quyết định trường hợp nào client nên ngừng reconnect tự động và báo lỗi cần người dùng can thiệp ra sao?
Bạn giải thích ảnh hưởng của chế độ ngủ thiết bị, chuyển mạng Wi-Fi sang di động và NAT timeout đến kết nối WebSocket như thế nào?
Bạn xử lý tình huống mạng đã ngắt nhưng client vẫn tưởng kết nối ở trạng thái OPEN như thế nào?
Bạn lựa chọn cách đo network latency, message latency và độ mới của dữ liệu được hiển thị như thế nào?
Bạn quyết định cơ chế backpressure khi client gửi nhanh hơn khả năng xử lý của server như thế nào?
Bạn quản lý hàng đợi gửi khi kết nối tạm chậm để không làm tăng bộ nhớ server vô hạn ra sao?
Bạn thiết kế chính sách drop, gộp cập nhật hay ngắt kết nối đối với client nhận thông điệp quá chậm như thế nào?
Bạn phân biệt thông điệp cần giao đáng tin cậy với cập nhật có thể bỏ qua như vị trí con trỏ hoặc trạng thái đang gõ ra sao?
Bạn kiểm soát kích thước và tốc độ gửi binary message để tránh cản trở các thông báo ưu tiên cao như thế nào?
Bạn tổ chức các thành phần WebSocket handler, service và repository trong ứng dụng Java/Spring sao cho logic nghiệp vụ dễ kiểm thử như thế nào?
Bạn cấu hình WebSocket endpoint trong Spring để nhận kết nối và kiểm soát các tham số transport ra sao?
Bạn sử dụng HandshakeInterceptor hoặc cơ chế tương đương để gắn thông tin người dùng vào WebSocket session như thế nào?
Bạn phân biệt việc xử lý trực tiếp bằng WebSocketHandler với sử dụng giao thức STOMP trong Spring như thế nào?
Bạn giải thích STOMP CONNECT, SUBSCRIBE, SEND, MESSAGE và DISCONNECT phối hợp để tạo kênh nhắn tin như thế nào?
Bạn phân biệt WebSocket frame với STOMP frame khi STOMP được dùng làm subprotocol như thế nào?
Bạn cấu hình endpoint và application destination prefix trong Spring WebSocket/STOMP theo quy tắc nào?
Bạn giải thích @MessageMapping xử lý thông điệp từ client và @SendTo định tuyến kết quả tới subscriber ra sao?
Bạn phân biệt destination /app, /topic, /queue và /user theo quy ước định tuyến trong Spring STOMP như thế nào?
Bạn dùng SimpMessagingTemplate để gửi cập nhật từ một service nghiệp vụ tới các client đang kết nối ra sao?
Bạn thiết kế user destination để gửi thông báo riêng tư tới đúng tài khoản khi người dùng có nhiều session như thế nào?
Bạn kiểm soát quyền SUBSCRIBE và SEND theo destination trong Spring Security như thế nào?
Bạn xử lý thông tin xác thực được cung cấp trong STOMP CONNECT khác gì với xác thực tại HTTP handshake ra sao?
Bạn dùng ChannelInterceptor để kiểm tra message, lưu ngữ cảnh người dùng hoặc hạn chế subscription như thế nào?
Bạn cấu hình cơ chế phản hồi lỗi cho client STOMP khi @MessageMapping gặp lỗi validation hoặc exception ra sao?
Bạn phân biệt simple in-memory broker với STOMP broker relay trong Spring theo khả năng mở rộng và vận hành ra sao?
Bạn sẽ chọn broker relay kết nối tới một message broker ngoài khi cần nhiều instance ứng dụng WebSocket dựa trên tiêu chí nào?
Bạn giải thích STOMP heart-beat được thương lượng giữa client và server và quan hệ với WebSocket Ping/Pong như thế nào?
Bạn đánh giá ý nghĩa của STOMP ACK và NACK khi cần biết bên tiêu thụ đã xử lý một message ra sao?
Bạn quyết định có nên dùng STOMP receipt để xác nhận thao tác subscription hoặc send và giới hạn của xác nhận đó như thế nào?
Bạn so sánh raw WebSocket và STOMP khi cần xây dựng chat, bảng giá thời gian thực hoặc trò chơi nhiều người như thế nào?
Bạn đánh giá trường hợp SockJS hoặc transport fallback có ích và những hạn chế vận hành của nó như thế nào?
Bạn giải thích vì sao session WebSocket là trạng thái cục bộ và gây khó khăn gì khi ứng dụng triển khai nhiều node?
Bạn lựa chọn sticky session hay kiến trúc phân phối message qua broker để phục vụ người dùng kết nối ở các node khác nhau như thế nào?
Bạn thiết kế fan-out một sự kiện từ service nghiệp vụ đến các kết nối WebSocket nằm trên nhiều instance ra sao?
Bạn đồng bộ metadata về user presence giữa nhiều node mà không phụ thuộc hoàn toàn vào một bộ nhớ cục bộ như thế nào?
Bạn ngăn trạng thái online bị sai khi một node chết đột ngột mà chưa kịp phát sự kiện disconnect ra sao?
Bạn lựa chọn giữa Redis Pub/Sub, message broker và event log bền vững cho luồng thông báo thời gian thực theo những tiêu chí nào?
Bạn phân biệt bảo đảm phát sự kiện qua message broker với bảo đảm client cuối cùng đã hiển thị sự kiện ra sao?
Bạn xử lý việc một message đi qua nhiều node làm phát sinh gửi trùng tới cùng một người dùng như thế nào?
Bạn thiết kế capacity planning cho số kết nối đồng thời, tốc độ message và bộ nhớ mỗi node theo cách nào?
Bạn cấu hình timeout và idle connection ở reverse proxy hoặc load balancer để tránh ngắt WebSocket ngoài ý muốn như thế nào?
Bạn thiết kế rolling deployment để client có thể reconnect sau khi node đang giữ kết nối được thay thế ra sao?
Bạn thực hiện graceful shutdown để hạn chế mất message và giúp client chuyển sang node còn hoạt động như thế nào?
Bạn dùng metric nào để giám sát số kết nối active, handshake failure, message rate và reconnect rate trong cụm WebSocket?
Bạn kết hợp log, sessionId và correlationId để truy vết một message từ client qua Spring đến client đích như thế nào?
Bạn xác định nút thắt khi handshake thành công nhưng message đến client bị trễ theo các bước điều tra nào?
Bạn nhận biết dấu hiệu nghẽn thread, event loop hoặc hàng đợi gửi khi số kết nối đồng thời tăng đột ngột như thế nào?
Bạn thiết kế cảnh báo phát hiện reconnect storm sau khi load balancer hoặc broker gặp sự cố ra sao?
Bạn phân biệt lỗi mạng, lỗi handshake, lỗi STOMP subscription và lỗi xử lý nghiệp vụ qua tín hiệu quan sát nào?
Bạn kiểm thử opening handshake hợp lệ và bị từ chối với nhiều origin, token và subprotocol bằng cách nào?
Bạn chuẩn bị các test case nào để xác minh text, binary, fragmented message, Ping/Pong và Close handshake?
Bạn viết integration test cho Spring WebSocket/STOMP để kiểm tra @MessageMapping và subscription nhận đúng nội dung như thế nào?
Bạn xác minh một client không thể SUBSCRIBE vào destination riêng của người dùng khác bằng bài kiểm thử nào?
Bạn kiểm thử reconnect sau timeout, mất Wi-Fi và chuyển mạng để kiểm tra khả năng khôi phục subscription ra sao?
Bạn mô phỏng việc server restart giữa quá trình gửi message để phát hiện message mất hoặc bị xử lý lặp như thế nào?
Bạn thiết kế kiểm thử tải với hàng nghìn kết nối WebSocket đồng thời để đánh giá memory, throughput và latency ra sao?
Bạn kiểm tra việc client nhận message theo thứ tự và khôi phục đúng trạng thái khi các sự kiện đến từ nhiều node như thế nào?
Bạn xác minh cách server phản ứng với message quá lớn, payload sai schema và tốc độ gửi bất thường bằng những test case nào?
Bạn kiểm thử hành vi khi broker relay bị ngắt kết nối nhưng các client vẫn còn WebSocket session như thế nào?
Bạn điều tra trường hợp handshake trả 101 thành công nhưng client không nhận được bất kỳ message STOMP nào theo trình tự nào?
Bạn phân tích nguyên nhân một số người dùng nhận thông báo trùng sau reconnect hoặc sau khi mở nhiều tab như thế nào?
Bạn xử lý sự cố hệ thống chat chỉ hoạt động trên một node nhưng mất thông báo khi mở rộng thành nhiều node ra sao?
Bạn giải thích cách thiết kế WebSocket phục vụ hệ thống thông báo đơn hàng thời gian thực với xác thực, phân quyền, reconnect và lưu sự kiện để phát lại như thế nào?
