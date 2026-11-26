Câu 1: Khi nào WebSocket phù hợp hơn việc liên tục gửi HTTP polling?
A. Khi cả client và server cần gửi dữ liệu thường xuyên
B. Khi ứng dụng đồng bộ dữ liệu bằng các lô lớn
C. Khi client chỉ cần đọc dữ liệu một lần theo yêu cầu
D. Khi server gửi kết quả định kỳ theo từng lần polling
Đáp án đúng: A

Câu 2: WebSocket hỗ trợ kiểu trao đổi dữ liệu nào sau khi kết nối được mở?
A. Client gửi yêu cầu rồi server trả một response
B. Mỗi message đi qua một request HTTP độc lập
C. Hai phía gửi message trên cùng kết nối
D. Server phát dữ liệu nhưng client chỉ được nhận
Đáp án đúng: C

Câu 3: Trong handshake WebSocket dùng HTTP/1.1, client thường yêu cầu điều gì?
A. Nâng cấp HTTP lên giao thức WebSocket
B. Giữ nguyên HTTP và chuyển sang long polling
C. Chuyển dữ liệu sang một HTTP response theo lô
D. Gửi yêu cầu CONNECT tới broker ở lớp ứng dụng
Đáp án đúng: A

Câu 4: Mã trạng thái nào thể hiện HTTP/1.1 WebSocket Upgrade thành công?
A. 202 Accepted cho một yêu cầu xử lý nền
B. 200 OK cho một phản hồi HTTP thông thường
C. 204 No Content cho một yêu cầu không có body
D. 101 Switching Protocols cho yêu cầu nâng cấp
Đáp án đúng: D

Câu 5: Header Sec-WebSocket-Accept trong phản hồi handshake có mục đích gì?
A. Xác nhận server đã xử lý khóa handshake hợp lệ
B. Khai báo thời gian hết hạn của kết nối WebSocket
C. Xác nhận danh tính người dùng đang đăng nhập
D. Chỉ ra phiên bản nén message đã được chọn
Đáp án đúng: A

Câu 6: Sự khác nhau cốt lõi giữa ws và wss là gì?
A. wss bảo vệ kết nối WebSocket bằng TLS
B. ws dùng TLS còn wss dùng mã hóa trong payload
C. wss bổ sung cơ chế phát lại message bị mất
D. ws cho gửi hai chiều còn wss chỉ cho nhận
Đáp án đúng: A

Câu 7: Sec-WebSocket-Protocol được dùng trong handshake nhằm mục đích gì?
A. Thương lượng timeout của TCP keepalive
B. Thương lượng thuật toán nén WebSocket frame
C. Thương lượng subprotocol ở tầng ứng dụng
D. Thương lượng cipher suite cho phiên TLS
Đáp án đúng: C

Câu 8: Khi nào nên chọn Server-Sent Events thay vì WebSocket?
A. Khi ứng dụng cần trao đổi binary frame hai chiều
B. Khi client chỉ nhận luồng cập nhật từ server
C. Khi client cần phát message tới nhiều room
D. Khi cả client và server cần gửi lệnh thường xuyên
Đáp án đúng: B

Câu 9: Điểm khác biệt giữa WebSocket frame và message là gì?
A. Message chỉ chứa tín hiệu điều khiển kết nối
B. Frame chỉ xuất hiện trong HTTP Upgrade ban đầu
C. Một message có thể chứa nhiều frame
D. Một frame có thể chứa nhiều message độc lập
Đáp án đúng: C

Câu 10: Khi gửi WebSocket text message, payload phải thỏa mãn yêu cầu nào?
A. Nội dung văn bản phải mã hóa bằng Base64
B. Nội dung phải có dạng JSON với trường type
C. Nội dung văn bản được biểu diễn bằng UTF-8 hợp lệ
D. Nội dung phải được đóng gói thành byte UTF-16
Đáp án đúng: C

