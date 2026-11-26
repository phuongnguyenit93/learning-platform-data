Câu 1. Trong Reactor Netty, event loop chủ yếu làm gì khi có nhiều kết nối?
A. Tự lưu mọi request vào queue bền vững trước khi xử lý.
B. Theo dõi I/O readiness và xử lý nhiều kết nối không chặn.
C. Tạo một luồng Java mới cho từng socket khi nhận dữ liệu.
D. Tự chuyển mọi truy vấn database qua một thread pool.
Đáp án đúng: B

Câu 2. Handler chạy trên event loop cần gọi JDBC blocking. Cách làm nào phù hợp?
A. Chuyển lời gọi chặn sang scheduler như `boundedElastic`.
B. Giữ lời gọi JDBC trên event loop và tăng timeout.
C. Thêm `.map()` quanh JDBC để lời gọi tự thành nonblocking.
D. Đổi tên thread hiện tại để tách nó khỏi event loop.
Đáp án đúng: A

Câu 3. Trong Reactor Netty, `HttpServer.bindNow()` thường làm gì?
A. Tạo publisher chờ subscribe mới bắt đầu mở socket.
B. Bind socket và trả `DisposableServer` khi thành công.
C. Trả một `Mono<HttpServer>` chưa thực hiện lệnh bind.
D. Khởi tạo HTTP client pool trước khi gửi request đầu.
Đáp án đúng: B

Câu 4. Khi dùng `HttpClient.responseSingle(...)`, callback nhận tham số nào?
A. `HttpServerRequest` và `HttpServerResponse` của server.
B. `HttpClientResponse` và `ByteBufMono` để xử lý body.
C. `NettyOutbound` và `UdpInbound` của UDP server.
D. `ConnectionProvider` và `Connection` từ pool.
Đáp án đúng: B

Câu 5. `HttpClient.responseTimeout(...)` của Reactor Netty giới hạn điều gì?
A. Thời gian sống tối đa của connection khi nhàn rỗi.
B. Thời gian thiết lập socket TCP trước khi gửi HTTP.
C. Thời gian chờ các thao tác đọc trong HTTP response.
D. Thời gian xếp hàng để lấy connection từ pool.
Đáp án đúng: C

Câu 6. Thiết lập nào dành cho timeout mở kết nối TCP mới trong Reactor Netty?
A. Dùng `ChannelOption.CONNECT_TIMEOUT_MILLIS`.
B. `HttpClient.wiretap(true)` của network logger.
C. `HttpClient.responseTimeout(...)` của response.
D. `ConnectionProvider.maxIdleTime(...)` của pool.
Đáp án đúng: A

Câu 7. Trong `ConnectionProvider`, `pendingAcquireTimeout` điều khiển gì?
A. Thời gian server chờ datagram đầu tiên sau khi bind.
B. Thời gian chờ lấy kết nối khả dụng từ connection pool.
C. Thời gian đọc response sau khi gửi xong HTTP request.
D. Thời gian kết nối nhàn rỗi trước khi được đánh giá loại.
Đáp án đúng: B

Câu 8. Thiết lập `maxConnections` cho pool Reactor Netty có tác dụng nào?
A. Giới hạn số phần tử một subscriber được nhận.
B. Giới hạn số payload tối đa trong một HTTP body.
C. Giới hạn số lần retry của mỗi HTTP request.
D. Giới hạn số kết nối tối đa trong connection pool.
Đáp án đúng: D

Câu 9. Với `ConnectionProvider.maxIdleTime`, cách hiểu nào chính xác hơn?
A. Đặt timeout cho subscriber chưa gửi tín hiệu demand.
B. Đặt thời gian tối đa server xử lý mỗi HTTP request.
C. Ngưỡng idle để pool cân nhắc loại kết nối.
D. Đặt thời gian cho bước DNS và TLS handshake.
Đáp án đúng: C

Câu 10. Khi gọi `DisposableServer.disposeNow()`, mục tiêu chính là gì?
A. Giải phóng mọi pool kết nối của toàn bộ JVM.
B. Hủy một luồng reactive nhưng giữ server hoạt động.
C. Ngắt một request HTTP nhưng tiếp tục lắng nghe socket.
D. Yêu cầu dừng server và chờ quá trình dispose hoàn tất.
Đáp án đúng: D

