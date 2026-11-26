Netty thường gắn một Channel với EventLoop nào trong suốt vòng đời đăng ký?
A. EventLoop được chọn lại sau mỗi lần channelRead để cân bằng tải.
B. Channel chuyển EventLoop theo từng callback khi hàng đợi tăng.
C. Mỗi Channel tạo một EventLoop riêng khi kết nối được chấp nhận.
D. Channel giữ EventLoop đã gán trong suốt thời gian hoạt động.
Đáp án đúng: D

Trong Netty server, boss và worker EventLoopGroup thường chia trách nhiệm ra sao?
A. Worker nhận socket mới còn boss xử lý toàn bộ I/O.
B. Boss xử lý nghiệp vụ còn worker chỉ tạo listening socket.
C. Mỗi child Channel dùng boss loop cho đọc ghi và worker để đóng.
D. Boss nhận kết nối mới rồi đăng ký child Channel vào worker.
Đáp án đúng: D

Cách nào xử lý ChannelFuture mà không chặn thread đang gọi thao tác?
A. sync tự chuyển thao tác sang thread pool chung khi cần.
B. Listener chạy khi Future hoàn tất mà không chặn.
C. await chỉ đăng ký callback và luôn trả về ngay lập tức.
D. isSuccess báo thao tác đã xếp hàng dù chưa hoàn tất.
Đáp án đúng: B

Quy trình nào phù hợp để graceful shutdown một EventLoopGroup?
A. Đóng EventLoopGroup ngay lập tức rồi bỏ các Channel còn mở.
B. Giữ group hoạt động để các callback còn lại tự thoát.
C. Xóa handler khỏi pipeline trước khi đóng listening socket.
D. Ngừng nhận kết nối mới, đóng Channel rồi chờ group dừng.
Đáp án đúng: D

Thứ tự duyệt handler trong ChannelPipeline của Netty được mô tả đúng thế nào?
A. Inbound đi từ tail về head, outbound đi từ head tới tail.
B. Cả hai chiều đều đi từ head tới tail theo thứ tự thêm.
C. Cả hai chiều đều đi từ tail về head theo thứ tự thêm.
D. Inbound đi head đến tail; outbound đi tail đến head.
Đáp án đúng: D

Khi nào một handler có thể được đánh dấu @Sharable một cách an toàn?
A. Mọi handler đều cần trạng thái riêng nên không thể chia sẻ.
B. Handler không giữ state riêng và phải thread-safe khi chia sẻ.
C. Annotation @Sharable tự đồng bộ mọi trường mutable trong handler.
D. Chỉ handler outbound mới được chia sẻ giữa các Channel.
Đáp án đúng: B

ctx.write khác channel.write ở điểm bắt đầu duyệt outbound pipeline nào?
A. ctx.write chạy outbound từ head, channel.write chạy inbound từ tail.
B. Hai cách write luôn bắt đầu tại cùng handler trong pipeline.
C. ctx.write bắt đầu tại context; channel.write bắt đầu từ tail.
D. channel.write bỏ qua outbound handler còn ctx.write gọi tất cả.
Đáp án đúng: C

Vì sao ứng dụng TCP dùng Netty thường cần frame decoder?
A. TCP giữ nguyên ranh giới từng message trong mỗi lần đọc.
B. TCP cung cấp byte stream nên ứng dụng phải tự đóng khung.
C. Một lần read luôn chứa đúng một message hoàn chỉnh.
D. TCP gom các lần write của sender thành từng message riêng khi nhận.
Đáp án đúng: B

Decoder nên xử lý thế nào khi mới nhận được một phần frame?
A. Bỏ các byte chưa đủ và chờ lần đọc tiếp theo từ đầu.
B. Phát phần payload hiện có như một message tạm thời.
C. Tạo decoder mới cho mỗi lần read để giữ trạng thái.
D. Giữ byte trong cumulation đến khi đủ frame.
Đáp án đúng: D

