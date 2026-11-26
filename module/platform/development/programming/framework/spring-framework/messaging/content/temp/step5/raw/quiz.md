Câu 1. Trong Spring Messaging, Message<T> thường chứa hai phần dữ liệu nào?
A. Tên broker và một transaction manager mặc định
B. Tên WebSocket endpoint và cấu hình session HTTP
C. Payload và tập metadata MessageHeaders đi kèm
D. Danh sách subscriber và một connection pool JMS
Đáp án đúng: C

Câu 2. Vì sao không nên coi MessageHeaders là một Map có thể sửa tùy ý?
A. Headers bị lưu riêng trong một bảng SQL khi tạo Message
B. Mỗi header buộc phải có giá trị dưới dạng byte[]
C. Headers chỉ tồn tại trong một phiên WebSocket đang mở
D. Nội dung headers được công bố theo giao diện bất biến
Đáp án đúng: D

Câu 3. Khi cần tạo Message<String> kèm một header mới, API nào thích hợp?
A. ConnectionFactory.createConnection().setHeader(...)
B. MessageBuilder.withPayload(...).setHeader(...).build()
C. SimpMessagingTemplate.getBroker().createHeader(...)
D. RSocketRequester.route(...).sendHeader(...)
Đáp án đúng: B

Câu 4. Vai trò chính của MessageChannel trong Spring Messaging là gì?
A. Đưa Message tới kênh xử lý bằng phương thức send
B. Chuyển dữ liệu SQL thành một payload JMS mặc định
C. Chuyển mọi consumer sang kết nối WebSocket mới
D. Tạo subscription STOMP tự động trong broker bên ngoài
Đáp án đúng: A

Câu 5. Một SubscribableChannel phù hợp khi consumer muốn nhận message bằng cách nào?
A. Đăng ký MessageHandler theo mô hình subscribe
B. Gọi poll() trực tiếp để lấy từng bản ghi từ channel
C. Chỉ dùng @JmsListener để kéo message từ channel
D. Gọi receiveAndConvert trên chính MessageHeaders
Đáp án đúng: A

Câu 6. Khi triển khai MessageHandler, callback nào xử lý thông điệp đến?
A. onConnect(ConnectionFactory) nhận một JMS Session
B. receivePayload(String) chỉ nhận body dạng văn bản
C. subscribe(SimpMessagingTemplate) nhận broker metadata
D. handleMessage(Message<?>) nhận đối tượng message
Đáp án đúng: D

Câu 7. Trong Spring Messaging, MessageConverter hỗ trợ nhu cầu nào?
A. Tự thiết lập định tuyến STOMP cho từng user đã đăng nhập
B. Chuyển đổi payload giữa Message và đối tượng ứng dụng
C. Đảm bảo message được lưu bền vững trong mọi broker
D. Tự commit giao dịch liên quan sau khi payload được đọc
Đáp án đúng: B

Câu 8. Khi dựng metadata cho một message STOMP cụ thể, API nào thường hữu ích?
A. SimpMessageHeaderAccessor hoặc StompHeaderAccessor
B. JdbcTemplate và một DataSource tại WebSocket handler
C. JmsTransactionManager và một Session XA mặc định
D. RSocketRequester.Builder để sửa STOMP frame header
Đáp án đúng: A

Câu 9. Trong method xử lý thông điệp, @Payload chỉ định điều gì?
A. Đối số được lấy từ phần payload của message đến
B. Đối số được lấy từ tên destination của message
C. Đối số chứa map mọi native header STOMP của frame
D. Đối số biểu diễn tên bean channel được inject
Đáp án đúng: A

Câu 10. Khi method handler cần một header có tên traceId, annotation nào phù hợp?
A. @DestinationVariable("traceId") trên payload object
B. @SendTo("traceId") trên tham số của handler
C. @Header("traceId") trên tham số tương ứng
D. @MessageMapping("traceId") trên chính tham số
Đáp án đúng: C