Câu 11: WebSocket binary message thích hợp để truyền loại dữ liệu nào?
A. Dữ liệu byte cần giữ nguyên cấu trúc nhị phân
B. Nội dung JSON cần parser chuyển thành object
C. Các STOMP header cần thay thế frame dữ liệu
D. Các HTTP header cần gửi trong mỗi request
Đáp án đúng: A

Câu 12: Tại sao frame từ WebSocket client đến server cần được masking?
A. Để bảo đảm mỗi message được xử lý đúng một lần
B. Ngăn client tạo mẫu byte trên dây gây nhầm lẫn proxy
C. Để nén payload trước khi chuyển qua proxy HTTP
D. Để cung cấp mã hóa thay thế cho kết nối TLS
Đáp án đúng: B

Câu 13: Khi một message WebSocket bị phân mảnh, frame continuation dùng để làm gì?
A. Chỉ định một subprotocol mới cho session hiện tại
B. Mang payload tiếp theo của message đang mở
C. Đánh dấu một message mới không liên quan message trước
D. Xác nhận toàn bộ message đã lưu trong broker
Đáp án đúng: B

Câu 14: Ping frame trong WebSocket thường phục vụ mục đích nào?
A. Kiểm tra kết nối và yêu cầu phản hồi Pong
B. Xác nhận dữ liệu đã được ghi vào database
C. Thương lượng lại thông số của HTTP handshake
D. Gửi định danh người dùng để xác thực lại
Đáp án đúng: A

Câu 15: Khi nhận Ping frame hợp lệ, một endpoint WebSocket cần phản ứng thế nào?
A. Gửi Close để khởi tạo quy trình đóng session
B. Gửi Pong tương ứng theo quy tắc của giao thức
C. Gửi message Text để thay thế protocol control
D. Gửi một HTTP GET tới endpoint ping tương ứng
Đáp án đúng: B

Câu 16: Vai trò của Close control frame trong WebSocket là gì?
A. Thương lượng subprotocol mới trong cùng session
B. Yêu cầu server thực hiện lại handshake HTTP
C. Đánh dấu message nghiệp vụ đã được broker lưu
D. Tham gia thủ tục đóng kết nối có kiểm soát
Đáp án đúng: D

Câu 17: Close code 1000 thường mang ý nghĩa nào trong WebSocket?
A. Kết nối bị đóng do dữ liệu text sai định dạng
B. Kết nối được đóng bình thường theo giao thức
C. Kết nối bị đóng do server gặp lỗi nội bộ
D. Kết nối bị đóng do kích thước message quá lớn
Đáp án đúng: B

Câu 18: Phát biểu nào đúng về close code 1006 của WebSocket?
A. Mã được gửi trong Close frame khi client đóng bình thường
B. Mã được gửi trong Close frame khi payload nhị phân quá lớn
C. Mã được gửi trong Close frame khi server chủ động shutdown
D. Mã trạng thái dự phòng, không gửi trong Close frame
Đáp án đúng: D

Câu 19: Điều kiện nào đúng đối với WebSocket control frames?
A. Payload tối đa 256 byte và cần opcode riêng
B. Payload có thể phân mảnh cùng message văn bản
C. Payload tối đa 125 byte và không được phân mảnh
D. Payload không có giới hạn nếu gửi qua HTTP/2
Đáp án đúng: C

Câu 20: permessage-deflate trong WebSocket liên quan trực tiếp đến cơ chế nào?
A. Thương lượng cấu hình xác thực của WebSocket
B. Thương lượng cơ chế replay khi client kết nối lại
C. Thương lượng subprotocol cho các command STOMP
D. Thương lượng mở rộng để nén message
Đáp án đúng: D

Câu 21: Trong trình duyệt, WebSocket.readyState bằng OPEN cho biết điều gì?
A. Kết nối sẵn sàng gửi và nhận message
B. Client đang chờ HTTP handshake hoàn thành
C. Kết nối đã đóng và không thể mở lại
D. Kết nối đang thực hiện thủ tục đóng session
Đáp án đúng: A