Vai trò chính của ByteToMessageDecoder trong xử lý TCP stream là gì?
A. Decoder chỉ chạy một lần cho mỗi socket khi channelActive.
B. Mỗi lần read tạo một instance mới và bỏ decoder cũ.
C. Decoder yêu cầu transport gửi sẵn đúng một frame mỗi lần.
D. Giữ cumulation, gọi decode khi có thêm byte.
Đáp án đúng: D

SimpleChannelInboundHandler thường xử lý reference count của message ra sao?
A. Mặc định auto-release message sau channelRead0.
B. Tự release message chỉ khi channelInactive xảy ra.
C. Không release message vì quyền sở hữu chuyển cho pipeline.
D. Tăng refCnt trước mỗi lần gọi channelRead0 rồi tự cân bằng.
Đáp án đúng: A

Quy tắc nào đúng khi quản lý ByteBuf bằng reference counting?
A. Mỗi lần retain cần một lần release tương ứng.
B. retain giải phóng bộ nhớ còn release tăng reference count.
C. release chỉ đánh dấu buffer không còn writable.
D. Buffer được giải phóng khi readerIndex bằng writerIndex.
Đáp án đúng: A

slice và retainedSlice khác nhau thế nào về reference count?
A. slice sao chép dữ liệu còn retainedSlice tạo vùng nhớ độc lập.
B. Cả hai đều tăng refCnt và cần release riêng sau khi dùng.
C. slice không tăng refCnt; retainedSlice tăng refCnt.
D. retainedSlice sao chép dữ liệu còn slice giữ nguyên buffer gốc.
Đáp án đúng: C

ResourceLeakDetector của Netty chủ yếu giúp phát hiện vấn đề nào?
A. Luôn ghi lại mọi allocation và giải phóng mà không sampling.
B. Tự release ByteBuf bị rò rỉ ngay khi phát hiện trong production.
C. Theo dõi allocation để cảnh báo ByteBuf có thể bị leak.
D. Đo dung lượng heap và báo mọi đối tượng chưa được GC.
Đáp án đúng: C

Đặc điểm nào mô tả đúng pooled ByteBuf allocator?
A. Pooling tái sử dụng vùng nhớ, nhưng lợi ích tùy workload.
B. Direct buffer luôn nhanh hơn và không cần quản lý vòng đời.
C. Pooled allocator loại bỏ reference counting để giảm chi phí.
D. Heap buffer bắt buộc được dùng cho mọi thao tác socket.
Đáp án đúng: A

Channel.isWritable và write buffer watermarks phối hợp thế nào?
A. isWritable chỉ phản ánh socket còn kết nối hay đã đóng.
B. High watermark dừng đọc đầu vào, low watermark đóng Channel.
C. isWritable false trên high, true dưới low watermark.
D. Hai watermark quyết định kích thước tối đa của mỗi ByteBuf.
Đáp án đúng: C

Cách nào triển khai backpressure khi producer ghi nhanh hơn consumer?
A. Tăng queue vô hạn để producer không cần chờ consumer.
B. Bỏ mọi message khi tốc độ ghi của consumer giảm.
C. Tắt TCP_NODELAY để bảo đảm producer gửi ít dữ liệu hơn.
D. Tạm dừng ghi khi buffer đầy, tiếp tục khi giảm.
Đáp án đúng: D

Khi autoRead được đặt false, hành vi đọc inbound của Channel thay đổi thế nào?
A. autoRead=false dừng đọc tự động; gọi read để tiếp tục.
B. autoRead false đóng socket sau khi đọc xong một frame.
C. autoRead false chỉ có tác dụng với UDP datagram.
D. autoRead false chuyển việc đọc sang một EventLoop khác.
Đáp án đúng: A