Câu 11. `HttpClient.create(connectionProvider)` sử dụng tham số để làm gì?
A. Tạo một socket UDP dùng pool của HTTP connection.
B. Khởi tạo client với `ConnectionProvider` đã chỉ định.
C. Tạo HTTP server nhận kết nối từ pool phía client.
D. Tạo scheduler riêng cho mọi truy vấn database blocking.
Đáp án đúng: B

Câu 12. Với publisher lạnh trả từ HTTP client, khi nào request thường bắt đầu?
A. Ngay lúc tạo `HttpClient` dù chưa khai báo request.
B. Khi publisher nhận được một subscription.
C. Ngay lúc gọi `.uri(...)` dù chưa ai subscribe.
D. Khi server gọi flush cho một HTTP response khác.
Đáp án đúng: B

Câu 13. Subscribe hai lần vào publisher HTTP lạnh chưa cache/share có thể gây gì?
A. Có thể thực hiện hai lượt HTTP exchange độc lập.
B. Luôn dùng chung một response đã cache của client.
C. Chỉ tăng demand mà không thể gửi request lần nữa.
D. Lần subscribe thứ hai luôn lỗi vì stream ID trùng.
Đáp án đúng: A

Câu 14. Downstream hủy subscription đang nhận HTTP body. Điều gì có thể xảy ra?
A. Server bắt buộc phát xong body trước khi client hủy.
B. Client tự động retry request khi nhận tín hiệu cancel.
C. Subscription được biến thành một kết nối HTTP mới.
D. Việc tiêu thụ dừng và tài nguyên I/O được hủy theo.
Đáp án đúng: D

Câu 15. Trong Reactive Streams, `request(n)` diễn tả điều gì?
A. Broker chuyển n datagram vào queue đang nhận.
B. Pool được tạo thêm tối đa n connection TCP mới.
C. Mỗi phần tử được gửi phải có ít nhất n byte.
D. Subscriber cho biết nhu cầu nhận tối đa n phần tử nữa.
Đáp án đúng: D

Câu 16. TCP cung cấp bảo đảm nào cho dữ liệu trên một kết nối còn hoạt động?
A. Không thể ngắt kết nối khi đang truyền nhiều byte.
B. Giữ từng ranh giới datagram độc lập như giao thức UDP.
C. Truyền luồng byte có thứ tự trong một kết nối.
D. Không thể nghẽn do bên nhận chậm đọc dữ liệu.
Đáp án đúng: C

Câu 17. Khi dùng UDP trong Reactor Netty, điều nào cần tính đến?
A. Datagram luôn được xác nhận và retry như TCP.
B. Datagram tự trở thành luồng byte có thứ tự.
C. Datagram chỉ được gửi qua một HTTP/2 connection.
D. Datagram có thể mất, trùng hoặc đảo thứ tự.
Đáp án đúng: D

Câu 18. `TcpServer` trong Reactor Netty phù hợp với nhiệm vụ nào?
A. Tạo WebSocket endpoint và quản lý HTTP route.
B. Bind TCP socket để gửi và nhận dữ liệu.
C. Phân phối datagram UDP giữa các queue cùng cổng.
D. Khởi tạo HTTP response có content type mặc định.
Đáp án đúng: B

Câu 19. `UdpServer` trong Reactor Netty cung cấp khả năng nào?
A. Tạo HTTP endpoint với routing dựa theo URL path.
B. Duy trì luồng byte có thứ tự như một socket TCP.
C. Bind cổng UDP để nhận các datagram.
D. Tạo kết nối TCP mới cho mỗi message nhận được.
Đáp án đúng: C

Câu 20. Với Netty `ByteBuf` có reference count, điều gì cần lưu ý?
A. Xem buffer như immutable value được Java GC thu hồi ngay.
B. Gọi `retain()` sau mỗi lần đọc dù không giữ buffer.
C. Quản lý vòng đời tham chiếu khi giữ buffer qua callback.
D. Dựa vào GC để giải phóng mọi vùng direct memory.
Đáp án đúng: C

Câu 21. Muốn giữ chính `ByteBuf` sau callback đang sở hữu nó, nên làm gì?
A. Chỉ lưu buffer vào collection để JVM tự thu hồi.
B. Đóng cả server sau mỗi lần sử dụng buffer này.
C. Giữ nguyên tham chiếu mà không tăng reference count.
D. Dùng `retain()` để giữ và `release()` khi xong.
Đáp án đúng: D

