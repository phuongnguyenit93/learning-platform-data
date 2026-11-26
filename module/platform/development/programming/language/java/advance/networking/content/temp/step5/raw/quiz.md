Câu 1. InetAddress.getAllByName("example.org") thường trả về điều gì?
A. Một Socket đã kết nối tới cổng mặc định của host
B. Các địa chỉ IP được resolver tìm thấy cho hostname
C. Một danh sách URI bao gồm path và query của host
D. Chứng chỉ TLS của host trong DNS response
Đáp án đúng: B

Câu 2. Tại sao ứng dụng Java không nên giả định DNS lookup luôn lấy dữ liệu mới?
A. InetAddress luôn bỏ cache nhưng hệ điều hành giữ nguyên IP
B. Kết quả phân giải tên có thể được JVM hoặc resolver cache
C. DNS chỉ đổi IP khi máy chủ Java được khởi động lại
D. Mọi hostname chỉ ánh xạ một IPv4 trong suốt vòng đời
Đáp án đúng: B

Câu 3. InetSocketAddress.createUnresolved(host, port) hữu ích trong trường hợp nào?
A. Mở kết nối TCP tới host mà không cần gọi connect
B. Bỏ qua kiểm tra cổng hợp lệ cho SocketChannel
C. Tạo địa chỉ có hostname chưa được resolve
D. Đổi host thành IP loopback trước khi mở socket
Đáp án đúng: C

Câu 4. Khi chỉ muốn phân tích cú pháp tham chiếu tài nguyên, nên ưu tiên gì?
A. Dùng URI để xử lý cấu trúc mà không mở kết nối mạng
B. Dùng URL.openStream để tách path mà không phát sinh I/O
C. Dùng Socket.connect để phân tích query string của URI
D. Dùng HttpClient.send để tách fragment của địa chỉ
Đáp án đúng: A

Câu 5. URI.resolve(relativeUri) chủ yếu giúp xử lý việc gì?
A. Phân giải hostname thành địa chỉ IP trước khi chạy client
B. Ghép tham chiếu tương đối với URI cơ sở theo quy tắc URI
C. Tự thực hiện HTTP redirect sau khi nhận response 3xx
D. Tự mã hóa mọi ký tự Unicode thành UTF-8 trong path
Đáp án đúng: B

Câu 6. URLEncoder.encode(value, UTF_8) thích hợp nhất trong ngữ cảnh nào?
A. Mã hóa giá trị theo quy tắc HTML form URL encoding
B. Mã hóa toàn bộ URL đã có scheme, authority và fragment
C. Mã hóa byte của TCP payload trước khi gửi qua socket
D. Mã hóa tên host để DNS trả về chứng chỉ hợp lệ
Đáp án đúng: A

Câu 7. Khi đọc dữ liệu từ TCP InputStream, điều nào đúng về message boundary?
A. Mỗi lần read luôn tương ứng đúng một lần write phía gửi
B. Mỗi TCP packet luôn chứa trọn một message cấp ứng dụng
C. TCP là luồng byte; ứng dụng phải tự định khung message
D. InputStream tự phân tách các message theo ký tự newline
Đáp án đúng: C

Câu 8. ServerSocket.accept() ở chế độ blocking thường có hành vi nào?
A. Trả DatagramPacket chứa payload đầu tiên từ client
B. Chờ một kết nối tới và trả Socket cho kết nối đó
C. Hoàn tất TLS handshake của tất cả client trước khi trả về
D. Trả null ngay nếu chưa có client dù không cấu hình timeout
Đáp án đúng: B

Câu 9. Khi gọi Socket.connect(endpoint, timeout), timeout kiểm soát bước nào?
A. Giới hạn thời gian chờ mỗi lần đọc từ InputStream
B. Giới hạn thời gian idle của kết nối đã thành lập
C. Giới hạn tổng thời gian xử lý mỗi request ứng dụng
D. Giới hạn thời gian chờ thiết lập kết nối tới endpoint
Đáp án đúng: D