Câu 11. Khi muốn nhận nhiều header đã được resolve thành Map, annotation nào phù hợp?
A. @Payload trên String chỉ chứa một native header
B. @SendToUser trên Map nhận session identifier
C. @JmsListener trên Map tạo mới danh sách header
D. @Headers trên tham số Map của method handler
Đáp án đúng: D

Câu 12. Trong Spring WebSocket, điểm khác nhau cơ bản giữa WebSocket và STOMP là gì?
A. WebSocket chọn STOMP destination; STOMP chỉ là TCP transport
B. WebSocket vận chuyển; STOMP định nghĩa frame và đích nhận
C. STOMP có thể thay WebSocket handshake mà không cần endpoint
D. STOMP chỉ dành cho JMS nên không truyền qua WebSocket
Đáp án đúng: B

Câu 13. Annotation @EnableWebSocketMessageBroker thường kích hoạt điều gì?
A. Tự bật broker relay ngoài để lưu mọi message offline
B. Tự lập subscription STOMP cho mọi client đã kết nối
C. Hạ tầng xử lý message kiểu STOMP trên WebSocket
D. Tạo WebSocket handshake thay cho cả việc đăng ký endpoint
Đáp án đúng: C

Câu 14. Để client kết nối STOMP qua WebSocket tại đường dẫn /ws, thường cấu hình ở đâu?
A. Đăng ký endpoint qua StompEndpointRegistry trong config
B. Khai tên /ws làm queue trong JmsTransactionManager
C. Đặt @MessageMapping("/ws") cho mọi lời gọi handshake
D. Chỉ khai SimpMessagingTemplate với đích mặc định /ws
Đáp án đúng: A

Câu 15. Khi setApplicationDestinationPrefixes("/app"), SEND tới /app/chat thường đi đâu?
A. Được phát trực tiếp tới mọi subscriber của /topic/chat
B. Được đưa vào RSocket route có tên /app/chat
C. Được JMS broker coi là durable topic đã tạo
D. Được route đến phương thức @MessageMapping phù hợp
Đáp án đúng: D

Câu 16. Khi @MessageMapping có pattern /rooms/{roomId}, cách bind roomId phù hợp?
A. Đặt @Header("JMSMessageID") lên tham số roomId
B. Dùng @DestinationVariable("roomId") trong handler
C. Gọi @SendToUser("/rooms/roomId") để đọc biến
D. Thêm @Payload vào class cấu hình WebSocket broker
Đáp án đúng: B

Câu 17. Cấu hình enableSimpleBroker("/topic") thường xử lý loại destination nào?
A. Lời gọi HTTP POST đi tới controller /topic
B. Lời gọi JDBC insert bảng topic trong database
C. Message gửi tới các subscription dưới prefix /topic
D. Mọi request-response của RSocket cùng route /topic
Đáp án đúng: C

Câu 18. Khi muốn broadcast kết quả của @MessageMapping tới /topic/news, nên dùng gì?
A. @SendTo("/topic/news") trên phương thức xử lý
B. @Header("/topic/news") trên đối số nhận payload
C. @DestinationVariable("/topic/news") trên bean config
D. @Payload("/topic/news") trên return value handler
Đáp án đúng: A

Câu 19. Khi gửi kết quả handler tới hàng đợi riêng của người dùng, annotation nào hỗ trợ?
A. @SendTo cho bất kỳ topic broadcast công khai
B. @Headers chỉ rõ tên user trong payload String
C. @EnableJms tự thêm prefix /user cho response
D. @SendToUser với user destination phù hợp
Đáp án đúng: D

Câu 20. Nếu một service chủ động phát bản tin STOMP từ nghiệp vụ, API nào phù hợp?
A. JmsTemplate.receiveAndConvert từ topic WebSocket
B. RSocketRequester.retrieveFlux không cần route
C. SimpMessagingTemplate.convertAndSend tới destination
D. WebSocketStompClient.registerStompEndpoints trong service
Đáp án đúng: C