Câu 22. Quên `release()` cho nhiều `ByteBuf` đã retain có thể gây hậu quả nào?
A. Tự kích hoạt retry HTTP trong mọi channel đang mở.
B. Tự đặt timeout mới cho các subscriber chậm.
C. Tự bật connection pool cho mọi client đang dùng.
D. Rò rỉ vùng nhớ buffer và tăng áp lực tài nguyên.
Đáp án đúng: D

Câu 23. Để cấu hình TLS cho Reactor Netty client/server, cách nào phù hợp?
A. Dùng `.secure(...)` cùng cấu hình SSL/TLS phù hợp.
B. Dùng `.responseTimeout(...)` thay cho TLS handshake.
C. Dùng `.maxConnections(...)` để xác minh chứng chỉ.
D. Dùng `.wiretap(...)` để mã hóa nội dung HTTP.
Đáp án đúng: A

Câu 24. Đối với HTTPS client, bước nào hỗ trợ xác thực đúng server?
A. Chấp nhận mọi chứng chỉ nếu socket TLS đã mở.
B. Mã hóa body thành base64 trước khi gửi request.
C. Kiểm tra trust chain và hostname của server.
D. Chỉ kiểm tra response có HTTP status thành công.
Đáp án đúng: C

Câu 25. Khi bật HTTP/2, multiplexing cho phép thực hiện điều gì?
A. Mọi HTTP stream phải chờ stream trước kết thúc.
B. Nhiều HTTP stream độc lập dùng chung một kết nối.
C. Mỗi HTTP request buộc phải dùng một TCP socket riêng.
D. Mọi response phải hoàn tất đúng thứ tự request.
Đáp án đúng: B

Câu 26. Trong Reactor Netty, `wiretap(true)` thường dùng để làm gì?
A. Chia traffic HTTP giữa nhiều pool khác nhau.
B. Tự retry request khi server trả về HTTP 5xx.
C. Ghi log I/O khi mức logging phù hợp.
D. Mã hóa toàn bộ traffic TCP trước khi truyền.
Đáp án đúng: C

Câu 27. Khi theo dõi pool HTTP client, bộ chỉ số nào hữu ích?
A. Theo dõi pool pending, active và response latency.
B. Số dòng code, số class và tên HTTP handler.
C. Số endpoint, phiên bản package và thời gian build.
D. Số thread khởi tạo mà không đo thời gian chờ.
Đáp án đúng: A

Câu 28. Trong kiểm thử reactive, tích hợp BlockHound giúp phát hiện điều gì?
A. Phát hiện blocking call trên nonblocking thread.
B. Kích thước ByteBuf khi ghi log I/O thành công.
C. Lỗi DNS do thay đổi hostname trong cấu hình TLS.
D. Thứ tự HTTP response trong một test đơn luồng.
Đáp án đúng: A

Câu 29. Một tác vụ CPU nặng xuất hiện trong handler Netty. Cách xử lý nào phù hợp?
A. Chạy trong event loop và tăng tối đa kích thước buffer.
B. Tắt backpressure để CPU được gửi thêm nhiều dữ liệu.
C. Đẩy tác vụ CPU sang `Schedulers.parallel()`.
D. Chuyển tất cả tác vụ CPU sang thread pool blocking I/O.
Đáp án đúng: C

Câu 30. Spring WebFlux dùng Reactor Netty làm HTTP server sẽ xử lý I/O chủ yếu thế nào?
A. Dùng event loop xử lý I/O HTTP không chặn.
B. Chuyển mọi request qua JMS queue rồi mới phản hồi.
C. Tạo một thread mới riêng cho mỗi HTTP request đến.
D. Buộc mọi controller phải chạy theo servlet blocking.
Đáp án đúng: A

Câu 31. Với HTTP/1.1 client có connection pool, xử lý body thế nào giúp tái sử dụng?
A. Đọc hoặc bỏ body đúng cách trước khi tái sử dụng.
B. Luôn bỏ qua lỗi response để pool tự thu hồi ngay.
C. Subscribe lần hai để đóng socket của request trước.
D. Không đọc body nhưng giữ kết nối bận vô thời hạn.
Đáp án đúng: A

Câu 32. Khi load test Reactor Netty, bộ phép đo nào cho cái nhìn tổng thể hơn?
A. Chỉ throughput trong một lần thử không có tải.
B. Chỉ p50 latency và bỏ qua pool đang chờ kết nối.
C. Chỉ CPU mà không theo dõi lỗi hay độ trễ request.
D. Theo dõi throughput, p95/p99, pool pending và lỗi.
Đáp án đúng: D