Câu 10. Socket.setSoTimeout(2000) chủ yếu ảnh hưởng tới thao tác nào?
A. Một lần write luôn phải hoàn tất trong đúng hai giây
B. Một lần đọc blocking có thể ném SocketTimeoutException
C. Thời gian connect bị giới hạn dù chưa gọi connect(timeout)
D. JVM sẽ đóng Socket ngay sau hai giây kể từ lúc tạo
Đáp án đúng: B

Câu 11. Sau Socket.shutdownOutput(), bên gọi vẫn có thể làm gì nếu kết nối còn phù hợp?
A. Gửi tiếp bytes qua output stream như trước đó
B. Vẫn có thể đọc input sau khi ngừng gửi dữ liệu
C. Tự khôi phục output để ghi bằng chính socket đó
D. Tạo một cổng TCP server mới từ socket hiện tại
Đáp án đúng: B

Câu 12. Khi Socket InputStream.read() trả -1 sau khi hết bytes đệm, điều này thường chỉ ra gì?
A. Không có bytes sẵn ngay lúc này nhưng socket vẫn mở
B. Socket timeout dù không có exception được ném
C. Đầu kia đã đóng chiều gửi và stream chạm EOF
D. TCP vừa nhận gói rỗng biểu thị một message hợp lệ
Đáp án đúng: C

Câu 13. Với SocketChannel ở chế độ non-blocking, write(buffer) có thể trả gì?
A. Số byte luôn bằng remaining nếu channel chưa đóng
B. Số lượng message TCP đã được gửi trọn tới peer
C. write() có thể ghi ít hơn buffer.remaining()
D. Số frame TLS đã được máy nhận xác minh
Đáp án đúng: C

Câu 14. DataInputStream.readFully(bytes) có tác dụng gì khi đọc frame cố định?
A. Trả ngay với số byte đang có mà không cần đọc tiếp
B. Dừng tự động tại ranh giới TCP segment từ peer
C. Chỉ chờ tới newline rồi trả mọi byte trước newline
D. Đọc đủ số byte yêu cầu hoặc báo EOFException nếu thiếu
Đáp án đúng: D

Câu 15. Với giao thức độ dài-tiền-tố trên TCP, quy tắc nào quan trọng để tránh cấp phát nguy hiểm?
A. Tin giá trị length từ client vì TCP bảo đảm toàn vẹn message
B. Giới hạn và kiểm tra độ dài frame trước khi cấp buffer
C. Đọc tới EOF trước khi xem prefix chỉ độ dài
D. Dùng Socket.setSoTimeout để tự giới hạn kích thước frame
Đáp án đúng: B

Câu 16. SO_KEEPALIVE của TCP không nên được hiểu nhầm thành điều gì?
A. Cơ chế heartbeat và deadline nghiệp vụ có bảo đảm tức thời
B. Cơ chế thăm dò kết nối idle do TCP stack điều khiển
C. Một socket option thường cấu hình được trên TCP Socket
D. Một tính năng giúp phát hiện vài kết nối chết sau một thời gian
Đáp án đúng: A

Câu 17. Gửi UDP datagram đến peer có bảo đảm nào về việc nhận không?
A. Không bảo đảm nhận, đúng thứ tự hoặc không trùng
B. Bảo đảm mỗi gói được nhận một lần nếu socket còn mở
C. Bảo đảm retransmit theo sequence number của TCP
D. Bảo đảm gửi theo thứ tự nếu không gọi flush
Đáp án đúng: A

Câu 18. Khi nhận UDP bằng DatagramPacket với buffer cấp sẵn, dùng gì để biết bytes hợp lệ?
A. Đọc getPort() để suy ra độ dài nội dung được nhận
B. Đọc getAddress() để tính số bytes của datagram
C. Dùng getLength() lấy số byte datagram vừa nhận
D. Dùng available() của TCP InputStream để biết kích thước
Đáp án đúng: C

Câu 19. DatagramSocket.setSoTimeout tác động thế nào tới receive() blocking?
A. Tự đổi DatagramSocket thành SocketChannel non-blocking
B. Bảo đảm datagram đến đúng hạn mà không mất gói
C. Bỏ giới hạn kích thước UDP packet ở phía nhận
D. receive() có thể ném SocketTimeoutException
Đáp án đúng: D

