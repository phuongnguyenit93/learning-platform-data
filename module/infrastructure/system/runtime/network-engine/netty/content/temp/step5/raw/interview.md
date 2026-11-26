Bạn giải thích Netty giải quyết những bài toán nào khi xây dựng ứng dụng client/server mạng bất đồng bộ trong Java?
Bạn phân biệt mô hình blocking I/O truyền thống với non-blocking I/O mà Netty sử dụng như thế nào?
Bạn mô tả kiến trúc Reactor trong Netty và vai trò của EventLoopGroup, EventLoop cùng Channel như thế nào?
Vì sao một EventLoop thường xử lý nhiều Channel và một Channel thường gắn với một EventLoop trong suốt vòng đời hoạt động?
Bạn phân biệt boss EventLoopGroup và worker EventLoopGroup trong cấu hình Netty server như thế nào?
Bạn lựa chọn số lượng EventLoop và thread dựa trên số lõi CPU, số kết nối và đặc điểm workload như thế nào?
Bạn mô tả vòng đời Channel từ lúc đăng ký với EventLoop, kết nối, hoạt động đến khi đóng như thế nào?
Bạn phân biệt Channel, ChannelHandlerContext và ChannelPipeline về trách nhiệm và phạm vi sử dụng như thế nào?
Bạn giải thích ChannelFuture và ChannelPromise hỗ trợ theo dõi thao tác bất đồng bộ trong Netty như thế nào?
Bạn xử lý kết quả connect, bind, write và close bất đồng bộ mà không chặn thread gọi như thế nào?
Bạn phân biệt addListener với sync hoặc await trên ChannelFuture và đánh giá rủi ro khi chờ đồng bộ trên EventLoop ra sao?
Bạn thiết kế quy trình graceful shutdown cho EventLoopGroup để đóng kết nối và giải phóng tài nguyên an toàn như thế nào?
Bạn sử dụng ServerBootstrap và Bootstrap để cấu hình server và client Netty với những khác biệt nào?
Bạn lựa chọn ChannelOption như SO_BACKLOG, SO_KEEPALIVE, TCP_NODELAY và CONNECT_TIMEOUT_MILLIS dựa trên mục tiêu nào?
Bạn phân biệt channel option áp dụng cho parent channel và child channel trong server bootstrap như thế nào?
Bạn lựa chọn NIO transport hoặc native transport như epoll và kqueue dựa trên hệ điều hành, khả năng triển khai và workload ra sao?
Bạn thiết kế ChannelInitializer để cài đặt pipeline cho mỗi kết nối mới mà không chia sẻ nhầm trạng thái giữa các Channel như thế nào?
Bạn mô tả cách ChannelPipeline tổ chức inbound và outbound handler trong một kết nối Netty như thế nào?
Bạn giải thích thứ tự gọi inbound handler theo chiều tiến và outbound handler theo chiều ngược trong pipeline như thế nào?
Bạn phân biệt ChannelInboundHandler, ChannelOutboundHandler và ChannelDuplexHandler theo loại sự kiện được xử lý như thế nào?
Bạn xác định thời điểm dùng channelRead, channelReadComplete, channelActive, channelInactive và exceptionCaught như thế nào?
Bạn chuyển tiếp sự kiện bằng ctx.fireChannelRead hoặc ctx.writeAndFlush và giải thích ảnh hưởng của vị trí handler trong pipeline ra sao?
Bạn thiết kế handler stateless có thể dùng chung giữa nhiều Channel và xác định khi nào cần đánh dấu @Sharable như thế nào?
Bạn quản lý trạng thái riêng cho từng kết nối khi handler được chia sẻ để tránh race condition hoặc rò rỉ dữ liệu giữa Channel như thế nào?
Bạn phân biệt ctx.write với channel.write về vị trí bắt đầu duyệt outbound handler trong pipeline như thế nào?
Bạn xử lý exception trong pipeline để phân biệt lỗi giao thức, lỗi kết nối và lỗi nghiệp vụ như thế nào?
Bạn quyết định handler nào nên đặt trước hoặc sau TLS handler, frame decoder và message codec trong pipeline như thế nào?
Bạn giải thích vì sao TCP cung cấp luồng byte và ứng dụng Netty phải tự xác định ranh giới message như thế nào?
Bạn so sánh LengthFieldBasedFrameDecoder, LineBasedFrameDecoder và delimiter-based framing theo định dạng giao thức như thế nào?
Bạn thiết kế custom frame decoder để xử lý header, payload length và message không đầy đủ qua nhiều lần đọc như thế nào?
Bạn xử lý trường hợp một lần channelRead chứa nhiều message hoặc chỉ chứa một phần message như thế nào?
Bạn phân biệt ByteToMessageDecoder, MessageToMessageDecoder và MessageToMessageEncoder theo kiểu dữ liệu đầu vào và đầu ra như thế nào?
Bạn lựa chọn codec JSON, Protobuf hoặc codec nhị phân tùy theo yêu cầu tương thích, kích thước và tốc độ xử lý ra sao?
Bạn thiết kế protocol versioning để client cũ và server mới có thể giao tiếp trong giai đoạn nâng cấp như thế nào?
Bạn xử lý message sai định dạng hoặc payload vượt giới hạn để bảo vệ server khỏi lỗi giải mã và tiêu thụ bộ nhớ quá mức ra sao?
Bạn so sánh transport TCP và UDP trong Netty về độ tin cậy, thứ tự dữ liệu và cách tổ chức Channel như thế nào?
Bạn cấu hình DatagramChannel và DatagramPacket để gửi, nhận UDP datagram mà vẫn giữ ranh giới từng gói như thế nào?
Bạn đánh giá giới hạn kích thước datagram, nguy cơ fragmentation và mất gói khi thiết kế giao thức UDP như thế nào?
Bạn xử lý việc UDP không có kết nối và không bảo đảm delivery bằng timeout, sequence number hoặc cơ chế xác nhận ở tầng ứng dụng như thế nào?
Bạn giải thích ByteBuf khác ByteBuffer của Java về readerIndex, writerIndex, capacity và khả năng mở rộng như thế nào?
Bạn sử dụng readerIndex, writerIndex, markReaderIndex và resetReaderIndex để đọc protocol header mà không làm mất dữ liệu chưa xử lý như thế nào?
Bạn phân biệt heap buffer, direct buffer, pooled buffer và unpooled buffer trong Netty về cấp phát và hiệu năng như thế nào?
Bạn lựa chọn pooled allocator hoặc unpooled allocator theo workload và cách đo thực tế như thế nào?
Bạn giải thích reference counting của ByteBuf và ý nghĩa của refCnt, retain và release trong quản lý vòng đời bộ nhớ như thế nào?
Bạn xác định handler nào chịu trách nhiệm release ByteBuf khi message được chuyển tiếp, giữ lại hoặc bị loại bỏ như thế nào?
Bạn phân biệt SimpleChannelInboundHandler với ChannelInboundHandlerAdapter về hành vi auto-release message như thế nào?
Bạn xử lý ByteBuf được lưu để dùng sau khi channelRead kết thúc bằng retainedDuplicate, retainedSlice hoặc retain như thế nào?
Bạn đánh giá rủi ro khi giữ một slice của ByteBuf lớn và tác động đến thời điểm giải phóng vùng nhớ gốc ra sao?
Bạn phát hiện và điều tra memory leak do thiếu release hoặc release nhiều lần bằng ResourceLeakDetector như thế nào?
Bạn lựa chọn mức leak detection phù hợp giữa môi trường phát triển, kiểm thử và production như thế nào?
Bạn giải thích vì sao ByteBuf có thể gây lỗi use-after-release hoặc IllegalReferenceCountException và thiết kế kiểm thử để bắt lỗi này ra sao?
Bạn phân biệt write, flush và writeAndFlush trong pipeline Netty về thời điểm dữ liệu được đẩy xuống transport như thế nào?
Bạn giải thích Channel.isWritable và write buffer watermarks phản ánh áp lực ghi dữ liệu như thế nào?
Bạn thiết kế backpressure để producer giảm tốc độ phát dữ liệu khi outbound buffer của Channel vượt ngưỡng như thế nào?
Bạn sử dụng ChannelWritabilityChanged để tạm dừng hoặc tiếp tục đọc dữ liệu đầu vào dựa trên trạng thái writable như thế nào?
Bạn phân biệt autoRead với thao tác read thủ công và xác định khi nào cần điều tiết inbound flow như thế nào?
Bạn xử lý tình huống producer gửi nhanh hơn consumer khiến pending write queue tăng liên tục như thế nào?
Bạn lựa chọn high watermark và low watermark để cân bằng thông lượng, bộ nhớ và độ trễ như thế nào?
Bạn thiết kế giới hạn số message hoặc số byte đang chờ xử lý trên mỗi kết nối để tránh một client chiếm hết tài nguyên ra sao?
Bạn đánh giá tác động của batch write và flush theo lô đến throughput và latency như thế nào?
Bạn tránh tạo hàng đợi vô hạn khi đưa công việc từ EventLoop sang worker pool và xác định chính sách từ chối hoặc giảm tải ra sao?
Bạn giải thích vì sao không được gọi thao tác blocking như truy vấn JDBC, đọc file đồng bộ hoặc sleep trên EventLoop như thế nào?
Bạn nhận diện EventLoop bị block từ latency, pending task, thread dump hoặc log như thế nào?
Bạn tổ chức offload tác vụ CPU-bound hoặc blocking I/O sang executor riêng và quay lại EventLoop để ghi response như thế nào?
Bạn kiểm soát thứ tự xử lý và truy cập trạng thái Channel khi callback từ worker pool quay lại EventLoop như thế nào?
Bạn đánh giá nguy cơ deadlock hoặc thread starvation khi EventLoop chờ Future được hoàn tất bởi chính executor đang bị chặn ra sao?
Bạn cấu hình SslContext và SslHandler để thiết lập TLS cho Netty client hoặc server như thế nào?
Bạn xác định vị trí đặt SslHandler trong pipeline để mã hóa và giải mã dữ liệu đúng thứ tự với frame decoder và codec ra sao?
Bạn theo dõi TLS handshake completion và xử lý handshake failure hoặc certificate validation error như thế nào?
Bạn cấu hình xác minh hostname, trust material và client certificate để bảo vệ kết nối TLS như thế nào?
Bạn triển khai mutual TLS để xác thực client và server, đồng thời ánh xạ danh tính chứng chỉ vào quyền ứng dụng ra sao?
Bạn xử lý certificate rotation và cập nhật SslContext mà không làm gián đoạn các kết nối đang hoạt động như thế nào?
Bạn đánh giá tác động của TLS handshake, session reuse và mã hóa dữ liệu đến CPU và latency như thế nào?
Bạn sử dụng EmbeddedChannel để kiểm thử inbound handler, outbound handler và codec mà không cần mở socket thật như thế nào?
Bạn viết test cho decoder khi nhận frame bị chia nhỏ qua nhiều lần writeInbound và khi nhiều frame đến cùng lúc như thế nào?
Bạn kiểm tra outbound encoding bằng writeOutbound và xác minh ByteBuf hoặc message kết quả như thế nào?
Bạn sử dụng finish, finishAndReleaseAll, runPendingTasks và runScheduledPendingTasks để kiểm soát vòng đời EmbeddedChannel trong test như thế nào?
Bạn kiểm thử handler ném exception, đóng Channel hoặc thay đổi trạng thái pipeline bằng EmbeddedChannel như thế nào?
Bạn thiết kế test cho reference counting để phát hiện leak, double release và use-after-release trong handler như thế nào?
Bạn kiểm thử backpressure và ChannelWritabilityChanged mà không phụ thuộc vào timing của mạng thật như thế nào?
Bạn kiểm thử TLS handler hoặc handshake behavior ở cấp tích hợp và phân biệt phần nào phù hợp với EmbeddedChannel như thế nào?
Bạn lựa chọn metric và log nào để theo dõi active channels, connection rate, bytes, event loop lag, queue depth và lỗi codec như thế nào?
Bạn chẩn đoán tình huống kết nối tăng nhưng throughput giảm bằng cách đối chiếu EventLoop utilization, backpressure và thời gian xử lý handler như thế nào?
Bạn điều tra sự cố CPU cao hoặc latency tăng sau khi thêm một handler mới bằng profiler và thread dump như thế nào?
Bạn phân biệt lỗi network reset, timeout, TLS failure, protocol decode failure và application exception qua pipeline events như thế nào?
Bạn thiết kế load test cho Netty server để đo throughput, p95/p99 latency, memory usage và số kết nối đồng thời như thế nào?
Bạn xây dựng quy trình shutdown và kiểm thử end-to-end để chứng minh Netty client/server xử lý đúng framing, backpressure, TLS và giải phóng ByteBuf như thế nào?