Câu 22: Khi WebSocket còn CONNECTING, ứng dụng JavaScript nên làm gì trước khi gọi socket.send?
A. Gửi trước vì browser sẽ đệm tới khi handshake xong
B. Gọi send lặp lại tới khi kết nối chuyển trạng thái
C. Chờ readyState chuyển sang OPEN rồi mới gửi
D. Chuyển message vào phần body của HTTP handshake
Đáp án đúng: C

Câu 23: Thuộc tính bufferedAmount của WebSocket trên browser thể hiện điều gì?
A. Số lượng message server đã xác nhận xử lý
B. Lượng byte dữ liệu đã xếp hàng chờ truyền đi
C. Số frame Ping được gửi trong kết nối hiện tại
D. Lượng byte message đã nhận nhưng chưa được xử lý
Đáp án đúng: B

Câu 24: Khi component sở hữu riêng WebSocket và không còn cần kết nối, thao tác phù hợp là gì?
A. Tháo các handler rồi đóng socket của component
B. Xóa state giao diện nhưng vẫn giữ kết nối cũ
C. Giữ listener đến khi server gửi Close frame
D. Mở socket mới và chuyển listener sang kết nối đó
Đáp án đúng: A

Câu 25: Sau khi một WebSocket đã CLOSED, ứng dụng muốn kết nối lại thì làm gì?
A. Gửi Ping mới từ chính socket đã đóng
B. Tạo WebSocket mới và thực hiện handshake mới
C. Gọi send trên socket cũ để tái mở kết nối
D. Đổi thuộc tính readyState của socket cũ sang OPEN
Đáp án đúng: B

Câu 26: Với trình duyệt dùng WebSocket API gốc, cách nào phù hợp để theo dõi dữ liệu đến?
A. Lắng nghe sự kiện message bằng callback
B. Gửi lại HTTP GET sau mỗi frame nhận được
C. Đọc thuộc tính bufferedAmount liên tục
D. Đọc body của response bằng fetch stream
Đáp án đúng: A

Câu 27: Khi trình duyệt nhận message JSON không parse được, ứng dụng nên xử lý thế nào?
A. Bỏ qua lỗi parse và chuyển payload đến tầng nghiệp vụ
B. Gửi lại nguyên message lỗi như một yêu cầu HTTP mới
C. Bắt lỗi parse và loại bỏ dữ liệu không hợp lệ
D. Cho rằng dữ liệu đã xác thực khi handshake thành công
Đáp án đúng: C

Câu 28: Vì sao ứng dụng nên có heartbeat ở tầng ứng dụng trong một số kết nối WebSocket?
A. Phát hiện kết nối không còn sống dù chưa báo đóng
B. Để giải quyết thứ tự message giữa nhiều node
C. Để bảo đảm các message được lưu trữ bền vững
D. Để thay thế yêu cầu xác thực ở mỗi kết nối mới
Đáp án đúng: A

Câu 29: Trong Spring WebSocket không dùng STOMP, lớp nào thích hợp để xử lý text message?
A. BinaryWebSocketHandler xử lý thông điệp văn bản mặc định
B. SimpMessagingTemplate xử lý trực tiếp frame text raw
C. TextWebSocketHandler xử lý thông điệp văn bản
D. StompBrokerRelayMessageHandler nhận callback frame raw
Đáp án đúng: C

Câu 30: Trong cấu hình Spring WebSocket handler thuần, thao tác nào đăng ký endpoint URL?
A. Khai báo setApplicationDestinationPrefixes ở broker
B. Khai báo @MessageMapping trên HTTP controller
C. Gọi addHandler trong WebSocketHandlerRegistry
D. Gọi convertAndSend trên SimpMessagingTemplate
Đáp án đúng: C

Câu 31: Callback afterConnectionEstablished trong Spring WebSocket thường dùng để làm gì?
A. Giải mã payload của từng text message mới
B. Khởi tạo trạng thái khi một session đã kết nối
C. Dọn registry sau khi session đã đóng
D. Ánh xạ STOMP destination tới method Java
Đáp án đúng: B