Câu 20. Với NIO DatagramChannel, để nhận IPv4 multicast qua interface cụ thể thường cần gì?
A. Gọi ServerSocket.accept để nhận multicast connection
B. Đăng ký OP_ACCEPT trên DatagramChannel đã bind
C. Gọi Socket.shutdownOutput trước khi join group
D. Join multicast group với NetworkInterface thích hợp
Đáp án đúng: D

Câu 21. Tại sao nên hạn chế UDP datagram lớn trên đường mạng không kiểm soát?
A. IP fragmentation có thể làm giảm khả năng nhận trọn gói
B. UDP tự đảm bảo phân mảnh được truyền lại khi mất mảnh
C. UDP datagram lớn mặc định chuyển thành TCP stream
D. DatagramSocket tự chia gói lớn thành message đáng tin cậy
Đáp án đúng: A

Câu 22. Sau khi ghi dữ liệu vào ByteBuffer, flip() chuẩn bị buffer thế nào để đọc?
A. Đặt limit thành capacity và giữ position cuối cùng
B. Xóa nội dung bytes đã ghi và reset toàn bộ về 0
C. Đặt limit theo position cũ rồi đưa position về 0
D. Chuyển byte order về BIG_ENDIAN rồi bắt đầu đọc
Đáp án đúng: C

Câu 23. Khi ByteBuffer còn bytes chưa đọc và cần ghi thêm dữ liệu mạng, dùng gì?
A. clear() giữ bytes chưa đọc ở đầu và tự tăng position
B. compact() giữ bytes chưa đọc để ghi tiếp
C. flip() giữ bytes chưa đọc và tự nối thêm bytes mới
D. rewind() dồn bytes còn lại vào phần đầu buffer
Đáp án đúng: B

Câu 24. ByteBuffer.clear() có ý nghĩa chính nào?
A. Ghi zero lên toàn bộ byte array của backing buffer
B. Đọc tất cả bytes còn lại để release TCP stream
C. Tự chuyển sang read-only buffer để tránh sửa nhầm
D. Reset position/limit mà không xóa bytes
Đáp án đúng: D

Câu 25. Trước khi đăng ký SocketChannel với Selector, yêu cầu thường gặp là gì?
A. Đặt configureBlocking(false) trước khi register
B. Đặt channel ở blocking mode để select báo readiness
C. Bật Socket.setSoTimeout cho từng SelectionKey
D. Đóng channel rồi đăng ký lại dưới tên interestOps
Đáp án đúng: A

Câu 26. Với ServerSocketChannel, SelectionKey.OP_ACCEPT biểu thị sự kiện nào?
A. Server channel sẵn sàng accept một kết nối đến
B. Client channel đã đọc xong toàn bộ frame ứng dụng
C. SocketChannel đã nhận response HTTP hoàn chỉnh
D. DatagramChannel đã kết thúc gửi một UDP message
Đáp án đúng: A

Câu 27. Một SelectionKey.isReadable() không chứng minh điều gì?
A. Channel có thể thử thao tác đọc mà không chặn lâu
B. Interest và ready operation có thể khác nhau
C. Không xác nhận đã có đủ byte của toàn bộ frame
D. Đọc từ channel vẫn có thể trả số byte hạn chế
Đáp án đúng: C

Câu 28. Sau khi xử lý SelectionKey từ selector.selectedKeys(), thao tác nào nên làm?
A. Để key trong selected set để JVM tự xóa sau mỗi select
B. Gọi selector.close() sau khi xử lý mỗi socket đọc được
C. Thêm key vào selected set một lần nữa để báo hoàn tất
D. Loại key đã xử lý khỏi selectedKeys bằng iterator
Đáp án đúng: D

Câu 29. Khi luôn đăng ký OP_WRITE dù không còn dữ liệu gửi, vấn đề nào dễ xảy ra?
A. SocketChannel sẽ tự đóng output khi thấy OP_WRITE
B. Selector sẽ chỉ báo OP_WRITE sau khi peer xác nhận frame
C. OP_WRITE chỉ kích hoạt lúc dữ liệu ứng dụng bị mất
D. Có thể liên tục báo readiness ghi khi hết data gửi
Đáp án đúng: D

