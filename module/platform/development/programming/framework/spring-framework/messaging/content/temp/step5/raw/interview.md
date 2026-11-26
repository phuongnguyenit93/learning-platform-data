Bạn giải thích Spring Messaging cung cấp những abstraction chung nào cho giao tiếp bằng thông điệp trong ứng dụng Spring Framework?
Bạn phân biệt Spring Messaging core với các module Spring JMS, Spring WebSocket và tích hợp RSocket theo trách nhiệm như thế nào?
Bạn mô tả Message<T> biểu diễn payload và metadata để nhiều transport dùng chung một hợp đồng ra sao?
Bạn phân biệt MessageHeaders với các field nghiệp vụ của payload trong thiết kế một domain event như thế nào?
Bạn sẽ dùng MessageBuilder để tạo message với content-type và correlation ID theo cách nào?
Bạn phân biệt MessageBuilder.withPayload với MessageBuilder.fromMessage khi tạo thông điệp chuyển tiếp ra sao?
Bạn đánh giá rủi ro lưu password hoặc token nhạy cảm vào MessageHeaders có thể bị log hoặc chuyển tiếp như thế nào?
Bạn phân biệt MessageHeaders.ID với business event ID cần thiết cho idempotency như thế nào?
Bạn sẽ thiết kế quy ước header và payload để producer và consumer không phụ thuộc tên class Java của nhau ra sao?
Bạn phân tích vì sao headers trong bộ nhớ không phải lúc nào cũng được ánh xạ nguyên vẹn sang STOMP hoặc JMS như thế nào?
Bạn mô tả vai trò của MessageHeaderAccessor khi đọc hoặc tạo metadata cho một thông điệp như thế nào?
Bạn phân biệt MessageHeaderAccessor và NativeMessageHeaderAccessor khi thao tác với header riêng của một giao thức ra sao?
Bạn sẽ thiết kế Message payload bất biến để tránh sửa dữ liệu đồng thời trong nhiều luồng xử lý ra sao?
Bạn đánh giá khi nào cần versioning schema của message thay vì chỉ thêm một header mới như thế nào?
Bạn sẽ phân biệt header do ứng dụng tin cậy tạo với header được truyền từ client chưa xác thực như thế nào?
Bạn giải thích MessageChannel chịu trách nhiệm gì trong việc kết nối producer với handler của Spring?
Bạn phân biệt MessageChannel với MessageHandler theo vai trò gửi và xử lý thông điệp ra sao?
Bạn sẽ dùng SubscribableChannel trong trường hợp consumer được gọi khi có message như thế nào?
Bạn phân biệt SubscribableChannel và PollableChannel theo cơ chế consumer nhận thông điệp ra sao?
Bạn phân tích vì sao một channel trong JVM không tự bảo đảm message durability như broker bên ngoài như thế nào?
Bạn sẽ lựa chọn ExecutorSubscribableChannel khi nào để tách thread gửi khỏi thread thực thi handler?
Bạn đánh giá tác động của executor queue đầy tới việc gửi message trên một channel bất đồng bộ ra sao?
Bạn phân biệt thành công của MessageChannel.send với kết quả nghiệp vụ khi handler được chạy sau đó ra sao?
Bạn sẽ giới hạn concurrency của handler khi một channel có lượng message tăng mạnh như thế nào?
Bạn phân tích vì sao nhiều handlers cùng subscribe vào một channel không nhất thiết có ngữ nghĩa competing consumers của queue ra sao?
Bạn sẽ đánh giá khi nào cần Spring Integration DirectChannel thay vì các abstraction có sẵn trong Spring Messaging core như thế nào?
Bạn mô tả vai trò của ChannelInterceptor khi kiểm tra hoặc điều chỉnh message trên đường qua channel ra sao?
Bạn phân biệt preSend, postSend và afterSendCompletion của ChannelInterceptor theo thời điểm thực thi như thế nào?
Bạn sẽ chẩn đoán vì sao ChannelInterceptor.preSend trả null khiến một message bị loại bỏ ra sao?
Bạn phân tích rủi ro interceptor thay đổi payload mà không được domain service chấp thuận như thế nào?
Bạn sẽ đặt logging và metric trong interceptor mà không ghi lại dữ liệu nhạy cảm ra sao?
Bạn phân biệt ExecutorChannelInterceptor với ChannelInterceptor khi cần quan sát thread thực thi handler như thế nào?
Bạn sẽ đo độ trễ xếp hàng và thời gian xử lý thực tế của MessageHandler độc lập ra sao?
Bạn phân tích cách exception của handler đồng bộ khác với exception của handler chạy qua executor như thế nào?
Bạn sẽ phân biệt MessagingException, MessageDeliveryException và MessageHandlingException khi chẩn đoán lỗi ở các giai đoạn ra sao?
Bạn mô tả cách một ErrorMessage có thể chuyển thông tin lỗi tới kênh quan sát riêng của ứng dụng như thế nào?
Bạn sẽ thiết kế luồng lỗi cho handler không để producer nhầm việc enqueue thành công với xử lý thành công ra sao?
Bạn phân tích rủi ro retry tự động ở một channel khi handler thực hiện side effect không idempotent như thế nào?
Bạn sẽ kiểm thử MessageChannel và các handlers bằng message giả lập không cần broker ngoài như thế nào?
Bạn giải thích MessageConverter tách định dạng dữ liệu nhận được khỏi Java payload type mà handler sử dụng như thế nào?
Bạn phân biệt MessageConverter của Spring Messaging với converter làm việc trên jakarta.jms.Message trong Spring JMS ra sao?
Bạn sẽ lựa chọn StringMessageConverter, ByteArrayMessageConverter hoặc MappingJackson2MessageConverter theo kiểu payload nào?
Bạn mô tả content-type header ảnh hưởng tới quá trình chuyển đổi payload như thế nào?
Bạn sẽ cấu hình CompositeMessageConverter khi hệ thống hỗ trợ nhiều định dạng message như thế nào?
Bạn phân tích ảnh hưởng của thứ tự converters khi nhiều converter đều có thể xử lý một kiểu payload ra sao?
Bạn sẽ dùng SmartMessageConverter khi cần gợi ý kiểu Java đích trong quá trình conversion như thế nào?
Bạn đánh giá khi nào cần custom MessageConverter thay vì đặt logic parse JSON trong handler như thế nào?
Bạn sẽ thiết kế schema compatibility để consumer cũ đọc được event do producer mới phát ra như thế nào?
Bạn phân tích nguy cơ converter dựa vào type hint không đáng tin cậy làm deserialize sai loại object như thế nào?
Bạn sẽ kiểm soát payload size trước khi convert để tránh cạn heap hoặc chiếm thread quá lâu ra sao?
Bạn phân biệt lỗi deserialize message với lỗi validate dữ liệu nghiệp vụ sau conversion như thế nào?
Bạn sẽ tổ chức kiểm thử converter cho field thiếu, null, Unicode và enum mới như thế nào?
Bạn sẽ bảo toàn correlation ID và custom headers khi message được chuyển qua nhiều adapter ra sao?
Bạn mô tả vai trò của MessageSendingOperations khi service muốn gửi message mà không phụ thuộc vào transport cụ thể ra sao?
Bạn phân biệt GenericMessagingTemplate với gửi trực tiếp bằng MessageChannel.send theo nhu cầu như thế nào?
Bạn sẽ dùng AbstractMessagingTemplate trong thiết kế một messaging adapter có chức năng conversion ra sao?
Bạn phân tích vì sao send timeout của messaging template không bảo đảm cùng ngữ nghĩa trên mọi transport như thế nào?
Bạn sẽ thiết kế interface domain publisher để có thể thay JMS bằng một transport khác mà không sửa logic nghiệp vụ ra sao?
Bạn mô tả cách kết hợp tracing headers, error handling và converter vào một pipeline không làm nhân đôi trách nhiệm ra sao?
Bạn giải thích JmsMessagingTemplate kết nối abstraction Spring Message với Jakarta Messaging như thế nào?
Bạn phân biệt JmsMessagingTemplate với JmsTemplate về payload, headers và API được cung cấp ra sao?
Bạn sẽ chọn JmsTemplate khi cần điều khiển chi tiết jakarta.jms.Message trong trường hợp nào?
Bạn phân tích khả năng chuyển MessageHeaders sang JMS properties và những giới hạn về kiểu dữ liệu ra sao?
Bạn sẽ thiết kế business event ID riêng thay vì chỉ dựa vào JMSMessageID khi chống xử lý trùng như thế nào?
Bạn mô tả vai trò của @EnableJms và @JmsListener trong việc đăng ký listener Spring với JMS provider như thế nào?
Bạn sẽ cấu hình listener container cho queue và topic mà không nhầm cơ chế pubSubDomain như thế nào?
Bạn phân biệt một JMS listener container với SubscribableChannel handler chỉ hoạt động trong JVM ra sao?
Bạn sẽ lựa chọn MessageConverter cho JMS listener để chuyển message thành DTO nhất quán như thế nào?
Bạn phân tích lỗi converter khiến @JmsListener chưa nhận được payload và cần xử lý ở tầng nào ra sao?
Bạn sẽ định tuyến một message bằng JMS property selector mà không tin đó là cơ chế authorization như thế nào?
Bạn mô tả vai trò của JMSCorrelationID và JMSReplyTo khi xây dựng request-reply qua JMS ra sao?
Bạn phân biệt acknowledgment do JMS provider quản lý với việc Spring domain service đã hoàn thành business transaction ra sao?
Bạn sẽ chọn transaction boundary để tránh acknowledge trước khi dữ liệu được ghi bền vững như thế nào?
Bạn phân tích rủi ro database commit thành công nhưng JMS session rollback khiến message được redeliver như thế nào?
Bạn sẽ thiết kế idempotent consumer để xử lý nhiều lần một business event mà không tạo kết quả trùng ra sao?
Bạn phân biệt retry do Spring handler với retry/redelivery do JMS broker về số lượt thực thi thực tế như thế nào?
Bạn sẽ quyết định khi nào một message lỗi schema cần vào dead-letter queue thay vì retry liên tục như thế nào?
Bạn đánh giá ảnh hưởng của số concurrent listeners lên thứ tự xử lý trong queue như thế nào?
Bạn sẽ thiết kế một listener trả kết quả cho WebSocket notification mà không giữ JMS session quá lâu ra sao?
Bạn phân tích vì sao JMS persistent delivery không tự bảo đảm thông điệp tới WebSocket client đang offline ra sao?
Bạn sẽ kiểm tra producer và consumer dùng hai converter khác nhau có còn tuân thủ message contract như thế nào?
Bạn đánh giá khi nào dùng transactional outbox thay vì yêu cầu JMS và database tham gia cùng một giao dịch phân tán ra sao?
Bạn sẽ tổ chức graceful shutdown để JMS listener không mất thông điệp đang xử lý khi ứng dụng dừng ra sao?
Bạn sẽ kiểm thử JmsMessagingTemplate với JMS broker thật trong Testcontainers theo những kịch bản nào?
Bạn giải thích WebSocket cung cấp kết nối song công còn STOMP cung cấp khả năng định tuyến message trên kết nối đó như thế nào?
Bạn phân biệt WebSocket frames thuần với STOMP frames trong Spring WebSocket như thế nào?
Bạn sẽ lựa chọn WebSocket/STOMP thay vì JMS cho giao tiếp browser realtime theo tiêu chí nào?
Bạn mô tả vai trò của @EnableWebSocketMessageBroker khi bật annotation-based STOMP messaging ra sao?
Bạn phân biệt WebSocketMessageBrokerConfigurer với một configuration class chỉ khai báo bean thông thường như thế nào?
Bạn sẽ dùng registerStompEndpoints để tạo endpoint STOMP handshake cho browser client như thế nào?
Bạn phân biệt HTTP WebSocket handshake với STOMP CONNECT thực hiện sau khi transport được thiết lập ra sao?
Bạn sẽ xác định khi nào cần SockJS fallback thay vì chỉ sử dụng native WebSocket như thế nào?
Bạn phân tích rủi ro cho phép mọi origins truy cập endpoint WebSocket có cookie authentication như thế nào?
Bạn sẽ cấu hình allowedOriginPatterns sao cho không mở quyền truy cập ngoài những origins được phép ra sao?
Bạn giải thích configureMessageBroker phân chia destinations gửi tới ứng dụng và destinations gửi tới broker như thế nào?
Bạn phân biệt setApplicationDestinationPrefixes với enableSimpleBroker về cách routing một STOMP SEND như thế nào?
Bạn sẽ thiết kế quy ước /app, /topic, /queue và /user nhằm phân biệt command với notification ra sao?
Bạn đánh giá hậu quả khi client gửi vào /topic thay vì /app khiến @MessageMapping không được gọi như thế nào?
Bạn mô tả vai trò của CONNECT, CONNECTED, SEND, SUBSCRIBE và DISCONNECT trong vòng đời STOMP session ra sao?
Bạn phân biệt STOMP ERROR frame với message lỗi nghiệp vụ trả từ một controller method như thế nào?
Bạn sẽ cấu hình STOMP heart-beat để phát hiện client ngừng hoạt động trong môi trường mạng không ổn định như thế nào?
Bạn phân tích vì sao một TCP socket vẫn mở không bảo đảm STOMP client còn xử lý notifications bình thường ra sao?
Bạn sẽ dùng receipt header của STOMP để xác minh điều gì mà không nhầm với business commit như thế nào?
Bạn đánh giá tác động của client reconnect rồi gửi lại SEND khi không chắc server đã xử lý command như thế nào?
Bạn sẽ thiết kế idempotency key cho command từ STOMP client có khả năng gửi lặp ra sao?
Bạn mô tả vai trò của clientInboundChannel, clientOutboundChannel và brokerChannel trong Spring STOMP messaging ra sao?
Bạn phân biệt một frame được chuyển tới controller với một frame được broker phát cho subscribers như thế nào?
Bạn sẽ dùng ChannelInterceptor trên clientInboundChannel để kiểm tra CONNECT và SEND theo tiêu chí nào?
Bạn phân tích rủi ro interceptor thực hiện truy vấn database chậm gây nghẽn inbound messaging như thế nào?
Bạn sẽ thiết kế concurrency của clientInboundChannel theo tải thực tế thay vì tăng thread vô hạn ra sao?
Bạn đánh giá tác động của clientOutboundChannel khi một số WebSocket clients đọc dữ liệu rất chậm ra sao?
Bạn sẽ giới hạn message size, send buffer và send time để tránh một phiên chiếm memory quá mức như thế nào?
Bạn phân tích nguy cơ subscriptions không giới hạn khiến broker và ứng dụng mất tài nguyên như thế nào?
Bạn giải thích simple broker của Spring có những đặc điểm nào khi phục vụ STOMP subscriptions trong một tiến trình như thế nào?
Bạn phân biệt enableSimpleBroker với enableStompBrokerRelay về routing, scaling và external broker như thế nào?
Bạn sẽ lựa chọn broker relay khi nào nếu ứng dụng WebSocket được triển khai nhiều replicas?
Bạn phân tích vì sao simple broker trong memory có thể không đáp ứng các yêu cầu fan-out qua nhiều Spring instances ra sao?
Bạn sẽ cấu hình thông tin host và credential cho broker relay mà không ghi secret vào repository như thế nào?
Bạn đánh giá cách xử lý khi WebSocket còn kết nối nhưng broker relay tạm thời mất khả năng truyền notification ra sao?
Bạn sẽ theo dõi broker availability riêng với số WebSocket sessions còn kết nối như thế nào?
Bạn mô tả @MessageMapping gắn một method Spring controller với destination của client như thế nào?
Bạn phân biệt @MessageMapping với @RequestMapping về cách method được gọi và trả dữ liệu ra sao?
Bạn sẽ tạo handler cho /app/orders/submit nhận DTO và validation trước khi gọi domain service như thế nào?
Bạn giải thích @Payload cho phép map phần thân message thành Java argument qua converter như thế nào?
Bạn sẽ sử dụng @Header và @Headers để đọc metadata mà không đưa logic giao thức vào domain service ra sao?
Bạn phân biệt @DestinationVariable với @Header khi lấy mã đối tượng từ STOMP destination như thế nào?
Bạn sẽ xử lý một message có payload không hợp lệ mà không làm sập toàn bộ WebSocket session như thế nào?
Bạn đánh giá rủi ro controller trả trực tiếp entity có relationship hoặc field nhạy cảm ra sao?
Bạn sẽ chọn khi nào @MessageMapping trả object và khi nào gọi SimpMessagingTemplate từ application service như thế nào?
Bạn giải thích @SendTo đưa kết quả từ handler tới destination dành cho subscribers như thế nào?
Bạn phân biệt @SendTo với @SendToUser khi phản hồi chỉ cho một user hoặc session ra sao?
Bạn sẽ dùng @SendToUser với broadcast=false khi chỉ cần trả cho session đã gửi yêu cầu như thế nào?
Bạn phân tích nguy cơ gửi notification riêng tư vào public /topic khiến nhiều client đọc được như thế nào?
Bạn sẽ sử dụng SimpMessagingTemplate.convertAndSend để gửi event không xuất phát trực tiếp từ STOMP request ra sao?
Bạn phân biệt convertAndSend với convertAndSendToUser trong cách Spring định tuyến người nhận như thế nào?
Bạn giải thích vai trò của SimpMessageSendingOperations khi muốn che chi tiết template trong business service như thế nào?
Bạn sẽ dùng SimpMessageHeaderAccessor để thiết lập các thông tin cần thiết trong một message server phát ra ra sao?
Bạn phân biệt SimpMessageHeaderAccessor và StompHeaderAccessor khi xử lý native STOMP headers như thế nào?
Bạn sẽ sử dụng Principal từ session để xác định danh tính thay vì tin username trong client payload như thế nào?
Bạn phân tích cách UserDestinationMessageHandler ánh xạ các user destinations về sessions thực tế ra sao?
Bạn sẽ tra cứu SimpUserRegistry khi cần biết một user có nhiều sessions hoặc subscriptions như thế nào?
Bạn đánh giá khi nào cần gửi notification tới tất cả sessions của user thay vì chỉ một session như thế nào?
Bạn sẽ thiết kế user destination sao cho tenant này không truy cập dữ liệu của tenant khác ra sao?
Bạn mô tả @SubscribeMapping giúp client lấy dữ liệu ban đầu khi đăng ký một destination như thế nào?
Bạn phân biệt @SubscribeMapping với @MessageMapping khi client muốn lấy snapshot rồi nhận cập nhật tiếp như thế nào?
Bạn sẽ thiết kế quy trình tránh mất event giữa thời điểm đọc snapshot và bắt đầu subscription như thế nào?
Bạn giải thích vai trò của @MessageExceptionHandler trong xử lý lỗi phát sinh từ STOMP controller methods như thế nào?
Bạn phân biệt @MessageExceptionHandler với @ControllerAdvice khi áp dụng chính sách lỗi chung cho nhiều controllers ra sao?
Bạn sẽ gửi validation error tới đúng session mà không broadcast chi tiết lỗi tới toàn bộ subscribers như thế nào?
Bạn phân tích rủi ro gửi stack trace, connection string hoặc tên bảng tới STOMP client như thế nào?
Bạn phân biệt SessionConnectEvent và SessionConnectedEvent về thời điểm xác lập kết nối như thế nào?
Bạn sẽ sử dụng SessionSubscribeEvent và SessionDisconnectEvent để quan sát lifecycle của subscribers như thế nào?
Bạn phân tích vì sao cleanup trên SessionDisconnectEvent cần idempotent do có thể phát nhiều sự kiện cho cùng session như thế nào?
Bạn sẽ xác định khi nào người dùng thực sự offline nếu họ có nhiều WebSocket sessions đang hoạt động ra sao?
Bạn đánh giá khi nào cần lưu presence trong shared store thay vì Map cục bộ khi ứng dụng nhiều replicas như thế nào?
Bạn sẽ sử dụng HandshakeInterceptor để đọc metadata của handshake mà không tin dữ liệu client chưa xác thực như thế nào?
Bạn phân biệt HTTP handshake authentication với xác thực STOMP CONNECT trong cùng một connection như thế nào?
Bạn sẽ thiết kế authorization SEND và SUBSCRIBE theo từng destination trong Spring Security như thế nào?
Bạn phân tích rủi ro chỉ kiểm tra quyền tại @MessageMapping mà bỏ quên quyền SUBSCRIBE vào broker như thế nào?
Bạn sẽ áp dụng CSRF và same-origin protection phù hợp cho STOMP WebSocket sử dụng cookies ra sao?
Bạn đánh giá khi nào cần rate limit theo session hoặc Principal để ngăn gửi quá nhiều STOMP frames ra sao?
Bạn sẽ xác minh destination có tenantId do client truyền được kiểm tra theo identity thật như thế nào?
Bạn phân tích vì sao một command xử lý lâu không nên chạy trực tiếp trên thread của inbound channel như thế nào?
Bạn sẽ thiết kế listener dọn subscriptions khi client disconnect bất thường mà không giữ dữ liệu vô thời hạn ra sao?
Bạn giải thích RSocket hỗ trợ các kiểu trao đổi thông điệp khác gì với WebSocket/STOMP trong ứng dụng Spring như thế nào?
Bạn phân biệt RSocket với JMS về khả năng backpressure và độ bền message như thế nào?
Bạn sẽ lựa chọn RSocket cho giao tiếp giữa các backend services trong tình huống nào?
Bạn mô tả các RSocket interaction models requestResponse, fireAndForget, requestStream và requestChannel ra sao?
Bạn sẽ chọn requestResponse cho thao tác trả một kết quả còn requestStream cho dữ liệu dạng luồng như thế nào?
Bạn phân tích rủi ro fireAndForget khi caller không có business response chứng minh thao tác đã hoàn tất ra sao?
Bạn sẽ thiết kế requestChannel khi cả hai phía liên tục gửi và nhận các phần tử thuộc cùng một cuộc trao đổi như thế nào?
Bạn giải thích backpressure của Reactive Streams ảnh hưởng số phần tử RSocket requester nhận trong requestStream như thế nào?
Bạn phân biệt backpressure với rate limiting theo hợp đồng nghiệp vụ khi hệ thống đang quá tải ra sao?
Bạn mô tả RSocketRequester cung cấp các thao tác route, data và metadata cho từng request như thế nào?
Bạn sẽ cấu hình RSocketRequester.Builder để kết nối RSocket qua TCP trong môi trường nội bộ ra sao?
Bạn phân biệt RSocket TCP transport với RSocket over WebSocket transport khi đi qua HTTP gateway như thế nào?
Bạn giải thích RSocketStrategies phối hợp converter, encoder và metadata extractor như thế nào?
Bạn sẽ xác định data MIME type giữa requester và responder để tránh lỗi conversion ra sao?
Bạn phân tích hậu quả khi route metadata hoặc content type không phù hợp với RSocketStrategies của responder như thế nào?
Bạn mô tả RSocketMessageHandler chọn method @MessageMapping dựa trên routing metadata ra sao?
Bạn sẽ xây dựng responder với @MessageMapping trả Mono cho một requestResponse như thế nào?
Bạn phân biệt @MessageMapping trong RSocket với @MessageMapping trong STOMP về cơ chế runtime và transport như thế nào?
Bạn sẽ sử dụng RSocketRequester.route để gọi method được ánh xạ bằng @MessageMapping ra sao?
Bạn đánh giá khi nào nên đặt version trong route thay vì dựa hoàn toàn vào payload schema như thế nào?
Bạn mô tả @ConnectMapping xử lý setup connection và thông tin ban đầu của RSocket requester như thế nào?
Bạn phân tích nguy cơ thực thi side effect không idempotent trong @ConnectMapping khi requester reconnect nhiều lần ra sao?
Bạn sẽ thiết kế authentication bằng metadata tại kết nối và authorization riêng cho từng RSocket route như thế nào?
Bạn sẽ kiểm soát quyền truy cập một route theo tenant thay vì tin tenantId trong payload như thế nào?
Bạn giải thích sự khác nhau giữa Mono.empty và error signal khi một RSocket query không tìm thấy dữ liệu ra sao?
Bạn sẽ tổ chức Flux trả nhiều kết quả mà không collectList toàn bộ vào heap như thế nào?
Bạn phân tích tác động của downstream cancellation tới database query phục vụ một requestStream như thế nào?
Bạn sẽ kiểm tra một RSocket responder không gọi block trên event-loop thread khi truy cập dữ liệu như thế nào?
Bạn đánh giá nguy cơ cùng một cold publisher bị subscribe hai lần khiến một write request được gửi lặp ra sao?
Bạn sẽ thiết kế retryWhen cho một RSocket read có khả năng retry mà không tạo retry storm như thế nào?
Bạn phân tích rủi ro retry fireAndForget khi request trước có thể đã được thực thi thành công như thế nào?
Bạn sẽ dùng idempotency key trong route metadata để kiểm soát side effects trùng ra sao?
Bạn sẽ thiết kế timeout và cancellation cho một stream vượt deadline của caller như thế nào?
Bạn phân biệt lỗi business validation với lỗi RSocket connection hoặc route-not-found khi ánh xạ response ra sao?
Bạn sẽ xử lý exception trong một RSocket @MessageMapping method theo hợp đồng lỗi thống nhất như thế nào?
Bạn mô tả vai trò của keepalive và reconnect đối với một RSocket connection hoạt động lâu dài như thế nào?
Bạn sẽ quản lý lifecycle RSocketRequester để tránh tạo kết nối mới cho mọi lời gọi nghiệp vụ ra sao?
Bạn đánh giá cách graceful shutdown ảnh hưởng các RSocket streams đang chạy như thế nào?
Bạn phân tích ảnh hưởng của số requestResponse đồng thời tới database pool dù truyền qua non-blocking RSocket như thế nào?
Bạn sẽ áp dụng giới hạn concurrency của flatMap để tránh quá tải responder như thế nào?
Bạn xác định cách truyền trace context qua RSocket metadata khi một workflow đi qua nhiều services ra sao?
Bạn sẽ kiểm thử requestResponse, requestStream và requestChannel với RSocketRequester và StepVerifier như thế nào?
Bạn giải thích vì sao JMS, STOMP và RSocket cần adapter riêng dù cùng dùng một business event schema như thế nào?
Bạn sẽ thiết kế một JMS consumer phát WebSocket notification mà không giữ JMS transaction quá lâu ra sao?
Bạn phân tích vì sao UI cần đồng bộ trạng thái lại sau reconnect thay vì coi WebSocket notification là nguồn dữ liệu cuối cùng như thế nào?
Bạn sẽ đưa một event từ RSocket request vào JMS queue theo transaction boundary nào để không mất dữ liệu ra sao?
Bạn đánh giá khi nào phải dùng transactional outbox trước khi phát đồng thời qua nhiều messaging transports như thế nào?
Bạn sẽ giữ correlation ID thống nhất qua JMS, WebSocket/STOMP và RSocket theo contract nào?
Bạn phân tích rủi ro cùng một business event được gửi nhiều lần qua các transports và gây side effects trùng như thế nào?
Bạn sẽ tổ chức MessageConverter ở transport adapter để domain model không phụ thuộc native headers như thế nào?
Bạn đánh giá khi nào cần một schema registry hoặc contract test chung cho các message payload ra sao?
Bạn sẽ phân biệt gửi thành công tới broker với hoàn tất xử lý nghiệp vụ trong các service level indicators như thế nào?
Bạn mô tả cách dùng Micrometer để đo send failures, handler latency và message conversion errors trong các pipeline ra sao?
Bạn sẽ xây dựng metrics riêng cho queue lag của JMS, subscriptions của STOMP và stream latency của RSocket như thế nào?
Bạn phân tích rủi ro đưa userId, messageId hoặc sessionId vào metric labels khiến cardinality tăng nhanh như thế nào?
Bạn sẽ sử dụng tracing headers để liên kết spans qua các lời gọi message bất đồng bộ như thế nào?
Bạn phân biệt context propagation qua Reactor Context với ThreadLocal trong handler chạy trên executor như thế nào?
Bạn sẽ xây dựng policy logging không lưu payload nhạy cảm khi message bị chuyển vào dead-letter queue ra sao?
Bạn đánh giá rủi ro lộ dữ liệu người dùng khi broadcast STOMP error hoặc trace thông tin exception như thế nào?
Bạn sẽ thiết kế lifecycle cleanup cho broker connections, WebSocket sessions và RSocket requesters khi Spring context đóng như thế nào?
Bạn phân tích vì sao readiness và liveness của ứng dụng cần được tách khi JMS broker hoặc STOMP relay tạm không sẵn sàng như thế nào?
Bạn sẽ xây dựng runbook xử lý broker relay outage dù HTTP health endpoint còn trả thành công như thế nào?
Bạn đánh giá khả năng tách lỗi broker connection, message converter và business handler trong dashboard như thế nào?
Bạn sẽ lựa chọn backpressure, rate limiting và load shedding khác nhau cho từng transport theo những giới hạn nào?
Bạn phân biệt unit test MessageConverter với integration test phải sử dụng kết nối JMS hoặc WebSocket thật như thế nào?
Bạn sẽ dùng MessageBuilder và fake MessageChannel để kiểm tra payload/header propagation trong unit test như thế nào?
Bạn sẽ kiểm thử ChannelInterceptor hủy một message có chủ đích mà không làm mất message hợp lệ như thế nào?
Bạn đánh giá cách chạy JMS integration test với Testcontainers và message schema khác phiên bản như thế nào?
Bạn sẽ sử dụng WebSocketStompClient và StompSessionHandler để kiểm thử SEND/SUBSCRIBE end-to-end ra sao?
Bạn phân tích cách kiểm thử @SendToUser chỉ gửi đúng user hoặc session và không lộ dữ liệu sang tenant khác như thế nào?
Bạn sẽ kiểm tra STOMP CONNECT từ origin không được phép bị từ chối trong một integration test như thế nào?
Bạn đánh giá khi nào cần test broker relay thật thay vì chỉ dùng Spring simple broker ra sao?
Bạn sẽ dùng StepVerifier kiểm tra RSocket requestResponse trả đúng payload hoặc error signal như thế nào?
Bạn sẽ test RSocket requestStream khi client cancel để xác minh giải phóng tài nguyên như thế nào?
Bạn phân tích cách đo concurrency và memory khi JMS consumers, STOMP sessions và RSocket streams đồng thời tăng tải như thế nào?
Bạn sẽ thiết kế contract test xác minh cùng event type có payload nhất quán trên ba transports ra sao?
Bạn đánh giá các tiêu chí nghiệm thu production về schema compatibility, security, tracing, retries và broker capacity như thế nào?
Nếu MessageChannel.send báo thành công nhưng handler bất đồng bộ thất bại, bạn sẽ xây dựng quy trình theo dõi lỗi ra sao?
Nếu ChannelInterceptor.preSend trả null làm message biến mất, bạn sẽ chẩn đoán chuỗi interceptors như thế nào?
Nếu cùng JSON payload lại mapping thành hai DTO khác nhau giữa JMS và STOMP, bạn sẽ kiểm tra converters ra sao?
Nếu @JmsListener nhận trùng business event sau broker restart, bạn sẽ bổ sung idempotency vào đâu?
Nếu một JMS message đã xử lý nhưng WebSocket client đang offline, bạn sẽ đồng bộ lại trạng thái UI như thế nào?
Nếu client SEND tới /topic thay vì /app, bạn sẽ kiểm tra broker prefixes và @MessageMapping ra sao?
Nếu notification tenant A tới subscriber tenant B, bạn sẽ kiểm tra destination authorization và Principal như thế nào?
Nếu simple broker chạy đúng một replica nhưng mất notification khi scale nhiều replicas, bạn sẽ đánh giá broker relay như thế nào?
Nếu @SendToUser gửi tới nhiều sessions ngoài ý muốn, bạn sẽ kiểm tra broadcast=false và session identity ra sao?
Nếu STOMP session còn mở nhưng broker relay mất kết nối, bạn sẽ tách trạng thái và tạo cảnh báo như thế nào?
Nếu outbound message buffer tăng do client đọc chậm, bạn sẽ đặt limits và điều chỉnh fan-out như thế nào?
Nếu RSocket requestStream bị cancel nhưng database query vẫn chạy, bạn sẽ truy tìm điểm đứt cancellation như thế nào?
Nếu retry RSocket fireAndForget khiến cập nhật bị thực hiện hai lần, bạn sẽ thiết kế deduplication theo business key ra sao?
Nếu RSocket requester và responder không thống nhất MIME type, bạn sẽ kiểm tra RSocketStrategies và setup metadata như thế nào?
Nếu một bản thay đổi message schema làm cả JMS và STOMP consumers bị lỗi, bạn sẽ lên kế hoạch rollback và contract tests ra sao?
Nếu trace giữa JMS consumer và WebSocket notification bị mất, bạn sẽ kiểm tra message headers và context propagation như thế nào?
Nếu cần thiết kế Spring Messaging end-to-end trên production, bạn sẽ phân chia Message/Channel/converter, JMS, WebSocket/STOMP, RSocket, bảo mật, quản lý lỗi và kiểm thử ra sao?