Câu 32: Phương thức nào của TextWebSocketHandler dùng để tiếp nhận text message?
A. afterConnectionClosed với session và CloseStatus
B. handleTextMessage với session và TextMessage
C. supportsPartialMessages với session và TextMessage
D. afterConnectionEstablished với session và handshake
Đáp án đúng: B

Câu 33: Khi một session WebSocket đóng, server nên thực hiện công việc nào?
A. Giữ session trong registry để cho phép gửi lại
B. Khởi tạo session khác mà không cần handshake
C. Gỡ session khỏi registry và giải phóng tài nguyên
D. Chuyển toàn bộ message còn lại thành HTTP response
Đáp án đúng: C

Câu 34: HandshakeInterceptor trong Spring WebSocket thích hợp cho việc gì?
A. Phát ACK khi handler nhận message từ client
B. Xử lý tất cả message sau khi gửi tới STOMP broker
C. Kiểm tra handshake và đặt thuộc tính session
D. Đảm bảo replay lại các message bị client bỏ lỡ
Đáp án đúng: C

Câu 35: Trong Spring WebSocket, đối tượng nào đại diện cho một kết nối đang hoạt động?
A. WebSocketSession chứa trạng thái và thao tác gửi
B. CloseStatus quản lý session và thao tác gửi message
C. HandshakeInterceptor giữ phiên gửi nhận dữ liệu
D. TextMessage chứa trạng thái của phiên kết nối
Đáp án đúng: A

Câu 36: Khi nhiều luồng cùng gửi qua một WebSocketSession của Spring, thiết kế nào phù hợp?
A. Mỗi luồng mở một HTTP response trên cùng session
B. Gửi đồng thời vì WebSocketSession đã tuần tự hóa
C. Gửi từng frame qua các worker không đồng bộ hóa
D. Dùng decorator để điều phối gửi tuần tự
Đáp án đúng: D

Câu 37: Trong handler Spring WebSocket thuần, thao tác nào phát text message tới một session?
A. Gọi addHandler với một đối tượng TextMessage
B. Gọi getPrincipal với một đối tượng TextMessage
C. Gọi setAllowedOrigins với một đối tượng TextMessage
D. Gọi sendMessage với một đối tượng TextMessage
Đáp án đúng: D

Câu 38: Khác biệt giữa raw WebSocket handler và @MessageMapping của Spring là gì?
A. @MessageMapping xử lý trực tiếp binary WebSocket frame
B. @MessageMapping xử lý message theo mô hình messaging STOMP
C. Raw handler chỉ nhận dữ liệu khi đã SUBSCRIBE destination
D. Raw handler chỉ có thể gửi dữ liệu nếu dùng broker relay
Đáp án đúng: B

Câu 39: Lợi ích chính của STOMP trên WebSocket trong ứng dụng Spring là gì?
A. Cung cấp destination và lệnh messaging
B. Cung cấp mã hóa payload thay thế chứng chỉ TLS
C. Cung cấp xác nhận HTTP cho từng WebSocket frame
D. Quy định broker lưu message để replay khi reconnect
Đáp án đúng: A

Câu 40: Cặp STOMP frame nào thường bắt đầu quá trình thiết lập phiên STOMP?
A. Client gửi SUBSCRIBE và server trả ACK
B. Client gửi SEND và server trả MESSAGE
C. Client gửi DISCONNECT và server trả RECEIPT
D. Client gửi CONNECT và server trả CONNECTED
Đáp án đúng: D

Câu 41: STOMP SUBSCRIBE được dùng vào mục đích gì?
A. Gửi message tới một destination của ứng dụng
B. Đăng ký nhận message từ một destination
C. Yêu cầu ngắt toàn bộ session STOMP hiện tại
D. Xác nhận đã xử lý một message nhận trước đó
Đáp án đúng: B