Câu 30. Ở chế độ non-blocking, SocketChannel.read(buffer) trả 0 thường có nghĩa gì?
A. Peer đã đóng chiều gửi nên channel ở EOF
B. Socket đã hết thời hạn keepalive và bị đóng
C. Lượt read hiện tại không lấy được byte nào
D. JVM đã hoàn thành một message độ dài bằng 0
Đáp án đúng: C

Câu 31. Khi giải mã UTF-8 từ nhiều lượt SocketChannel.read, nên tránh cách nào?
A. Giữ bytes chưa hoàn chỉnh cho lần decode sau khi cần
B. Dùng CharsetDecoder để theo dõi trạng thái giải mã
C. Đặt giới hạn frame trước khi chuyển bytes thành String
D. Không giải mã độc lập chunk có ký tự UTF-8 bị chia
Đáp án đúng: D

Câu 32. AsynchronousSocketChannel.read thường trả kết quả qua cơ chế nào?
A. Future hoặc CompletionHandler trả kết quả async
B. SelectionKey.OP_ACCEPT mà không cần ServerSocketChannel
C. Một DatagramPacket chứa bytes của TCP stream
D. JVM gọi main lần nữa khi I/O đã hoàn thành
Đáp án đúng: A

Câu 33. SSLContext trong Java TLS thường được dùng cho vai trò gì?
A. Định nghĩa hostname DNS và port của TCP peer
B. Chuyển HTTP request thành SOAP XML envelope
C. Tự kiểm tra frame length của TCP application protocol
D. Khởi tạo ngữ cảnh TLS với key/trust managers phù hợp
Đáp án đúng: D

Câu 34. Trong cấu hình TLS Java, truststore thường phục vụ công việc nào?
A. Chứa mọi session token do SocketChannel phát hành
B. Chứa frame ứng dụng chưa được gửi qua SSLEngine
C. Chứa toàn bộ HTTP cookie thay cho CookieManager
D. Trust anchors dùng xác minh chứng chỉ của peer
Đáp án đúng: D

Câu 35. Với raw SSLSocket client, vì sao cần cấu hình endpoint identification phù hợp?
A. Để tắt việc kiểm tra CA nhưng vẫn coi TLS đáng tin
B. Để kiểm tra hostname peer ngoài certificate chain
C. Để SSLSocket tự đổi thành HTTPS proxy ở cấp HTTP
D. Để xác định IP của client khi server cấp session ID
Đáp án đúng: B

Câu 36. SSLEngine trong NIO TLS xử lý dữ liệu mạng chủ yếu qua thao tác nào?
A. Dùng wrap/unwrap và quản lý trạng thái TLS handshake
B. readFully/writeUTF với DataInputStream mặc định
C. accept/connect qua ServerSocket rồi bỏ qua TLS record
D. encode/decode URI rồi gửi thẳng vào SelectableChannel
Đáp án đúng: A

Câu 37. Một TLS handshake fail do chứng chỉ hết hạn nên được xử lý thế nào?
A. Tạm bỏ xác minh certificate cho mọi peer để hoàn tất
B. Từ chối kết nối và xử lý lỗi tin cậy thay vì bỏ xác minh
C. Tự ký certificate mới trên client rồi tin ngay peer
D. Đổi sang TCP plain socket để tránh lỗi SSLHandshake
Đáp án đúng: B

Câu 38. Khi cấu hình phiên bản TLS, hướng nào phù hợp với ứng dụng mới?
A. Bật SSLv3 để tối đa khả năng tương thích với peer
B. Vô hiệu hostname verification khi dùng TLS 1.3
C. Bỏ kiểm tra chứng chỉ khi client dùng HTTPS URL
D. Chọn TLS protocol và cipher suite an toàn theo policy
Đáp án đúng: D