Câu 21. Khi chủ động gửi thông điệp tới user đã xác định, method nào đáng dùng?
A. SimpMessagingTemplate.getUserSession rồi gọi commit
B. JmsTemplate.convertAndSendToUser với endpoint STOMP
C. SimpMessagingTemplate.convertAndSendToUser với username
D. RSocketRequester.route(username) để tạo user subscription
Đáp án đúng: C

Câu 22. Trong STOMP, frame SUBSCRIBE của client thường biểu thị điều gì?
A. Đăng ký nhận message từ một destination được chọn
B. Gửi payload nghiệp vụ lên @MessageMapping của server
C. Đóng kết nối WebSocket và thu hồi principal
D. Xác nhận đã ghi message vào database nghiệp vụ
Đáp án đúng: A

Câu 23. Một client STOMP muốn đẩy payload tới application destination nên dùng frame nào?
A. SUBSCRIBE với header destination là body cần gửi
B. MESSAGE do client sinh để giả lập broker outbound
C. CONNECTED rồi chèn payload vào version header
D. SEND với destination nằm dưới prefix ứng dụng
Đáp án đúng: D

Câu 24. Trong Spring WebSocket messaging, clientInboundChannel thường dùng để làm gì?
A. Truyền message từ broker tới client socket outbound
B. Dẫn message từ client vào pipeline phía server
C. Gửi request SQL tới JDBC connection pool
D. Lưu offline message của topic vào database
Đáp án đúng: B

Câu 25. clientOutboundChannel trong hạ tầng STOMP/WebSocket có vai trò nào?
A. Tiếp nhận CONNECT frame trước khi authentication
B. Đăng ký toàn bộ @MessageMapping trong ApplicationContext
C. Tạo JMS destination mới khi một user đăng ký
D. Chuyển message phía server ra các kết nối client
Đáp án đúng: D

Câu 26. So với simple broker tích hợp, STOMP broker relay giải quyết nhu cầu nào tốt hơn?
A. Biến mọi lời gọi RSocket thành WebSocket handshake
B. Chuyển @JmsListener thành HTTP request handler
C. Giao việc xử lý STOMP cho broker bên ngoài qua relay
D. Thay Spring Security bằng xác thực native headers
Đáp án đúng: C

Câu 27. Vì sao simple broker không nên được xem như message store bền vững cho cụm nhiều node?
A. Nó luôn dùng một cơ sở SQL có replication riêng
B. Simple broker giữ subscription trong bộ nhớ ứng dụng
C. Nó sẽ chuyển subscriber sang Kafka nếu node restart
D. Nó bắt buộc thực hiện XA transaction trước khi SEND
Đáp án đúng: B

Câu 28. Khi dùng STOMP receipt header, xác nhận RECEIPT từ broker nên được hiểu thế nào?
A. Message đã được mọi subscriber lưu bền vững vào database
B. Tất cả handler downstream đã trả kết quả trong một transaction
C. Receipt tự thay thế toàn bộ quy trình retry và idempotency
D. RECEIPT xác nhận frame, không xác nhận commit nghiệp vụ
Đáp án đúng: D

Câu 29. STOMP heartbeat được dùng chủ yếu để hỗ trợ điều gì?
A. Bảo đảm thứ tự cập nhật dữ liệu giữa các subscriber
B. Nhận biết kết nối mất hoạt động hoặc gián đoạn
C. Tự tạo user principal từ một HTTP cookie session
D. Thay thế ACK frame để commit database transaction
Đáp án đúng: B

Câu 30. Trong Spring WebSocket/STOMP, Principal của session thường lấy từ đâu?
A. Tên class @MessageMapping được scan trong context
B. Ngữ cảnh xác thực gắn với HTTP handshake ban đầu
C. Giá trị của destination /topic trên frame SUBSCRIBE
D. MessageConverter mặc định sinh từ JSON payload
Đáp án đúng: B