Câu 42: STOMP SEND được dùng trong trường hợp nào?
A. Gửi message đến destination đã chỉ định
B. Ngắt kết nối sau khi hoàn tất subscription
C. Xác nhận một message nhận được qua subscription
D. Đăng ký nhận message từ một destination
Đáp án đúng: A

Câu 43: Khi /app được cấu hình làm application destination prefix trong Spring STOMP, message gửi tới /app được xử lý ở đâu?
A. HTTP controller xử lý như một request GET mới
B. Simple broker sẽ broadcast trực tiếp cho subscriber
C. Broker relay lưu giữ message để phát lại sau
D. Các application handler ánh xạ bởi @MessageMapping
Đáp án đúng: D

Câu 44: Với Spring simple broker cấu hình /topic, message gửi tới /topic thường được xử lý thế nào?
A. Session chỉ gửi message đến client đã phát nó
B. Message được coi là yêu cầu gọi một @MessageMapping
C. Controller ứng dụng phải phản hồi HTTP 200 tương ứng
D. Broker phân phối message đến subscriber phù hợp
Đáp án đúng: D

Câu 45: Annotation @MessageMapping trong Spring dùng để làm gì?
A. Ánh xạ địa chỉ HTTP handshake tới TCP socket
B. Ánh xạ destination ứng dụng tới phương thức xử lý
C. Ánh xạ quyền admin cho tất cả session STOMP
D. Ánh xạ chủ đề broker với quy tắc của SSLContext
Đáp án đúng: B

Câu 46: Annotation @SendTo có thể được dùng khi nào trong Spring STOMP?
A. Gửi giá trị trả về tới destination chỉ định
B. Thay thế yêu cầu kiểm tra quyền của session
C. Đánh dấu message được broker ghi bền vững sau khi gửi
D. Đăng ký subscription cho client trước khi gửi
Đáp án đúng: A

Câu 47: Khi cần gửi phản hồi riêng cho người dùng trong Spring STOMP, cơ chế nào phù hợp?
A. Sử dụng một destination chỉ chứa thông tin session
B. Sử dụng user destination với cơ chế @SendToUser
C. Sử dụng một destination trỏ tới endpoint HTTP GET
D. Sử dụng một topic chung không có kiểm tra quyền
Đáp án đúng: B

Câu 48: SimpMessagingTemplate trong Spring STOMP thường được dùng thế nào?
A. Chủ động gửi message tới destination từ mã server
B. Đổi phiên bản giao thức của HTTP handshake
C. Đăng ký subscription mới cho client ở destination
D. Cấu hình broker relay mỗi lần thực hiện lệnh gửi
Đáp án đúng: A

Câu 49: Spring STOMP simple broker có giới hạn chính nào khi mở rộng nhiều node?
A. Trạng thái subscription cục bộ khó chia sẻ giữa node
B. Subscription được lưu bền vững và tự replay giữa node
C. Đồng bộ message giữa các instance bằng simple broker
D. Dựa vào cookie để dùng chung subscription giữa node
Đáp án đúng: A

Câu 50: Lựa chọn nào thường phù hợp để mở rộng định tuyến STOMP qua nhiều node Spring?
A. Giữ subscription trong biến static của mỗi instance
B. Dùng handshake interceptor để thay broker chung
C. Chia WebSocket session theo topic bằng cookie trình duyệt
D. Dùng broker relay tới message broker có hỗ trợ STOMP
Đáp án đúng: D

Câu 51: Trong STOMP, chế độ ack client-individual hỗ trợ cơ chế nào?
A. Broker tự gửi ACK sau mỗi frame SEND
B. Broker đánh dấu message đã xử lý ngay khi CONNECT
C. Client xác nhận dồn toàn bộ message cùng subscription
D. Client xác nhận riêng từng message đã nhận
Đáp án đúng: D