Câu 39. Java HttpClient trong java.net.http nên được sử dụng thế nào ở nhiều request?
A. Tạo HttpClient mới cho từng request để giữ pool riêng
B. Tái sử dụng HttpClient để tận dụng quản lý kết nối
C. Tạo HttpClient từ Socket đang kết nối tới server
D. Tạo HttpClient bằng URI.resolve trước mọi request
Đáp án đúng: B

Câu 40. HttpRequest.BodyPublishers.ofString(payload) thường dùng cho trường hợp nào?
A. Đọc response body thành String sau khi server trả
B. Tạo decoder trực tiếp cho certificate của HTTPS
C. BodyPublishers.ofString tạo request body String
D. Định nghĩa trạng thái 2xx mặc định của response
Đáp án đúng: C

Câu 41. Khác biệt chính giữa HttpClient.send và sendAsync là gì?
A. send luôn chạy HTTP/1.1; sendAsync chỉ chạy HTTP/2
B. send dùng proxy; sendAsync luôn kết nối trực tiếp
C. send chờ response; sendAsync trả CompletableFuture
D. send có timeout; sendAsync không hỗ trợ timeout
Đáp án đúng: C

Câu 42. Để nhận HTTP response body dưới dạng String, handler nào phù hợp?
A. HttpRequest.BodyPublishers.ofString() khi đọc response
B. HttpResponse.BodyHandlers.discarding() để giữ chuỗi
C. HttpClient.Redirect.NORMAL để tự decode nội dung
D. HttpResponse.BodyHandlers.ofString() khi gửi request
Đáp án đúng: D

Câu 43. Khi HttpClient nhận status HTTP 404, hành vi nào thường đúng?
A. Response chứa statusCode 404, không tự ném lỗi HTTP status
B. HttpClient tự ném IOException vì mọi response 4xx
C. sendAsync luôn hoàn tất exceptionally cho status 4xx
D. Response tự retry đến khi chuyển được sang status 2xx
Đáp án đúng: A

Câu 44. HttpClient.connectTimeout khác HttpRequest.timeout ở phạm vi nào?
A. Cả hai chỉ áp dụng cho TLS handshake ở tầng transport
B. connectTimeout kiểm soát body, request.timeout kiểm soát DNS
C. Một cái giới hạn connect, một cái giới hạn thời gian request
D. connectTimeout đặt trên response, request.timeout đặt trên socket
Đáp án đúng: C

Câu 45. Khi muốn đi qua HTTP proxy cố định với Java HttpClient, nên cấu hình gì?
A. HttpRequest.Builder.uri(URI.create("proxy://host"))
B. HttpClient.Builder.proxy(ProxySelector.of(proxyAddress))
C. HttpClient.Builder.followRedirects(NEVER) để bật proxy
D. HttpResponse.BodyHandlers.ofString(proxyAddress)
Đáp án đúng: B

Câu 46. Khi không thiết lập redirect policy cho Java HttpClient, mặc định là gì?
A. Redirect.ALWAYS, tự theo mọi redirect kể cả HTTPS xuống HTTP
B. Redirect.NORMAL, tự theo 301/302 cho mọi request
C. Redirect.NEVER, không tự theo HTTP 3xx redirect
D. Redirect.SECURE, chỉ theo redirect giữ nguyên host
Đáp án đúng: C

Câu 47. HttpClient.Version.HTTP_2 thể hiện lựa chọn nào trong kết nối HTTP?
A. Ưu tiên dùng HTTP/2 nếu peer có thể thương lượng phù hợp
B. Bắt buộc mọi server chỉ phản hồi HTTP/2, nếu không lỗi ngay
C. Gửi mọi request bằng UDP datagram vì HTTP/2 là UDP
D. Bỏ TLS và kiểm tra chứng chỉ vì HTTP/2 đã mã hóa body
Đáp án đúng: A

Câu 48. Khi request POST có timeout sau khi gửi, tại sao retry cần cân nhắc?
A. Server có thể đã xử lý; cần idempotency hoặc chống lặp
B. Timeout chứng minh server chưa từng nhận bất kỳ bytes nào
C. HTTP POST mặc định sẽ tự loại bỏ tác dụng khi retry
D. Cứ retry vô hạn vì TCP đảm bảo giao dịch exactly-once
Đáp án đúng: A