Câu 31. Khi cho phép WebSocket clients từ origin bên ngoài, điều gì phải được cân nhắc?
A. Cho phép mọi origin thì token truy cập tự được kiểm tra
B. Chỉ tăng kích thước message buffer để chống truy cập sai
C. Giới hạn origin được phép và cơ chế xác thực phù hợp
D. Tắt channel interceptor vì origin đã đủ cho authorization
Đáp án đúng: C

Câu 32. Để kiểm tra quyền gửi hoặc subscribe theo destination, giải pháp Spring nào phù hợp?
A. Chỉ đặt security rule cho HTTP GET mà bỏ STOMP frame
B. Kiểm tra payload JSON hợp lệ thay cho user permission
C. Áp policy authorization lên client inbound messages
D. Dựa vào tên topic để chặn frame tại WebSocket transport
Đáp án đúng: C

Câu 33. Nếu logic cần chặn hoặc bổ sung metadata khi message vào clientInboundChannel, hook nào phù hợp?
A. RSocketRequester.Builder cùng hàm setupRoute
B. ChannelInterceptor với callback như preSend
C. JmsTemplate.convertAndSend với defaultDestination
D. BeanFactoryPostProcessor chạy khi context startup
Đáp án đúng: B

Câu 34. Nếu một @MessageMapping handler phát sinh lỗi cần trả thông báo có kiểm soát, điểm mở rộng nào phù hợp?
A. Dùng @MessageExceptionHandler để xử lý lỗi của handler
B. @AfterReturning để bắt exception trong method listener
C. @EnableJms để tự chuyển lỗi thành STOMP SEND
D. @SendToUser để loại bỏ exception mà không xử lý
Đáp án đúng: A

Câu 35. Khi client cũ không hỗ trợ WebSocket trực tiếp, cấu hình nào có thể cung cấp fallback?
A. RSocket TCP transport tự chuyển thành WebSocket fallback
B. SockJS trên STOMP endpoint nếu ứng dụng cho phép
C. JmsTemplate tự mở long-polling route cho browser
D. STOMP receipt frame tự kích hoạt HTTP polling
Đáp án đúng: B

Câu 36. Vì sao không thể mặc định kỳ vọng client STOMP offline nhận lại mọi message đã bỏ lỡ?
A. Mọi /topic subscription tự bền vững khi tạo
B. @SendTo luôn ghi toàn bộ message vào database
C. Phát lại message phụ thuộc broker và cấu hình lưu trữ
D. WebSocket session tự giữ backlog sau khi bị ngắt
Đáp án đúng: C

Câu 37. Với RSocket request-response, cặp API mô tả thường gặp nào đúng?
A. Requester gửi một Flux nhưng server cấm phản hồi
B. Requester chỉ phát metadata mà không gửi payload
C. Requester phải tạo STOMP SUBSCRIBE trước khi gọi
D. Requester nhận một kết quả Mono từ responder
Đáp án đúng: D

Câu 38. Trong RSocket request-stream, kiểu kết quả reactive nào thường phù hợp?
A. Flux phát nhiều phần tử dữ liệu từ responder
B. Mono<Void> chỉ xác nhận đã gửi một chiều
C. JMS MessageSelector trả một chuỗi nhận duy nhất
D. HTTP ResponseEntity trả tất cả frame theo blocking IO
Đáp án đúng: A

Câu 39. Tương tác RSocket fire-and-forget phù hợp nhất với nhu cầu nào?
A. Nhận stream dài dữ liệu kèm điều khiển backpressure
B. Yêu cầu một response object sau khi request xử lý
C. Nhận hai stream đồng thời theo hai chiều liên tục
D. Gửi một chiều và không chờ payload phản hồi nghiệp vụ
Đáp án đúng: D