Câu 52: STOMP heart-beat giữa client và server giúp kiểm tra điều gì?
A. Kiểm tra kết nối khi không có message nghiệp vụ
B. Độ tin cậy của việc ghi message vào bộ lưu broker
C. Kiểm tra quyền destination theo tín hiệu heartbeat
D. Khả năng tương thích của payload JSON giữa hai bên
Đáp án đúng: A

Câu 53: Trong STOMP, receipt header thường được dùng để làm gì?
A. Yêu cầu server phát lại bản tin theo receipt ID
B. Yêu cầu cấp thêm thời gian sống của cookie đăng nhập
C. Yêu cầu broker xác nhận đã xem message trên giao diện
D. Yêu cầu biên nhận khi server xử lý frame
Đáp án đúng: D

Câu 54: Trong ứng dụng Spring WebSocket, kiểm tra Origin khi handshake chủ yếu nhằm mục đích gì?
A. Kiểm chứng nội dung frame đã mã hóa qua TLS
B. Giới hạn những trang web được phép mở kết nối
C. Kiểm tra mỗi tài khoản thuộc phòng chat nào
D. Xác nhận message sẽ được lưu đúng một lần
Đáp án đúng: B

Câu 55: Điểm cần lưu ý khi áp dụng CORS cho WebSocket trên browser là gì?
A. CORS được sử dụng để xác thực broker STOMP
B. Browser gửi preflight OPTIONS trước WebSocket handshake
C. Kiểm tra Origin tại WebSocket handshake riêng biệt
D. CORS cho biết mỗi message thuộc tenant nào
Đáp án đúng: C

Câu 56: Khi WebSocket sử dụng cookie đăng nhập, biện pháp nào giúp giảm nguy cơ truy cập chéo origin?
A. Đặt tên topic theo user rồi tin vào định tuyến client
B. Kéo dài thời gian sống của cookie để tránh đổi phiên
C. Xác thực qua cookie rồi bỏ kiểm tra Origin tại handshake
D. Kiểm tra Origin cùng xác thực và phân quyền session
Đáp án đúng: D

Câu 57: Cách nào bảo vệ dữ liệu WebSocket khi truyền qua mạng Internet?
A. Dùng ws kết hợp đổi tên đường dẫn endpoint thường xuyên
B. Dùng frame masking thay cho cơ chế xác thực TLS
C. Dùng STOMP CONNECT thay việc mã hóa kết nối TLS
D. Dùng kết nối wss cùng TLS và chứng chỉ server hợp lệ
Đáp án đúng: D

Câu 58: Trong trình duyệt, WebSocket constructor gốc có giới hạn nào đáng chú ý với token?
A. Không cho đặt tùy ý HTTP Authorization header
B. Không hỗ trợ dùng cookie phiên trong HTTP handshake
C. Không hỗ trợ thương lượng subprotocol qua constructor
D. Không hỗ trợ truyền token tạm thời trong URL kết nối
Đáp án đúng: A

Câu 59: Khi người dùng kết nối được WebSocket nhưng gửi lệnh tới phòng không có quyền, server nên làm gì?
A. Kiểm tra quyền ở bước Close frame của session
B. Để client lọc room sau khi server broadcast message
C. Kiểm tra quyền ở message và từ chối lệnh trái phép
D. Dựa vào handshake và xử lý message mà không kiểm tra quyền
Đáp án đúng: C

Câu 60: Trong hệ thống nhiều tenant, việc định tuyến broadcast qua WebSocket cần tuân thủ điều gì?
A. Dựa vào tenant tự khai rồi gửi vào kênh dùng chung
B. Chỉ gửi tới session đã được cấp quyền thuộc đúng tenant
C. Dựa vào message ID thay cho kiểm tra tenant
D. Dựa riêng vào URL handshake để phân tách quyền
Đáp án đúng: B

Câu 61: Để giảm nguy cơ quá tải do client gửi nhiều message WebSocket, nên áp dụng cơ chế nào?
A. Tăng timeout nhận message ở tất cả session đang mở
B. Giới hạn tốc độ và kích thước message theo session
C. Tăng tần suất heartbeat nhằm theo dõi tải client
D. Giảm tần suất trả Pong khi client gửi quá nhanh
Đáp án đúng: B

