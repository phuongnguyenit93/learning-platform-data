Một server Netty nhận nhiều kết nối nhưng một Channel bị xử lý chậm làm các kết nối khác trên cùng EventLoop cũng tăng latency; nhóm vận hành chưa hiểu một EventLoop thường phục vụ nhiều Channel và callback chạy tuần tự trên thread đó.
Ứng dụng gọi Thread.sleep() trong ChannelInboundHandler để chờ hệ thống bên ngoài; EventLoop bị chặn và mọi Channel được đăng ký trên loop đó ngừng xử lý I/O trong thời gian chờ.
Một handler gọi JDBC truy vấn đồng bộ ngay trong channelRead(); khi database chậm, EventLoop không xử lý kịp socket readiness và hàng loạt kết nối bị timeout.
Nhóm dùng Future.get() trên EventLoop để chờ kết quả từ worker pool; worker lại cần gửi callback về EventLoop nên hai phía chờ nhau và pipeline không tiến triển.
Một handler offload xử lý message sang executor không giới hạn; khi downstream chậm, hàng đợi task tăng vô hạn và heap của server tăng cho tới khi OOM.
Nhóm dùng một EventLoopGroup cho client và server với số thread quá ít; tác vụ TLS handshake và business callback cùng tranh thread, khiến thời gian đăng ký Channel và xử lý I/O tăng.
Ứng dụng lưu ChannelHandler dùng chung cho nhiều Channel nhưng handler có field mutable giữ trạng thái request; dữ liệu của các kết nối trộn lẫn do handler không thread-safe.
Nhóm đánh dấu handler @Sharable dù handler vẫn giữ ByteBuf và trạng thái phiên trong field; cùng một instance được dùng ở nhiều pipeline và gây lỗi tham chiếu hoặc rò rỉ dữ liệu.
Một ChannelInboundHandler ghi response nhưng quên gọi fireChannelRead() cho message cần chuyển tiếp; các handler phía sau không nhận được dữ liệu dù socket đã đọc thành công.
Nhóm thêm ChannelOutboundHandler chứa encoder ở đầu pipeline thay vì vị trí phù hợp; write() bắt đầu từ tail và đi ngược qua outbound handlers nên encoder không được gọi.
Pipeline có nhiều handler cùng xử lý exception nhưng handler đầu tiên không gọi fireExceptionCaught(); lỗi bị nuốt và nhóm không thấy stack trace ở logging handler cuối.
Một ChannelHandler ném exception trong channelRead() nhưng không đóng hoặc giải phóng ByteBuf; lỗi lan tới exceptionCaught và buffer bị giữ lại ngoài ý muốn.
TCP client gửi một message dài nhưng server nhận thành nhiều lần channelRead(); nhóm giả định một lần read tương ứng một message và parser xử lý thiếu dữ liệu.
TCP client gửi nhiều request nhỏ liên tiếp nhưng server nhận gộp trong một lần read; decoder không tách frame nên hai request bị hiểu thành một payload.
Ứng dụng dùng LengthFieldBasedFrameDecoder nhưng cấu hình lengthFieldOffset và lengthAdjustment không khớp header thực tế; frame bị cắt ngắn hoặc chờ thêm byte vô hạn.
Length field do client gửi có giá trị rất lớn; decoder cấp phát hoặc giữ buffer chờ payload quá lớn, tạo nguy cơ DoS và áp lực bộ nhớ.
Nhóm dùng ObjectEncoder/ObjectDecoder cho dữ liệu không tin cậy; payload có thể kích hoạt deserialization nguy hiểm và kích thước object không được giới hạn.
UDP server dùng DatagramPacket nhưng giả định datagram lớn sẽ được phân mảnh và ghép lại an toàn ở mọi mạng; gói vượt MTU bị mất hoặc phân mảnh gây giảm độ tin cậy.
Ứng dụng dùng UDP để truyền sự kiện cần đảm bảo thứ tự; nhóm không có sequence number, retry hoặc deduplication nên mất và đảo thứ tự datagram làm sai trạng thái.
Nhóm chuyển server từ NIO sang native epoll transport nhưng image production thiếu thư viện native phù hợp; ứng dụng fallback hoặc khởi động lỗi khác với môi trường phát triển.
Channel bị đóng sau khi client reset kết nối; nhóm chỉ lắng nghe channelInactive mà không phân biệt channelUnregistered, exceptionCaught và nguyên nhân close để xử lý reconnect.
Client gọi connect() rồi gọi sync() trên EventLoop; thao tác chờ đồng bộ chặn loop và làm các Channel khác trên loop không được phục vụ.
Ứng dụng gọi writeAndFlush() liên tục mà không theo dõi ChannelFuture; khi socket đóng giữa lúc gửi, lỗi ghi không được xử lý và dữ liệu bị coi nhầm là đã chuyển thành công.
Server chỉ gọi write() mà quên flush(); dữ liệu vẫn nằm trong outbound buffer và client không nhận response cho tới khi có lần flush khác.
ByteBuf được tạo bằng Unpooled.buffer() trong mỗi request và không được release sau khi encode; leak detector phát cảnh báo và direct memory tăng dần.
Handler gọi ctx.fireChannelRead(msg) rồi tiếp tục đọc ByteBuf để log payload; handler sau đã release buffer khiến thao tác đọc tiếp theo báo IllegalReferenceCountException.
Một handler giữ ByteBuf để xử lý bất đồng bộ nhưng không gọi retain() trước khi trả khỏi callback; buffer bị release bởi pipeline trước khi worker sử dụng.
Nhóm gọi retain() khi chuyển ByteBuf sang worker nhưng quên release() sau khi xử lý; reference count không về zero và bộ nhớ direct bị giữ lâu dài.
Code gọi release() hai lần trên cùng ByteBuf do cả handler hiện tại và downstream cùng nghĩ mình sở hữu buffer; lỗi IllegalReferenceCountException xuất hiện dưới tải.
CompositeByteBuf ghép nhiều thành phần nhưng chỉ release composite ở một nhánh xử lý; component buffer còn reference và memory leak detector báo leak sau khi client ngắt kết nối.
Ứng dụng dùng pooled ByteBuf allocator nhưng đo heap JVM để kết luận bộ nhớ ổn định; direct memory tăng ngoài heap và container bị OOM dù heap chưa chạm giới hạn.
Nhóm chuyển từ heap ByteBuf sang direct ByteBuf để giảm copy nhưng thao tác codec vẫn sao chép sang byte array; chi phí allocation tăng mà lợi ích direct memory không đạt.
Leak detector đặt ở mức disabled trong production để giảm overhead; một đường code quên release chỉ bị phát hiện khi bật PARANOID trong test.
Server gửi dữ liệu lớn tới client chậm bằng writeAndFlush() liên tục; ứng dụng không kiểm tra isWritable() hoặc channelWritabilityChanged() nên outbound buffer tăng và direct memory cạn.
Nhóm đặt WRITE_BUFFER_WATER_MARK quá cao để giảm trạng thái non-writable; outbound buffer giữ quá nhiều dữ liệu và tiến trình tiêu thụ bộ nhớ lớn khi client chậm.
Server nhận dữ liệu nhanh hơn worker xử lý; autoRead vẫn bật nên inbound buffer và queue task tăng vô hạn dù EventLoop vẫn hoạt động.
Ứng dụng tắt autoRead khi queue đầy nhưng không bật lại sau khi worker xử lý xong; kết nối dừng nhận dữ liệu dù backpressure đã hết.
Nhóm bật autoRead=false trong channelReadComplete() nhưng không có cơ chế phối hợp giữa nhiều handler; một handler bật đọc lại quá sớm và phá vỡ giới hạn queue.
Nhóm dùng TCP_NODELAY để giảm độ trễ nhưng gửi nhiều message cực nhỏ; packet rate tăng mạnh và CPU kernel cao hơn lợi ích latency thu được.
TCP server đặt SO_BACKLOG thấp trong đợt nhiều client reconnect; kết nối bị từ chối hoặc timeout trước khi application accept kịp.
Client không đặt connect timeout và giữ Future chờ lâu khi endpoint mất route; request thread bị chiếm và retry đồng thời làm tăng tải.
Ứng dụng dùng IdleStateHandler để phát heartbeat nhưng không xử lý ALL_IDLE hoặc WRITER_IDLE đúng cách; kết nối sống bị đóng dù peer vẫn hoạt động.
TLS SslHandler được thêm sai thứ tự trong pipeline; application encoder chạy trước khi dữ liệu được mã hóa và peer nhận plaintext hoặc handshake lỗi.
Client TLS không xác minh hostname của certificate; kết nối được mã hóa nhưng vẫn có thể bị chuyển hướng tới máy chủ giả mạo.
Server TLS không gửi đủ certificate chain; một số client tin CA gốc vẫn không xác minh được chứng chỉ do thiếu intermediate certificate.
Nhóm bật TLS nhưng không xử lý handshake future; ứng dụng gửi application data trước khi handshake hoàn tất và nhận lỗi protocol.
Ứng dụng dùng SslHandler nhưng không xử lý close_notify khi đóng Channel; peer ghi nhận TLS truncation hoặc mất dữ liệu cuối phiên.
EmbeddedChannel test decoder với một ByteBuf hoàn chỉnh nhưng không test trường hợp frame đến thành nhiều mảnh; lỗi framing chỉ xuất hiện trong mạng thật.
Test EmbeddedChannel gọi writeInbound() nhưng quên kiểm tra inboundMessages; decoder có thể bỏ message mà test vẫn pass do chỉ xác minh không có exception.
Unit test pipeline gọi finish() nhưng không release message còn trong EmbeddedChannel; test suite tích lũy ByteBuf và leak detector phát cảnh báo không ổn định.
Nhóm test outbound encoder bằng writeInbound() thay vì writeOutbound(); test không đi qua đúng chiều pipeline và không phát hiện lỗi encode.
Test ByteBuf reference counting chỉ xác nhận nội dung byte mà không assert refCnt về zero sau finishAndReleaseAll(); đường leak không bị phát hiện.
Nhóm dùng EmbeddedChannel để test SslHandler như thể nó thay thế đầy đủ TLS socket thực; handshake, certificate validation và transport behavior cần được kiểm chứng thêm ở integration test.
Pipeline test không mô phỏng exceptionCaught và channelInactive; handler giải phóng ByteBuf đúng ở happy path nhưng rò rỉ khi peer reset kết nối.
Ứng dụng Netty có benchmark throughput tốt trên localhost nhưng không thử client chậm, packet loss và network latency; backpressure và reconnect behavior thất bại khi chạy production.
Server Netty bị CPU cao nhưng dashboard chỉ theo dõi process CPU; không có metric event loop task queue, pending writes, channel count và allocator usage để xác định nút thắt.
Một ứng dụng tạo Channel nhưng không đóng khi client idle; số channel active tăng liên tục và file descriptor của process tiến gần giới hạn hệ điều hành.
Client reconnect ngay lập tức trong vòng lặp khi server đóng kết nối; hàng nghìn reconnect cùng lúc tạo connection storm và làm EventLoopGroup cùng server quá tải.
Server gọi shutdownGracefully() nhưng không chờ Future hoàn tất; process kết thúc trước khi event loop dừng và tài nguyên native chưa được giải phóng.
Nhóm chia sẻ một ByteBuf qua nhiều Channel để broadcast nhưng không retain theo từng lần chuyển ownership; một channel release buffer làm các channel còn lại đọc buffer đã giải phóng.
Ứng dụng nhận frame hợp lệ nhưng không giới hạn kích thước trước khi decode thành object; client gửi payload khổng lồ làm CPU và memory tăng, tạo điểm DoS qua protocol.
Một ChannelPipeline có decoder, decompressor và object mapper xử lý dữ liệu không tin cậy; không giới hạn decompressed size khiến payload nén nhỏ mở rộng thành dữ liệu rất lớn.
Nhóm đặt timeout ở HTTP layer nhưng không có timeout cho protocol TCP tùy chỉnh; peer mở kết nối và gửi header từng byte rất chậm, giữ Channel và decoder state trong thời gian dài.
Một service Netty xử lý TCP và UDP trong cùng EventLoopGroup nhưng handler UDP thực hiện công việc blocking; datagram processing làm chậm cả các Channel TCP dùng chung loop.
Nhóm triển khai Netty server sau load balancer nhưng không xử lý proxy protocol; địa chỉ client được ghi nhận thành IP của load balancer và chính sách giới hạn kết nối theo IP hoạt động sai.