Câu 40. Trong RSocket request-channel, mô hình trao đổi nào đúng?
A. Client chỉ gửi một payload và server chỉ trả một Mono
B. Hai bên trao đổi luồng dữ liệu trong một tương tác
C. Mọi message được phát tới topic qua một JMS broker
D. Server buộc trả một HTTP redirect sau khi connect
Đáp án đúng: B

Câu 41. Khi service Spring muốn gọi RSocket responder theo route, API nào thường dùng?
A. RSocketRequester.route(...).data(...).retrieveMono(...)
B. JmsTemplate.convertAndSend(...).retrieveMono(...)
C. SimpMessagingTemplate.subscribe(...).retrieveMono(...)
D. WebSocketStompClient.connect(...).executeCypher(...)
Đáp án đúng: A

Câu 42. Ở Spring RSocket, @MessageMapping thường dùng để khai báo điều gì?
A. HTTP endpoint được map theo URL trong DispatcherServlet
B. Đích JMS queue tự sinh cho mỗi entity repository
C. Handler nhận message theo route metadata từ requester
D. Kết nối WebSocket handshake phải dùng STOMP CONNECT
Đáp án đúng: C

Câu 43. RSocket request-stream khác việc gửi một danh sách đồng bộ ở điểm nào?
A. Mỗi request-stream bắt buộc dùng một JDBC transaction
B. Dùng backpressure theo demand của luồng reactive
C. Server luôn tính xong toàn bộ stream trước khi gửi
D. Publisher của stream được broker JMS lưu bền mặc định
Đáp án đúng: B

Câu 44. Trong Spring, cách gửi message qua JMS và qua STOMP/WebSocket khác nhau chủ yếu ở thành phần nào?
A. JmsTemplate gửi JMS; SimpMessagingTemplate gửi STOMP
B. Cả hai buộc chạy cùng một JMS Session để gửi tin
C. SimpMessagingTemplate phải mở JDBC ConnectionFactory
D. JmsTemplate chỉ gửi được khi STOMP broker relay bật
Đáp án đúng: A

Câu 45. Một @JmsListener và một @MessageMapping STOMP cùng xử lý nghiệp vụ có chung điều kiện gì?
A. Mọi annotation tự tạo subscription bền vững cho cùng queue
B. Cả hai luôn tham gia cùng một transaction database
C. Cả hai bắt buộc trả một STOMP MESSAGE frame cho client
D. Cần cấu hình hạ tầng listener phù hợp cho mỗi annotation
Đáp án đúng: D

Câu 46. Trong ứng dụng nhận JMS rồi phát WebSocket notification, điều gì cần thiết kế để tránh thông báo sai?
A. Chỉ thay đổi destination để gộp transaction JMS và WebSocket
B. Dùng chung một MessageConverter sẽ cho exactly-once delivery
C. Chỉ đặt @SendTo là WebSocket tự chờ DB commit
D. Quản lý commit và phục hồi nếu phát notification thất bại
Đáp án đúng: D

Câu 47. Khi kiểm thử thông điệp STOMP/WebSocket qua Spring, cách nào đáng tin cậy?
A. Thử send/subscribe bằng client STOMP với server test
B. Chỉ mock method @MessageMapping mà không chạy WebSocket
C. Chỉ assert có bean SimpMessagingTemplate để kết luận frame đúng
D. Chỉ kiểm tra annotation ở controller mà không gửi frame
Đáp án đúng: A

Câu 48. Trong hệ thống kết hợp STOMP, RSocket và JMS, cách quan sát luồng xử lý nào phù hợp?
A. Chỉ dựa vào ThreadLocal vì context tự vượt qua broker
B. Dùng chung tên bean giữa các transport để chia sẻ traceId
C. Truyền metadata trace qua transport và đo lỗi từng chặng
D. Tắt log nghiệp vụ để mọi lỗi message tự được retry
Đáp án đúng: C