Câu 62: Nếu ứng dụng hiển thị nội dung chat từ WebSocket, biện pháp nào giúp chống XSS?
A. Escape hoặc sanitize nội dung trước khi render ra DOM
B. Dựa vào Origin header để xác minh HTML an toàn
C. Dựa vào TLS để xác minh nội dung HTML an toàn
D. Chỉ giới hạn kích thước frame từ message broker
Đáp án đúng: A

Câu 63: Khi thiết kế reconnect cho WebSocket sau lỗi mạng, chiến lược nào phù hợp?
A. Đóng vĩnh viễn khả năng kết nối sau lỗi đầu tiên
B. Thực hiện retry liên tục không có giới hạn thời gian
C. Retry theo backoff lũy thừa có jitter
D. Giữ socket đã CLOSED và tiếp tục gọi send
Đáp án đúng: C

Câu 64: Nếu client mất kết nối và bỏ lỡ cập nhật quan trọng, cơ chế nào giúp đồng bộ lại?
A. Tạo session mới nhưng giữ nguyên dữ liệu đang hiển thị
B. Dùng Close frame để chuyển yêu cầu replay tới broker
C. Dựa vào session ID mới để suy ra các message còn thiếu
D. Dùng sequence hoặc cursor để lấy phần dữ liệu bị thiếu
Đáp án đúng: D

Câu 65: Khi client nhận lại một cập nhật đã xử lý sau reconnect, nên áp dụng cách nào?
A. Bỏ kiểm tra trùng nếu kết nối mới đã xác thực
B. Dedupe bằng event ID hoặc version nghiệp vụ
C. Áp dụng lại cập nhật theo thứ tự nhận mới nhất
D. Thay đổi destination để tránh sự kiện đã nhận
Đáp án đúng: B

Câu 66: Trong cụm WebSocket nhiều node, vì sao sticky session không đủ để phân phối message tới mọi client?
A. Sticky session sao chép registry khi client đổi node
B. Sticky session tự phát lại message sau reconnect
C. Session ở nhiều node vẫn cần kênh chia sẻ sự kiện
D. Sticky session tạo một hàng đợi message bền vững
Đáp án đúng: C

Câu 67: Giải pháp nào thường giúp nhiều node WebSocket cùng phát thông báo từ một nguồn?
A. Dùng HTTP Upgrade để replicate session sang node khác
B. Dùng cookie phiên để trực tiếp truyền message giữa node
C. Dùng broker pub-sub phân phối sự kiện giữa node
D. Dùng biến static cục bộ để chia sẻ message giữa node
Đáp án đúng: C

Câu 68: Để quản lý danh sách người dùng đang online qua nhiều node, nên kết hợp điều gì?
A. Trạng thái presence chỉ được cập nhật lúc HTTP GET
B. Trạng thái presence lưu vào header của từng message
C. Trạng thái presence chỉ lưu trong memory từng browser
D. Lưu trạng thái presence trong kho chia sẻ với TTL và heartbeat
Đáp án đúng: D

Câu 69: Khi client tiêu thụ quá chậm, cơ chế nào giảm rủi ro cạn bộ nhớ tại server?
A. Tăng tần suất Ping thay cho kiểm soát buffer
B. Tăng timeout nhưng giữ nguyên buffer không giới hạn
C. Giới hạn queue gửi và xử lý riêng client chậm
D. Mở rộng queue gửi không giới hạn cho từng client
Đáp án đúng: C

Câu 70: Về thứ tự các frame trong một kết nối WebSocket, phát biểu nào phù hợp?
A. Client reconnect sẽ nhận lại toàn bộ message cũ
B. Các frame được nhận theo thứ tự gửi trên cùng kết nối
C. Các node xử lý event theo thứ tự nhận chung của cụm
D. Broker duy trì thứ tự message qua các topic khác nhau
Đáp án đúng: B