Cách nào phù hợp khi handler cần thực hiện blocking I/O?
A. Gọi blocking API trên EventLoop nhưng đặt timeout thật ngắn.
B. Dùng sync để chờ I/O hoàn tất trước khi xử lý tiếp.
C. Tạo một EventLoop mới cho từng truy vấn database đồng bộ.
D. Chuyển I/O chặn sang executor, trả kết quả về EventLoop.
Đáp án đúng: D

Làm sao giữ thứ tự xử lý khi offload tác vụ của cùng một Channel?
A. Tuần tự hóa theo Channel, cập nhật state trên EventLoop.
B. Cho mọi callback chạy trên common pool không cần thứ tự.
C. Dùng nhiều executor tùy ý để giảm hàng đợi từng Channel.
D. Để worker thread sửa trực tiếp trạng thái Channel cùng lúc.
Đáp án đúng: A

TCP_NODELAY thường được bật nhằm đạt mục tiêu nào?
A. SO_KEEPALIVE gửi probe định kỳ để phát hiện kết nối chết.
B. SO_BACKLOG giới hạn byte chờ trong outbound buffer.
C. CONNECT_TIMEOUT_MILLIS đặt thời gian sống của session TCP.
D. TCP_NODELAY tắt Nagle để gửi dữ liệu nhỏ sớm hơn.
Đáp án đúng: D

Đặc điểm nào đúng với UDP DatagramChannel trong Netty?
A. UDP bảo đảm giao nhận một lần nhưng không giữ thứ tự.
B. UDP giữ ranh giới gói, không bảo đảm giao nhận hoặc thứ tự.
C. DatagramChannel ghép nhiều datagram nhận được thành một byte stream liên tục.
D. UDP tự truyền lại gói mất khi nhận thấy checksum sai.
Đáp án đúng: B

Thiết kế payload UDP nào giúp giảm nguy cơ IP fragmentation?
A. Chia payload thành nhiều datagram nhưng không cần sequence.
B. Trừ header IP/UDP và giao thức khỏi PMTU.
C. Dựa vào TCP_NODELAY để ngăn IP fragmentation trên UDP.
D. Tăng datagram tới giới hạn 64 KB để tránh fragmentation.
Đáp án đúng: B

SslHandler nên được đặt ở đâu so với frame decoder trong pipeline?
A. Đặt SslHandler trước frame decoder để giải mã trước.
B. Đặt frame decoder trước SslHandler để giải mã TLS thành frame.
C. Đặt codec trước SslHandler theo cả hai chiều pipeline.
D. Đặt SslHandler sau outbound socket handler để xử lý plaintext.
Đáp án đúng: A

Client xác minh máy chủ TLS đúng cách cần kiểm tra điều gì?
A. Chỉ kiểm tra certificate còn hạn, không cần kiểm tra hostname.
B. Xác minh chain tới trust anchor và hostname theo SAN.
C. Chấp nhận mọi certificate nếu TLS handshake hoàn tất thành công.
D. Tắt hostname verification khi kết nối bằng DNS name.
Đáp án đúng: B

Trong mutual TLS, server cần làm gì để xác thực client?
A. Client chỉ gửi username trong header sau TLS handshake.
B. Server dùng certificate của mình để suy ra danh tính client.
C. Server xác minh client certificate rồi ánh xạ danh tính.
D. Client certificate hợp lệ tự động cấp quyền mọi endpoint.
Đáp án đúng: C

Ứng dụng Netty nên theo dõi TLS handshake như thế nào?
A. Chỉ kiểm tra channelActive vì TLS handshake luôn hoàn tất trước callback.
B. Gọi sync trên EventLoop để chờ TLS handshake hoàn tất.
C. Dùng listener của handshakeFuture để xử lý thành công hoặc lỗi.
D. Bỏ handshake event và kiểm tra certificate khi channelInactive.
Đáp án đúng: C

