Bạn giải thích sự khác biệt giữa hostname, địa chỉ IP, cổng mạng và socket endpoint trong Java như thế nào?
Bạn mô tả quy trình phân giải DNS từ tên miền tới địa chỉ IP trước khi tạo kết nối TCP ra sao?
Bạn phân biệt DNS A record với AAAA record khi một hostname có thể trỏ tới IPv4 hoặc IPv6 như thế nào?
Bạn sẽ dùng InetAddress.getByName để phân giải hostname và xử lý trường hợp không có kết quả theo cách nào?
Bạn phân biệt InetAddress.getAllByName với getByName trong ứng dụng cần thử nhiều địa chỉ IP ra sao?
Bạn sẽ thiết kế kết nối tới hostname có nhiều địa chỉ để giảm rủi ro một địa chỉ không phản hồi như thế nào?
Bạn giải thích tác động của DNS caching trong JVM khi IP của một backend thay đổi sau failover như thế nào?
Bạn sẽ đánh giá cấu hình networkaddress.cache.ttl và networkaddress.cache.negative.ttl theo yêu cầu DNS refresh nào?
Bạn phân biệt positive DNS caching với negative caching về khả năng phục hồi sau lỗi phân giải ra sao?
Bạn sẽ xác định vì sao thay đổi DNS record chưa chắc có hiệu lực ngay trong một ứng dụng Java chạy lâu như thế nào?
Bạn mô tả Inet4Address và Inet6Address đại diện những dạng địa chỉ nào ra sao?
Bạn sẽ xử lý IPv6 literal trong một URI có host và port theo cú pháp nào?
Bạn phân biệt địa chỉ loopback, link-local và private address về phạm vi kết nối như thế nào?
Bạn sẽ dùng InetAddress.isLoopbackAddress và isSiteLocalAddress để phân loại địa chỉ nhưng đánh giá giới hạn của chúng ra sao?
Bạn phân tích vì sao InetAddress.isReachable không đủ chứng minh một TCP service cụ thể đang phục vụ như thế nào?
Bạn sẽ sử dụng NetworkInterface để liệt kê giao diện và địa chỉ mạng khi cần chọn nguồn kết nối ra sao?
Bạn phân biệt bind vào wildcard address với bind vào một địa chỉ giao diện cụ thể theo phạm vi lắng nghe như thế nào?
Bạn mô tả InetSocketAddress kết hợp hostname hoặc IP với port và trạng thái unresolved như thế nào?
Bạn sẽ dùng InetSocketAddress.createUnresolved khi cần trì hoãn DNS lookup theo chính sách nào?
Bạn phân tích vì sao hostname là danh tính logic nhưng IP address không phải bằng chứng xác thực TLS server ra sao?
Bạn sẽ thiết kế chẩn đoán riêng cho UnknownHostException so với ConnectException như thế nào?
Bạn phân biệt DNS lookup failure với TCP connect timeout trong luồng lỗi mạng ra sao?
Bạn sẽ chọn chiến lược ưu tiên IPv6/IPv4 dựa trên khả năng kết nối thực tế thay vì giả định DNS trả về một địa chỉ ra sao?
Bạn phân tích nguy cơ DNS rebinding khi ứng dụng phân giải tên miền do người dùng cung cấp để gọi HTTP như thế nào?
Bạn sẽ kiểm tra địa chỉ sau phân giải và các lần redirect khi xây tính năng gọi URL bên ngoài để tránh SSRF ra sao?
Bạn sẽ quản lý DNS timeout và retry mà không nhân quá số lượt truy vấn hoặc gây retry storm như thế nào?
Bạn mô tả vì sao một port mở trên localhost không đồng nghĩa dịch vụ có thể truy cập từ bên ngoài container như thế nào?
Bạn sẽ thiết kế một phép thử sử dụng loopback và cổng ngẫu nhiên để kiểm chứng kết nối TCP mà không phụ thuộc Internet ra sao?
Bạn phân biệt URI với URL trong Java theo vai trò định danh tài nguyên và khả năng mở kết nối như thế nào?
Bạn sẽ sử dụng URI.create và new URI trong những tình huống cần xử lý input hợp lệ khác nhau ra sao?
Bạn mô tả các thành phần scheme, authority, host, port, path, query và fragment của một URI như thế nào?
Bạn phân biệt URI.getPath với getRawPath khi đầu vào chứa percent-encoded characters ra sao?
Bạn sẽ xác định nguy cơ mã hóa hoặc giải mã URI hai lần khi ghép đường dẫn API như thế nào?
Bạn phân tích vì sao nối chuỗi thủ công để tạo URL có thể làm sai query parameters chứa dấu cách và ký tự đặc biệt ra sao?
Bạn sẽ thiết kế bộ dựng URI an toàn khi path segment chứa dấu gạch chéo cần được coi là dữ liệu ra sao?
Bạn phân biệt percent encoding cho query string với form encoding của application/x-www-form-urlencoded theo quy tắc nào?
Bạn sẽ dùng URLEncoder và URLDecoder mà không nhầm chúng với bộ mã hóa path segment của một URI như thế nào?
Bạn giải thích URI.resolve xử lý một đường dẫn tương đối dựa trên base URI như thế nào?
Bạn sẽ xác định sự khác nhau giữa URI.normalize và canonicalization cần thiết cho security policy ra sao?
Bạn phân tích rủi ro dùng URI normalization không đồng nhất giữa reverse proxy và Java server khiến đường dẫn được kiểm soát sai như thế nào?
Bạn sẽ dùng IDN.toASCII khi làm việc với tên miền quốc tế hóa và cân nhắc giới hạn nào?
Bạn phân biệt host trong URI với Host HTTP header về nguồn dữ liệu và tác dụng định tuyến ra sao?
Bạn sẽ kiểm tra scheme của URI trước khi cho ứng dụng mở kết nối tới tài nguyên do bên ngoài cung cấp như thế nào?
Bạn phân tích vì sao file URI hoặc jar URI không nên được đối xử như HTTP endpoint nếu ứng dụng nhận địa chỉ từ người dùng ra sao?
Bạn sẽ phân biệt URL.openConnection với HttpClient về cách quản lý HTTP connection, timeout và redirects như thế nào?
Bạn mô tả URLConnection.connect khởi tạo kết nối theo protocol handler và cấu hình ra sao?
Bạn sẽ xác định sự khác nhau giữa connect timeout và read timeout của URLConnection theo tác động đến request nào?
Bạn phân tích rủi ro đọc toàn bộ response qua URL.openStream mà không giới hạn kích thước hoặc timeout như thế nào?
Bạn sẽ thiết kế validation để từ chối URI chứa credentials trong user-info nếu ứng dụng không hỗ trợ nó ra sao?
Bạn phân biệt URI có fragment với HTTP request target thực tế gửi tới server như thế nào?
Bạn sẽ tổ chức redaction query parameters khi ghi logs để không lộ access token hoặc dữ liệu cá nhân ra sao?
Bạn phân tích vì sao IPv6 host cần dấu ngoặc vuông khi ghép với port trong URI dạng chuỗi như thế nào?
Bạn sẽ kiểm thử các URI có Unicode, percent encoding, empty query và relative references theo nhóm tình huống nào?
Bạn giải thích cơ chế TCP three-way handshake liên hệ thế nào với Socket.connect trong Java?
Bạn phân biệt TCP là byte stream với mô hình message-oriented của UDP theo nghĩa truyền dữ liệu như thế nào?
Bạn sẽ tạo TCP client bằng Socket và kết nối tới InetSocketAddress với connect timeout ra sao?
Bạn mô tả ServerSocket.bind và accept thiết lập khả năng nhận kết nối của một Java server như thế nào?
Bạn phân biệt listening socket với accepted Socket xử lý một client cụ thể ra sao?
Bạn sẽ thiết kế vòng lặp accept nhiều clients mà không để một client chậm chặn toàn bộ server như thế nào?
Bạn phân tích khi nào mô hình một thread cho mỗi kết nối tiêu tốn quá nhiều threads và memory như thế nào?
Bạn sẽ lựa chọn virtual threads cho blocking socket handlers theo giới hạn I/O và tài nguyên nào?
Bạn phân biệt TCP connection establishment với application-level handshake khi cần xác nhận peer có hỗ trợ protocol ra sao?
Bạn mô tả InputStream.read trên Socket có thể trả ít byte hơn số lượng ứng dụng yêu cầu như thế nào?
Bạn sẽ xử lý kết quả read bằng âm một để nhận biết kết nối đã đóng phía remote như thế nào?
Bạn phân biệt Socket.setSoTimeout với Socket.connect timeout theo thao tác bị giới hạn thời gian ra sao?
Bạn sẽ xác định trường hợp read timeout không đồng nghĩa toàn bộ giao dịch đã vượt quá deadline như thế nào?
Bạn phân tích vì sao một lần OutputStream.write không bảo đảm peer đã xử lý dữ liệu tại application layer ra sao?
Bạn sẽ sử dụng Socket.shutdownOutput khi muốn báo không còn gửi dữ liệu nhưng vẫn nhận phản hồi ra sao?
Bạn phân biệt shutdownInput, shutdownOutput và Socket.close theo vòng đời half-close của TCP như thế nào?
Bạn sẽ xác định tại sao đóng socket đột ngột có thể khiến peer thấy Connection reset thay vì kết thúc bình thường ra sao?
Bạn mô tả ảnh hưởng của TCP_NODELAY tới độ trễ khi gửi nhiều messages nhỏ như thế nào?
Bạn phân biệt Nagle algorithm với cơ chế flush ở Java BufferedOutputStream theo các tầng nào?
Bạn sẽ quyết định sử dụng SO_KEEPALIVE để phát hiện kết nối chết và nêu giới hạn của nó ra sao?
Bạn phân tích vì sao TCP keepalive không thay thế heartbeat ở tầng giao thức khi cần phát hiện lỗi nhanh như thế nào?
Bạn sẽ cấu hình SO_REUSEADDR khi khởi động lại server và tránh giả định nó giống nhau trên mọi hệ điều hành ra sao?
Bạn sẽ chọn receive/send buffer sizes theo throughput và cách TCP flow control vận hành như thế nào?
Bạn phân biệt congestion control với flow control khi TCP giảm tốc độ truyền như thế nào?
Bạn sẽ xác định khi nào backpressure ở tầng ứng dụng vẫn cần thiết dù TCP có cơ chế flow control như thế nào?
Bạn phân tích rủi ro chỉ dựa vào TCP checksum mà không có application validation cho dữ liệu nghiệp vụ ra sao?
Bạn sẽ quản lý try-with-resources cho Socket và streams để tránh rò kết nối khi xử lý exception như thế nào?
Bạn sẽ kiểm tra client hủy kết nối giữa lúc server đang ghi response và xử lý IOException ra sao?
Bạn sẽ thiết kế graceful shutdown dừng nhận kết nối mới nhưng cho phép các requests hiện tại kết thúc như thế nào?
Bạn phân tích vì sao SocketTimeoutException và ConnectException cần được xử lý thành hai loại lỗi khác nhau ra sao?
Bạn giải thích vì sao một TCP stream không giữ nguyên ranh giới của từng message được ứng dụng ghi như thế nào?
Bạn sẽ thiết kế length-prefixed message framing khi application protocol gửi nhiều binary messages trên một kết nối như thế nào?
Bạn phân biệt delimiter-based framing với length-prefix framing theo khả năng escape dữ liệu và chống payload lớn ra sao?
Bạn sẽ xác định giới hạn message length trước khi cấp phát ByteBuffer hoặc byte array theo dữ liệu từ mạng như thế nào?
Bạn phân tích nguy cơ peer khai báo độ dài message cực lớn gây memory exhaustion trước khi gửi payload thật như thế nào?
Bạn sẽ dùng DataInputStream.readFully để đọc một payload đúng kích thước nhưng xử lý EOF sớm ra sao?
Bạn phân biệt DataInputStream.readInt theo network byte order với parse bốn bytes bằng thứ tự little-endian như thế nào?
Bạn sẽ thiết kế bộ giải mã xử lý một message được chia qua nhiều lần InputStream.read từ Socket như thế nào?
Bạn mô tả bộ xử lý khi một lần read nhận nhiều messages liên tiếp phải giữ lại bytes chưa tiêu thụ ra sao?
Bạn sẽ phân biệt encoding UTF-8 với độ dài ký tự Java khi gửi string qua socket như thế nào?
Bạn phân tích vì sao dùng String.length để khai báo byte length có thể làm hỏng framing với ký tự tiếng Việt ra sao?
Bạn sẽ quyết định khi nào dùng JSON, Protobuf hoặc binary format cho application protocol dựa trên compatibility nào?
Bạn sẽ thiết kế version field và capability negotiation để client/server có thể nâng cấp protocol độc lập như thế nào?
Bạn phân tích rủi ro parser tự cấp phát nhiều objects cho một message không tin cậy trước khi kiểm tra giới hạn ra sao?
Bạn sẽ xử lý truncated payload, checksum failure và invalid message type theo mã lỗi giao thức nào?
Bạn sẽ xác định cách chống slowloris ở TCP protocol khi peer gửi từng byte rất chậm mà không bao giờ hoàn thành message như thế nào?
Bạn phân biệt per-read timeout với total message deadline và idle connection timeout ra sao?
Bạn sẽ áp dụng cancellation khi tổng thời gian nhận message vượt deadline mà không để task chờ mãi ra sao?
Bạn mô tả cơ chế request ID correlation khi có nhiều requests và responses trên một kết nối như thế nào?
Bạn sẽ giải quyết vấn đề response đến không theo thứ tự gửi nếu protocol hỗ trợ multiplexing ra sao?
Bạn phân tích vì sao retry một request sau timeout có thể tạo side effect trùng dù TCP có truyền dữ liệu đáng tin cậy ra sao?
Bạn sẽ thiết kế idempotency key ở application layer cho thao tác tạo resource khi client không biết server đã xử lý chưa như thế nào?
Bạn sẽ xác định khi nào cần heartbeat ping/pong để kiểm tra peer còn xử lý protocol thay vì chỉ còn socket mở ra sao?
Bạn phân biệt keepalive message với request timeout và connection liveness theo ý nghĩa nào?
Bạn sẽ xây dựng state machine cho một protocol login, authenticated và closing để tránh nhận message sai thứ tự như thế nào?
Bạn sẽ kiểm thử decoder với dữ liệu bị chia tại mọi vị trí boundary, message rỗng và nhiều message dồn cùng read ra sao?
Bạn sẽ tổ chức queue giới hạn số lượng outbound messages để một slow consumer không làm tăng heap vô hạn như thế nào?
Bạn giải thích UDP datagram truyền các gói độc lập mà không bảo đảm delivery hay ordering như thế nào?
Bạn phân biệt DatagramSocket với DatagramChannel theo cơ chế blocking và tích hợp NIO ra sao?
Bạn sẽ tạo UDP server bằng DatagramSocket.bind và nhận DatagramPacket theo cách nào?
Bạn mô tả DatagramPacket chứa địa chỉ nguồn, port và payload length sau khi nhận datagram như thế nào?
Bạn sẽ xác định khi nào DatagramPacket buffer nhỏ hơn gói đến khiến dữ liệu bị cắt mà ứng dụng cần xử lý ra sao?
Bạn phân tích vì sao ứng dụng không thể coi một datagram vượt MTU sẽ được truyền an toàn nếu có IP fragmentation như thế nào?
Bạn sẽ lựa chọn kích thước UDP payload để hạn chế fragmentation theo điều kiện mạng nào?
Bạn phân biệt UDP connect trên DatagramSocket với TCP handshake và phiên kết nối tin cậy như thế nào?
Bạn sẽ dùng DatagramSocket.setSoTimeout để tránh chờ nhận vô hạn và xử lý timeout ra sao?
Bạn mô tả DatagramSocket.send tạo datagram gửi tới một địa chỉ và port cụ thể như thế nào?
Bạn sẽ xử lý một UDP response không khớp request identifier hoặc nguồn peer đã dự kiến như thế nào?
Bạn phân tích rủi ro UDP spoofing khiến ứng dụng tin một datagram chỉ vì source IP và port ra sao?
Bạn sẽ thiết kế application-level sequence number để phát hiện mất gói hoặc gói đến sai thứ tự như thế nào?
Bạn phân biệt retransmission của ứng dụng với cơ chế khôi phục loss của TCP theo trách nhiệm nào?
Bạn sẽ chọn khi nào UDP phù hợp cho dữ liệu thời gian thực có thể bỏ qua gói lỗi thay vì dùng TCP ra sao?
Bạn phân tích vì sao retry UDP không có backoff có thể khuếch đại lưu lượng khi server quá tải ra sao?
Bạn sẽ cấu hình MulticastSocket để tham gia nhóm multicast cùng một network interface cụ thể như thế nào?
Bạn phân biệt multicast với broadcast về phạm vi phân phối và cấu hình router/network như thế nào?
Bạn sẽ dùng DatagramChannel.join để nhận multicast group trong NIO theo điều kiện nào?
Bạn phân tích nguy cơ multicast traffic bị chặn trong container hoặc cloud network dù local test PASS ra sao?
Bạn sẽ xác định tác động của TTL/hop limit đối với phạm vi gửi multicast như thế nào?
Bạn sẽ lựa chọn protocol bảo vệ tính toàn vẹn cho UDP message vì transport không tự xác thực sender như thế nào?
Bạn sẽ cân nhắc DTLS thay TLS thông thường cho ứng dụng datagram theo các điều kiện nào?
Bạn sẽ viết test UDP trên loopback chấp nhận packet loss giả lập và duplicate packets mà không gây flaky vô ích như thế nào?
Bạn giải thích Java NIO phân biệt Buffer, Channel và Selector theo trách nhiệm nào?
Bạn sẽ mô tả SocketChannel khác Socket về blocking mode và thao tác read/write như thế nào?
Bạn phân biệt ServerSocketChannel với SocketChannel trong một TCP server dùng NIO ra sao?
Bạn sẽ dùng ServerSocketChannel.configureBlocking(false) trước khi đăng ký vào Selector như thế nào?
Bạn mô tả Selector.select lấy các kênh sẵn sàng cho các loại thao tác I/O đã quan tâm như thế nào?
Bạn phân biệt SelectionKey.OP_ACCEPT, OP_CONNECT, OP_READ và OP_WRITE theo trạng thái kênh nào?
Bạn sẽ quản lý interestOps của SelectionKey để tránh kiểm tra OP_WRITE liên tục khi outbound queue rỗng như thế nào?
Bạn phân tích vì sao OP_WRITE thường gần như luôn ready gây CPU spin nếu không quản lý interestOps ra sao?
Bạn sẽ xử lý selectedKeys sau select và xóa các key đã xử lý để tránh lặp sai như thế nào?
Bạn phân biệt SelectionKey.cancel với SocketChannel.close trong vòng đời một kết nối NIO ra sao?
Bạn sẽ gọi SocketChannel.finishConnect sau OP_CONNECT để hoàn tất nonblocking connect như thế nào?
Bạn mô tả ByteBuffer position, limit và capacity tương tác trong quá trình ghi và đọc dữ liệu như thế nào?
Bạn sẽ sử dụng ByteBuffer.flip trước khi chuyển từ ghi dữ liệu vào buffer sang đọc dữ liệu ra sao?
Bạn phân biệt ByteBuffer.clear với compact khi còn bytes của message chưa được decoder tiêu thụ như thế nào?
Bạn sẽ xác định vì sao gọi clear thay compact có thể làm mất phần frame chưa đọc hết ra sao?
Bạn mô tả ByteBuffer.slice và duplicate chia sẻ underlying storage nhưng có position/limit riêng ra sao?
Bạn phân biệt heap ByteBuffer với direct ByteBuffer về memory placement và I/O overhead như thế nào?
Bạn sẽ quyết định khi nào allocateDirect hợp lý và cách kiểm soát direct memory usage ra sao?
Bạn sẽ xử lý SocketChannel.read trả 0 trong nonblocking mode thay vì coi đó là EOF như thế nào?
Bạn phân biệt SocketChannel.read trả âm một với trả 0 khi peer đóng hoặc tạm chưa có dữ liệu ra sao?
Bạn sẽ viết state machine đọc length prefix rồi tiếp tục payload qua nhiều lần read ra sao?
Bạn phân tích vì sao SocketChannel.write có thể gửi ít bytes hơn remaining() và phải giữ outbound buffer cho lần sau ra sao?
Bạn sẽ thiết kế per-connection outbound queue có giới hạn để xử lý slow clients như thế nào?
Bạn sẽ đặt SelectionKey attachment để lưu trạng thái decoder, encoder và pending writes theo client ra sao?
Bạn mô tả Selector.wakeup giải phóng thread đang chờ select khi một thread khác thay đổi task queue như thế nào?
Bạn sẽ phối hợp selector thread với worker threads để tránh sửa SelectionKey hoặc queues không thread-safe ra sao?
Bạn phân tích rủi ro block selector thread bằng database call hay JSON parsing nặng khiến tất cả clients bị chậm ra sao?
Bạn sẽ sử dụng ByteBuffer.order để xử lý byte order khi giao thức binary quy định little-endian ra sao?
Bạn phân biệt scatter/gather I/O của SocketChannel với việc tự nối nhiều byte arrays theo chi phí nào?
Bạn sẽ kiểm tra selector loop dùng CPU cao khi không có traffic bằng cách quan sát select wakeups và interestOps như thế nào?
Bạn sẽ thiết kế shutdown cho selector, channels và selector thread để không giữ file descriptors sau khi dừng server ra sao?
Bạn giải thích asynchronous I/O API trong java.nio.channels khác Selector-based nonblocking I/O theo cơ chế callback như thế nào?
Bạn sẽ dùng AsynchronousSocketChannel.connect để thiết lập kết nối mà không chặn thread gọi theo cách nào?
Bạn phân biệt Future-based completion với CompletionHandler khi gọi read hoặc write qua AsynchronousSocketChannel ra sao?
Bạn sẽ xây dựng asynchronous TCP server bằng AsynchronousServerSocketChannel.accept theo mô hình nào?
Bạn mô tả CompletionHandler.completed và failed phối hợp với application state sau mỗi operation như thế nào?
Bạn sẽ xác định vì sao một asynchronous read vẫn có thể nhận ít bytes hơn kích thước message cần đọc ra sao?
Bạn phân tích rủi ro khởi tạo nhiều concurrent reads trên cùng AsynchronousSocketChannel không đúng protocol state như thế nào?
Bạn sẽ thiết kế chuỗi read callbacks cho length-prefixed messages mà không tạo recursive stack growth vô kiểm soát ra sao?
Bạn sẽ xử lý partial asynchronous writes và tiếp tục gửi khi ByteBuffer còn remaining bytes như thế nào?
Bạn phân biệt completion callback thread với thread gọi API khi ghi dữ liệu chung vào state mutable ra sao?
Bạn sẽ dùng AsynchronousChannelGroup để quản lý threads phục vụ các asynchronous channels theo nhu cầu nào?
Bạn phân tích rủi ro callback làm CPU-heavy work trên nhóm threads I/O và chặn các completions khác ra sao?
Bạn sẽ xác định giới hạn thực tế của asynchronous file/network operations khác nhau theo JVM và hệ điều hành như thế nào?
Bạn sẽ thiết kế cancellation khi Future của một operation không còn cần thiết nhưng channel vẫn cần cleanup ra sao?
Bạn phân biệt socket-level timeout với deadline của toàn bộ request khi I/O bất đồng bộ ra sao?
Bạn sẽ tổ chức CompletableFuture bao quanh CompletionHandler để kết hợp với application workflow như thế nào?
Bạn phân tích vì sao CompletableFuture.cancel không tự bảo đảm remote peer đã ngừng xử lý request ra sao?
Bạn sẽ giữ correlation giữa response và request trong asynchronous client có nhiều outstanding operations ra sao?
Bạn sẽ áp dụng backpressure khi tốc độ callbacks nhận dữ liệu cao hơn khả năng xử lý nghiệp vụ như thế nào?
Bạn phân biệt asynchronous I/O dựa trên channels với virtual-thread blocking I/O theo độ phức tạp và khả năng scale ra sao?
Bạn sẽ lựa chọn Selector, AsynchronousSocketChannel hay virtual-thread-per-connection khi xây server có hàng chục nghìn kết nối theo tiêu chí nào?
Bạn sẽ kiểm thử completion order bị đảo, lỗi channel đóng và timeout mà không dựa vào Thread.sleep thiếu ổn định ra sao?
Bạn giải thích TLS tạo kênh bảo mật trên TCP qua xác thực peer, bảo mật dữ liệu và kiểm tra toàn vẹn như thế nào?
Bạn phân biệt TLS handshake với TCP handshake về loại thông tin được thương lượng ra sao?
Bạn sẽ sử dụng SSLContext để cấu hình nền tảng TLS cho Java client và server như thế nào?
Bạn mô tả vai trò của KeyManagerFactory và TrustManagerFactory khi khởi tạo SSLContext ra sao?
Bạn phân biệt keystore chứa private key/certificate với truststore dùng xác minh phía đối tác ra sao?
Bạn sẽ quản lý password của keystore và truststore mà không lưu plaintext trong source repository như thế nào?
Bạn phân tích nguy cơ dùng TrustManager chấp nhận mọi chứng chỉ khiến TLS mất khả năng xác thực server ra sao?
Bạn sẽ cấu hình SSLSocket để thực hiện TLS connection với một endpoint từ Java như thế nào?
Bạn phân biệt SSLSocket với SSLServerSocket về vai trò client và server trong TLS handshake như thế nào?
Bạn sẽ bật hostname verification cho TLS client khi API mặc định không tự áp dụng HTTPS endpoint identification theo cách nào?
Bạn mô tả SSLParameters.setEndpointIdentificationAlgorithm với giá trị HTTPS hỗ trợ kiểm tra tên server như thế nào?
Bạn phân biệt kiểm tra certificate chain với kiểm tra hostname trong xác thực TLS endpoint ra sao?
Bạn sẽ xử lý server certificate bị hết hạn hoặc hostname mismatch thay vì tắt validation như thế nào?
Bạn phân tích nguy cơ dùng chứng chỉ tự ký trong production mà không có quy trình trust anchor rõ ràng ra sao?
Bạn sẽ thiết kế mutual TLS khi server phải xác minh chứng chỉ của client theo chính sách nào?
Bạn phân biệt TLS client certificate authentication với application authorization sau khi xác thực peer ra sao?
Bạn sẽ chọn protocol versions và cipher suites cho SSLParameters dựa trên cấu hình JDK và yêu cầu bảo mật nào?
Bạn phân tích vì sao hardcode một cipher suite không được runtime hỗ trợ có thể làm TLS handshake thất bại ra sao?
Bạn sẽ sử dụng SNIHostName khi cần chỉ định tên virtual host trong TLS handshake theo điều kiện nào?
Bạn mô tả ALPN cho phép client/server thương lượng giao thức ứng dụng như HTTP/2 ra sao?
Bạn sẽ phân biệt TLS handshake timeout với socket read timeout khi điều tra kết nối treo như thế nào?
Bạn phân tích rủi ro hostname verification bỏ qua SAN của chứng chỉ hoặc chỉ kiểm tra Common Name theo cách cũ ra sao?
Bạn sẽ tổ chức certificate rotation để client không gián đoạn kết nối khi backend thay khóa như thế nào?
Bạn sẽ dùng SSLEngine cho TLS trên nonblocking SocketChannel theo các bước xử lý unwrap/wrap nào?
Bạn phân biệt SSLEngine NEED_WRAP, NEED_UNWRAP và NEED_TASK trong trạng thái handshake như thế nào?
Bạn sẽ xử lý buffer underflow/overflow khi SSLEngine yêu cầu dữ liệu mã hóa hoặc plaintext buffer lớn hơn như thế nào?
Bạn phân tích rủi ro quên xử lý close_notify khiến ứng dụng không biết peer đã đóng TLS đúng cách ra sao?
Bạn sẽ kiểm tra TLS session resumption khi kết nối ngắn lặp lại và cân nhắc bảo mật các session tickets như thế nào?
Bạn sẽ thiết kế chẩn đoán SSLHandshakeException dựa trên trust chain, hostname, protocol và certificate usage ra sao?
Bạn giải thích java.net.http.HttpClient cung cấp những thành phần nào cho việc gửi HTTP requests từ Java như thế nào?
Bạn phân biệt HttpClient với HttpURLConnection về HTTP/2, asynchronous calls và tái sử dụng cấu hình ra sao?
Bạn sẽ xây dựng một HttpClient có connectTimeout và version policy phù hợp với API đích như thế nào?
Bạn mô tả HttpRequest.Builder cấu hình URI, headers, method và request timeout như thế nào?
Bạn phân biệt HttpClient.Builder.connectTimeout với HttpRequest.Builder.timeout theo giai đoạn được giới hạn ra sao?
Bạn sẽ dùng HttpClient.send cho synchronous call và xử lý InterruptedException theo chính sách nào?
Bạn phân biệt HttpClient.sendAsync với send về kết quả CompletableFuture và cách điều phối bất đồng bộ ra sao?
Bạn sẽ chọn BodyPublishers.ofString, ofFile hoặc ofInputStream theo kích thước và nguồn request body nào?
Bạn phân tích rủi ro tái sử dụng BodyPublisher không phát lại dữ liệu được khi tự động retry một POST request ra sao?
Bạn sẽ dùng BodyHandlers.ofString cho response nhỏ và tránh nạp toàn bộ response lớn vào memory như thế nào?
Bạn mô tả BodyHandlers.ofInputStream giúp xử lý streaming response nhưng đòi hỏi cleanup tài nguyên ra sao?
Bạn sẽ xử lý HTTP status 4xx/5xx tách biệt với IOException hoặc HttpTimeoutException như thế nào?
Bạn phân biệt HttpConnectTimeoutException với HttpTimeoutException khi chẩn đoán HTTP client timeout ra sao?
Bạn sẽ cấu hình followRedirects của HttpClient và đánh giá nguy cơ đi qua domain không tin cậy như thế nào?
Bạn phân tích rủi ro tự chuyển tiếp Authorization header sang endpoint khác sau redirect theo cách sai ra sao?
Bạn sẽ xây dựng ProxySelector để định tuyến HTTP request qua corporate proxy theo yêu cầu nào?
Bạn phân biệt HTTP proxy với SOCKS proxy trong cấu hình Java networking và giới hạn của từng API như thế nào?
Bạn sẽ dùng Authenticator cho HTTP proxy authentication hoặc server challenge mà không để lộ credentials trong logs ra sao?
Bạn phân tích vì sao HTTP keep-alive và connection reuse ảnh hưởng latency của nhiều requests tới cùng host như thế nào?
Bạn sẽ kiểm tra HttpClient được chia sẻ an toàn giữa nhiều threads theo vòng đời ứng dụng như thế nào?
Bạn mô tả HttpResponse.BodyHandler quyết định cách tiêu thụ response body và memory footprint như thế nào?
Bạn sẽ truyền request correlation ID trong HTTP headers và xử lý response tương ứng như thế nào?
Bạn phân tích vì sao Retry-After của HTTP 429 hoặc 503 cần được xét cùng tổng deadline trước khi retry ra sao?
Bạn sẽ sử dụng java.net.http.WebSocket cùng WebSocket.Listener khi ứng dụng cần kênh thông điệp hai chiều như thế nào?
Bạn phân biệt WebSocket ping/pong với HTTP request-response và TCP keepalive theo mục tiêu kiểm tra liveness ra sao?
Bạn sẽ quản lý backpressure qua WebSocket.Listener.request khi nhận nhiều events liên tiếp như thế nào?
Bạn sẽ kiểm thử HTTP client với local fake server thay vì phụ thuộc external API có thể thay đổi ra sao?
Bạn sẽ quyết định khi nào dùng HTTP Client chuẩn JDK và khi nào chọn thư viện networking khác có tính năng bổ sung như thế nào?
Bạn giải thích khác biệt giữa retry, timeout, deadline và circuit breaker trong một network client có độ tin cậy cao như thế nào?
Bạn sẽ thiết kế tổng request deadline bao gồm DNS, connect, TLS handshake, read và retry delays ra sao?
Bạn phân biệt connect timeout, read timeout, idle timeout và application processing timeout theo triệu chứng nào?
Bạn phân tích vì sao timeout không chứng minh remote server chưa xử lý một thao tác ghi như thế nào?
Bạn sẽ quyết định retry GET hay PUT và POST dựa trên idempotency semantics thay vì chỉ dựa vào HTTP method name ra sao?
Bạn sẽ sử dụng exponential backoff với jitter để tránh đồng loạt retry khi backend vừa phục hồi như thế nào?
Bạn phân tích nguy cơ retry amplification khi mỗi tầng proxy, HTTP client và service cùng tự retry ra sao?
Bạn sẽ đặt retry budget chung với rate limit để bảo vệ server quá tải theo chính sách nào?
Bạn sẽ phân biệt lỗi DNS tạm thời với lỗi certificate verification và sai HTTP credentials trước khi quyết định retry ra sao?
Bạn sẽ thiết kế circuit breaker mở khi upstream lỗi nhưng vẫn bảo đảm không coi thất bại nghiệp vụ là network outage như thế nào?
Bạn phân tích nguy cơ tạo hàng nghìn kết nối mới khi connection pool bị cạn và hệ thống liên tục retry ra sao?
Bạn sẽ giới hạn concurrent connections hoặc in-flight requests để áp dụng backpressure tới caller như thế nào?
Bạn sẽ phân biệt TCP-level connection pool với HTTP/2 multiplexing theo cách tiêu thụ sockets ra sao?
Bạn sẽ quyết định keepalive timeout và idle connection eviction khi backend hoặc load balancer đóng kết nối nhàn rỗi ra sao?
Bạn phân tích vì sao client phải xử lý connection reset khi tái sử dụng pooled connection đã bị server đóng như thế nào?
Bạn sẽ thiết kế graceful shutdown của networking client để ngừng nhận request mới và giải phóng resources ra sao?
Bạn sẽ chọn proxy bypass rules khi giao tiếp với localhost hoặc địa chỉ nội bộ mà không tạo đường đi ngoài ý muốn ra sao?
Bạn phân tích rủi ro tin HTTP redirects hoặc URL do user gửi khiến application truy cập metadata endpoint nội bộ như thế nào?
Bạn sẽ xây dựng allowlist scheme, domain và resolved IP ranges để hạn chế SSRF trên outbound HTTP requests ra sao?
Bạn phân biệt TLS encryption với application-level authentication và authorization đối với một API như thế nào?
Bạn sẽ giới hạn header size, message size và số lượng kết nối nhằm giảm nguy cơ network DoS ra sao?
Bạn phân tích vì sao server phải tách parsing input không tin cậy khỏi business side effects và quyền truy cập như thế nào?
Bạn sẽ thiết kế structured error categories cho DNS, connect, TLS, framing, timeout và remote application errors như thế nào?
Bạn sẽ dùng correlation IDs và distributed tracing để định vị một request thất bại qua proxy và nhiều backend như thế nào?
Bạn sẽ bảo đảm logs không chứa raw cookies, authorization headers hoặc private network secrets như thế nào?
Bạn phân biệt unit test message decoder với integration test dùng TCP/UDP socket thực trên loopback như thế nào?
Bạn sẽ tạo ServerSocket bind port 0 và lấy actual local port để tránh va chạm trong test như thế nào?
Bạn sẽ kiểm thử TCP client đọc thiếu frame bằng cách server gửi payload thành nhiều chunks như thế nào?
Bạn sẽ kiểm thử nhiều frames trong một lần read để chứng minh decoder không nhầm ranh giới dữ liệu ra sao?
Bạn sẽ tổ chức test half-close TCP và EOF để xác minh cleanup của client/server như thế nào?
Bạn phân tích vì sao test networking dùng Thread.sleep thay cho coordination primitives dễ flaky trên CI ra sao?
Bạn sẽ dùng CountdownLatch hoặc CompletableFuture để đồng bộ server fixture và client test theo cách nào?
Bạn sẽ giả lập kết nối bị reset giữa lúc ghi response để đánh giá cleanup và exception handling ra sao?
Bạn sẽ tạo test connect timeout mà không phụ thuộc một public IP cố định có thể thay đổi trạng thái như thế nào?
Bạn phân biệt test read timeout với server trả HTTP 503 sau một thời gian dài theo mong đợi nào?
Bạn sẽ giả lập DNS lookup failure hoặc resolver trả nhiều IP để kiểm tra fallback strategy ra sao?
Bạn sẽ kiểm thử SocketChannel partial write và OP_WRITE interest handling dưới backpressure giả lập như thế nào?
Bạn sẽ kiểm tra Selector loop không gây busy spin khi không có dữ liệu bằng metrics nào?
Bạn sẽ xây dựng test cho AsynchronousSocketChannel khi CompletionHandler.failed được gọi sau channel close ra sao?
Bạn sẽ kiểm thử UDP packet loss, duplicate và out-of-order bằng transport fake có thể kiểm soát như thế nào?
Bạn sẽ kiểm tra multicast join group bị lỗi trong môi trường CI và quyết định khi nào skip environment-specific test ra sao?
Bạn sẽ tạo TLS test server bằng chứng chỉ thử nghiệm và truststore riêng để kiểm tra hostname verification như thế nào?
Bạn sẽ kiểm thử SSLHandshakeException do chứng chỉ hết hạn hoặc tên host sai mà không vô hiệu hóa certificate validation ra sao?
Bạn sẽ dùng local HttpServer hoặc stub HTTP backend để kiểm thử HttpClient redirects, status và timeouts như thế nào?
Bạn sẽ kiểm tra response streaming được đóng đúng khi caller hủy CompletableFuture hoặc dừng đọc giữa chừng ra sao?
Bạn sẽ chạy load test đánh giá throughput, p95 latency và số file descriptors với nhiều kết nối đồng thời như thế nào?
Bạn sẽ đo packet retransmissions, connection resets và DNS errors bằng metrics cùng logs nào?
Bạn sẽ phân biệt SocketException từ local close với network failure từ peer trong incident response như thế nào?
Bạn sẽ lập runbook chẩn đoán UnknownHostException, ConnectException, SocketTimeoutException và SSLHandshakeException ra sao?
Bạn sẽ sử dụng tcpdump hoặc Wireshark trong môi trường kiểm thử để đối chiếu TCP handshake, retransmission và TLS handshake mà không lộ dữ liệu nhạy cảm như thế nào?
Bạn sẽ đánh giá timeouts và retries sau khi triển khai proxy hoặc load balancer có idle timeout khác ứng dụng ra sao?
Bạn sẽ xác định checklist production cho Java networking gồm connection lifecycle, TLS, framing, limits, backpressure, observability và CI tests như thế nào?
Nếu InetAddress trả địa chỉ cũ sau khi backend đã failover, bạn sẽ kiểm tra JVM DNS cache và chính sách retry như thế nào?
Nếu một máy có IPv4/IPv6 nhưng Java client chỉ kết nối được một nhóm địa chỉ, bạn sẽ chẩn đoán DNS result và routing ra sao?
Nếu URL do user nhập trỏ tới internal metadata service sau redirect, bạn sẽ thiết kế chặn SSRF ở từng bước như thế nào?
Nếu ServerSocket.accept bị block trong lúc shutdown, bạn sẽ làm thế nào để dừng listener và giải phóng socket an toàn?
Nếu TCP client đọc một phần frame rồi thấy timeout, bạn sẽ giữ hay hủy decoder state theo deadline và protocol policy nào?
Nếu OutputStream.write hoàn tất nhưng client chưa nhận business response, bạn sẽ phân biệt transport success với application success ra sao?
Nếu message có ký tự tiếng Việt bị cắt vì length header tính theo String.length, bạn sẽ sửa encoding và framing như thế nào?
Nếu UDP receiver đôi khi nhận payload thiếu bytes, bạn sẽ kiểm tra DatagramPacket buffer size và MTU như thế nào?
Nếu UDP message bị nhận trùng sau retry, bạn sẽ dùng sequence number hoặc idempotency key ở tầng ứng dụng ra sao?
Nếu Selector thread sử dụng gần 100% CPU khi không có kết nối bận, bạn sẽ điều tra interestOps và select loop như thế nào?
Nếu SocketChannel.write chỉ gửi một phần payload nhưng code bỏ ByteBuffer, bạn sẽ thiết kế pending queue và resume write như thế nào?
Nếu hai asynchronous read callbacks sửa chung state làm đảo byte order, bạn sẽ tổ chức một state machine theo channel như thế nào?
Nếu AsynchronousSocketChannel trả completion sau khi request đã timeout, bạn sẽ xử lý stale result và cleanup như thế nào?
Nếu TLS handshake thất bại do server certificate không khớp hostname, bạn sẽ kiểm tra SAN, SNI và truststore như thế nào?
Nếu SSLEngine trả BUFFER_UNDERFLOW liên tục, bạn sẽ kiểm tra encrypted input buffer và read loop ra sao?
Nếu HttpClient trả 301 tới host khác kèm yêu cầu authentication, bạn sẽ kiểm soát redirect và headers nhạy cảm như thế nào?
Nếu một HTTP client có nhiều timeout liên tục nhưng server đã thực hiện các POST, bạn sẽ áp dụng idempotency và retry budget ra sao?
Nếu backend đóng idle pooled connections gây Connection reset ngẫu nhiên, bạn sẽ điều chỉnh connection lifecycle và retry có điều kiện như thế nào?
Nếu test networking PASS trên máy developer nhưng flaky ở CI vì ports bị chiếm, bạn sẽ dùng ephemeral port và lifecycle synchronization như thế nào?
Nếu cần xây Java client/server giao tiếp đáng tin cậy qua TCP/UDP, NIO, TLS và HTTP, bạn sẽ thiết kế framing, timeout, proxy, backpressure, diagnostics và kiểm thử như thế nào?