Câu 71: Khi triển khai bản mới khiến nhiều kết nối WebSocket phải đóng, cách nào giảm gián đoạn?
A. Duy trì session cũ trong bộ nhớ của node đã dừng
B. Đóng đồng loạt rồi retry không có backoff
C. Đóng có kiểm soát và cho client reconnect có backoff
D. Đợi client tự phát hiện lỗi rồi ngừng reconnect
Đáp án đúng: C

Câu 72: Khi kiểm thử WebSocket handshake dùng HTTP/1.1, thao tác nào xác nhận nâng cấp thành công?
A. Kiểm tra broker có lưu được message từ console
B. Kiểm tra database trả về đúng số bản ghi hiện có
C. Thử kết nối, kiểm tra HTTP 101 và header Upgrade
D. Kiểm tra server có trả dữ liệu từ HTTP GET không Upgrade
Đáp án đúng: C

Câu 73: Khi kiểm thử frame WebSocket bị phân mảnh, cần xác nhận điều gì?
A. Client tự đổi subprotocol sau mỗi continuation frame
B. Server tái hợp payload thành message đúng thứ tự
C. Server xử lý từng continuation frame thành một message
D. Client thực hiện một HTTP handshake cho mỗi fragment
Đáp án đúng: B

Câu 74: Trong kiểm thử STOMP phân quyền, tình huống nào cần xác minh trực tiếp?
A. Đánh giá latency của SUBSCRIBE sau khi mở WebSocket
B. Kiểm tra token tại handshake thay cho quyền SEND
C. Chấp nhận quyền theo room do client khai báo
D. User không được quyền bị từ chối SEND hoặc SUBSCRIBE
Đáp án đúng: D

Câu 75: Kịch bản kiểm thử nào cho thấy reconnect và khôi phục dữ liệu hoạt động đúng?
A. Tăng số Ping frame trong một kết nối khỏe mạnh
B. Đóng tab rồi mở lại khi không có dữ liệu nào đổi
C. Gửi nhiều message khi mạng ổn định, không ngắt
D. Ngắt mạng, kiểm tra client đồng bộ cập nhật bỏ lỡ
Đáp án đúng: D

Câu 76: Khi đánh giá hiệu năng WebSocket, bộ chỉ số nào sát với năng lực thời gian thực?
A. CPU trung bình, bộ nhớ heap và thời gian khởi động
B. Số kết nối, độ trễ message và lượt reconnect
C. Số HTTP request, tải CPU và tổng dung lượng bộ nhớ
D. Tổng request thành công, uptime và lịch triển khai
Đáp án đúng: B

Câu 77: Khi kiểm thử khả năng chịu tải của WebSocket server, kịch bản nào có giá trị nhất?
A. Đo riêng tải CPU server khi chưa phát message
B. Đo nhiều handshake nhưng không duy trì kết nối
C. Kết hợp nhiều kết nối mở với lưu lượng message thực tế
D. Đo tải broker khi chưa có kết nối WebSocket
Đáp án đúng: C

Câu 78: Để chẩn đoán mất thông điệp sau khi deploy nhiều node, thông tin nào hữu ích nhất?
A. Correlation ID cùng log phát, định tuyến và nhận message
B. Thống kê throughput tổng cộng và thời gian DB query
C. Tổng số lần reconnect và timeout ở load balancer
D. Tổng số session đang mở trên các node của cụm
Đáp án đúng: A

Câu 79: Khi một node WebSocket bị mất kết nối với broker, hành vi nào tăng độ tin cậy?
A. Gửi message như cũ và bỏ qua kết quả từ broker relay
B. Gửi Close frame thay cho message chưa chuyển qua broker
C. Xác nhận thành công toàn bộ message dù chưa được chuyển
D. Phát hiện lỗi, giới hạn gửi và khôi phục kết nối
Đáp án đúng: D