Có thể kiểm thử decoder nhận frame bị chia nhỏ bằng EmbeddedChannel ra sao?
A. Dùng socket thật để buộc decoder nhận một frame mỗi lần.
B. Ghi từng mảnh vào EmbeddedChannel; chỉ phát frame đủ.
C. Ghi toàn bộ frame một lần và chỉ kiểm tra số byte cuối.
D. Tạo decoder mới cho từng đoạn để không cần cumulation.
Đáp án đúng: B

Cách nào giúp dọn message còn tồn đọng sau bài test EmbeddedChannel?
A. finish chỉ đóng channel, còn message queue tự được GC.
B. finishAndReleaseAll giữ buffer để test khác dùng tiếp.
C. finishAndReleaseAll giải phóng message còn chờ.
D. runPendingTasks tự release mọi inbound và outbound message.
Đáp án đúng: C

Giới hạn quan trọng nào của EmbeddedChannel cần nhớ khi kiểm thử?
A. EmbeddedChannel kiểm thử handler; socket/TLS cần integration test.
B. EmbeddedChannel mô phỏng đầy đủ kernel TCP và mọi network failure.
C. EmbeddedChannel xác minh certificate qua trust store hệ điều hành.
D. EmbeddedChannel đo chính xác throughput của nhiều kết nối thật.
Đáp án đúng: A

Cách xử lý exceptionCaught nào phù hợp khi lỗi giao thức khiến Channel không thể tiếp tục?
A. Nuốt mọi exception để giữ channel luôn hoạt động.
B. Ghi nhận lỗi, đóng Channel nếu không thể tiếp tục.
C. Chỉ ghi exception rồi tiếp tục pipeline như không có lỗi.
D. Chuyển exception thành inbound message rồi bỏ qua pipeline.
Đáp án đúng: B

Metric nào phản ánh trực tiếp EventLoop bị chậm xử lý task?
A. Đếm tổng số Channel đã từng mở từ khi process khởi động.
B. Theo dõi heap used một lần mỗi giờ là đủ để đo lag.
C. Đo EventLoop lag và thời gian xử lý handler.
D. Đếm số message đã decode mà không theo dõi thời gian xử lý.
Đáp án đúng: C

Nhận định nào đúng khi lựa chọn native transport như epoll hoặc kqueue?
A. Native transport luôn chạy trên mọi hệ điều hành và JVM.
B. Epoll hoặc kqueue cải thiện hiệu quả trên hệ điều hành hỗ trợ.
C. NIO chỉ hoạt động khi có epoll hoặc kqueue được cài đặt.
D. Native transport làm thay đổi ngữ nghĩa xử lý của ChannelPipeline.
Đáp án đúng: B

Cách nào phù hợp để offload tác vụ blocking khỏi EventLoop?
A. Executor giới hạn tác vụ; callback về EventLoop.
B. Tạo thread mới cho mỗi request và không giới hạn số thread.
C. Chạy blocking task trong EventLoop nhưng chia nhỏ bằng sleep.
D. Đưa tác vụ vào queue không giới hạn để tránh từ chối request.
Đáp án đúng: A

Điều gì có thể xảy ra nếu gọi sync trên Future ngay trong EventLoop?
A. Chờ Future trên EventLoop có thể chặn loop hoặc gây deadlock.
B. sync luôn chạy callback trên thread hiện tại nên không thể block.
C. await tự phát hiện EventLoop và chuyển việc chờ sang worker.
D. sync chỉ hợp lệ trước khi Channel được đăng ký EventLoop.
Đáp án đúng: A

Cách nào bảo vệ decoder trước frame có độ dài do peer khai báo quá lớn?
A. Chỉ kiểm tra length sau khi cấp phát buffer theo độ dài nhận được.
B. Cho phép frame lớn rồi dựa vào idle timeout để giải phóng.
C. Đặt max frame length và từ chối frame vượt giới hạn.
D. Giảm readerIndex khi vượt giới hạn để tiếp tục decode.
Đáp án đúng: C
