Một API Spring WebFlux gọi JDBC repository trực tiếp bên trong map trên Reactor Netty event loop; vài truy vấn chậm giữ các event loop thread và nhiều request HTTP không liên quan cùng bị trễ dù CPU tổng còn thấp.
Nhóm chuyển lệnh block() sang đoạn sau publishOn nhưng lệnh blocking vẫn được thực thi trước khi đổi scheduler; ứng dụng tiếp tục chặn thread reactor-http-nio và phát cảnh báo blocking call.
Ứng dụng gọi thư viện mã hóa đồng bộ tốn CPU trên event loop; khi payload lớn xuất hiện, event loop không kịp xử lý I/O dù không có thao tác network nào bị nghẽn.
Nhóm đưa toàn bộ xử lý blocking sang boundedElastic nhưng tạo scheduler riêng không giới hạn và không dispose; số thread tăng dần khi tải cao và tiến trình tiêu thụ nhiều bộ nhớ.
Ứng dụng dùng Reactor Netty global resources trong nhiều test integration; test tạo và dispose tài nguyên dùng chung không đúng vòng đời khiến test khác lỗi kết nối ngẫu nhiên.
Một service tạo LoopResources mới cho mỗi WebClient thay vì tái sử dụng; số event loop group và thread tăng theo số client, gây overhead và khó kiểm soát shutdown.
Ứng dụng gọi disposeLater cho ConnectionProvider dùng chung khi một bean bị đóng; các client khác đang chạy không lấy được connection mới sau khi một thành phần kết thúc vòng đời.
HttpServer được bind trên cổng cấu hình nhưng bind address chỉ là loopback trong container; health check nội bộ thành công còn traffic từ service khác nhận connection refused.
Một HttpServer xử lý request body lớn bằng cách gom toàn bộ thành byte array trước khi parse; nhiều request đồng thời làm heap tăng mạnh và GC pause kéo dài.
TCP server dùng receive().asString() để giả định mỗi lần nhận là một message hoàn chỉnh; TCP có thể chia một message qua nhiều buffer hoặc gộp nhiều message nên parser đọc sai ranh giới.
Một TcpClient gửi các message JSON liên tiếp trên cùng socket nhưng không có length prefix hoặc delimiter framing; phía server không thể xác định điểm kết thúc của từng message.
TCP client chỉ xử lý inbound receive stream mà không giám sát connection.onDispose; socket bị đóng từ xa nhưng ứng dụng giữ trạng thái session cũ và không reconnect đúng cách.
Ứng dụng gọi outbound.send(Flux) nhưng không subscribe hoặc nối vào send().then(); dữ liệu không được ghi ra socket dù publisher đã được tạo.
Một TCP client tái sử dụng Connection sau khi remote peer đóng socket; lần write tiếp theo thất bại với connection reset và logic retry không tạo connection mới.
HTTP client gọi endpoint nội bộ qua DNS nhưng resolver cache giữ IP cũ sau khi service được thay pod; kết nối tiếp tục thất bại cho tới khi cache hết hạn.
Reactor Netty HttpClient có nhiều request đồng thời nhưng maxConnections đặt quá thấp; pending acquire tăng, request chờ lấy connection và response timeout xuất hiện trước khi request được gửi.
Pool đạt maxConnections trong khi backend vẫn khỏe; pendingAcquireTimeout quá ngắn làm request thất bại khi chờ slot dù connection hiện tại sẽ sớm được trả về.
Ứng dụng tăng maxConnections rất cao để xóa pending acquire nhưng backend có giới hạn connection thấp; database proxy hoặc upstream bị quá tải và tỷ lệ 5xx tăng.
ConnectionProvider dùng maxIdleTime dài hơn idle timeout của load balancer; pool tái sử dụng socket đã bị middlebox đóng và request đầu tiên trên connection stale thất bại.
Pool giữ connection quá lâu qua nhiều lần deploy backend; maxLifeTime chưa được cấu hình nên các socket cũ tiếp tục được tái sử dụng sau khi upstream thay đổi topology.
Ứng dụng tạo ConnectionProvider mới theo từng request để cấu hình timeout động; pool không được tái sử dụng, số socket và thread quản lý tăng mạnh.
HttpClient dùng một ConnectionProvider cho nhiều host nhưng cấu hình giới hạn pool không phù hợp với tải lệch; một upstream chiếm slot và các host khác bị pending acquire.
Client nhận response headers nhưng không consume hoặc release response body khi nhánh xử lý lỗi; connection không được trả lại pool và pending acquire tăng theo thời gian.
Một WebClient filter đọc response body để log rồi trả tiếp response đã bị tiêu thụ; controller downstream nhận body rỗng hoặc lỗi decode vì publisher chỉ được tiêu thụ một lần.
Ứng dụng đặt connectTimeout 2 giây nhưng không cấu hình responseTimeout; TCP connection thiết lập nhanh còn server xử lý chậm vô thời hạn và request treo lâu hơn SLA.
Nhóm cấu hình responseTimeout nhưng tưởng đây là deadline tổng cho toàn bộ chuỗi reactive; các bước chờ pool, DNS hoặc retry vẫn kéo dài vượt thời gian nghiệp vụ cho phép.
HttpClient đặt ReadTimeoutHandler và WriteTimeoutHandler ở channel pipeline dùng chung connection pool; timeout handler còn sót sau một request có thể ảnh hưởng request tiếp theo trên connection tái sử dụng.
TCP client chỉ đặt connect timeout; sau khi kết nối thành công, peer ngừng gửi dữ liệu nhưng receive stream không có read timeout hoặc application-level deadline nên subscription treo.
Ứng dụng dùng timeout trên Mono response nhưng không propagate cancellation tới công việc upstream; request đã hết hạn ở client nhưng server tiếp tục xử lý và giữ tài nguyên.
RetryWhen được cấu hình retry mọi lỗi kết nối cho POST tạo đơn hàng; response timeout xảy ra sau khi server đã commit đơn và retry tạo giao dịch trùng.
Nhóm retry liên tục khi pool pending acquire timeout; retry tạo thêm request cạnh tranh cùng pool và khuếch đại nghẽn thay vì chờ tài nguyên phục hồi.
Retry policy không có backoff hoặc jitter; khi upstream phục hồi, hàng nghìn client retry đồng thời tạo traffic spike và backend lại quá tải.
HttpClient không giới hạn thời gian toàn bộ chuỗi retry; mỗi attempt có timeout riêng nhưng tổng thời gian vượt deadline của API gọi tới.
TLS handshake thất bại vì client tin CA khác với chứng chỉ server; đội vận hành chỉ tăng connect timeout dù lỗi xảy ra ở bước xác thực chứng chỉ.
Ứng dụng cấu hình custom trust manager chấp nhận mọi certificate để xử lý lỗi môi trường; kết nối thành công nhưng mất xác thực danh tính server.
Reactor Netty HttpClient dùng SNI theo hostname mặc định nhưng request đi tới IP trực tiếp; server trả certificate cho domain khác và hostname verification thất bại.
TLS handshake timeout quá thấp đối với kết nối qua mạng liên vùng; request bị hủy trước khi bắt tay hoàn tất trong khi các kết nối nội vùng vẫn hoạt động.
Chứng chỉ client mTLS được rotate nhưng Reactor Netty client giữ SSL context cũ; các kết nối mới bị upstream từ chối sau thời điểm rollover.
HTTP/2 client mở nhiều stream đồng thời trên một connection; giới hạn concurrent streams phía server đạt trần và các request mới phải chờ dù connection pool còn một socket khỏe.
HTTP/2 flow control window nhỏ đối với response streaming lớn; throughput giảm và các stream chờ window update trong khi ứng dụng tưởng network bandwidth là nút nghẽn.
Server gửi GOAWAY khi graceful shutdown; client tiếp tục dùng connection cũ cho request mới và cần xử lý retry những stream chưa được xử lý theo semantics HTTP/2.
Ứng dụng nhận HTTP response streaming nhưng dùng collectList trước khi xử lý; backpressure bị vô hiệu ở tầng ứng dụng và toàn bộ dữ liệu được giữ trong heap.
Client gửi body từ Flux tốc độ cao nhưng nguồn không tôn trọng demand hoặc dùng unbounded buffer; outbound queue tăng và memory pressure xuất hiện khi network chậm.
Server nhận upload theo streaming nhưng handler chuyển body sang blocking file write trên event loop; backpressure từ disk không được xử lý và các request khác bị chặn.
Một endpoint trả Flux dữ liệu vô hạn nhưng client hủy subscription; server không xử lý cancellation và tiếp tục tạo dữ liệu, giữ socket cùng tài nguyên sau khi consumer rời đi.
Ứng dụng dùng onBackpressureBuffer với giới hạn không đặt; downstream chậm trong thời gian dài khiến buffer tăng cho tới khi tiến trình hết bộ nhớ.
Nhóm dùng onBackpressureDrop để bảo vệ bộ nhớ cho luồng sự kiện thanh toán; khi consumer chậm, một số event quan trọng bị loại mà không có metric hoặc cơ chế replay.
HttpServer nhận nhiều request body lớn cùng lúc; max chunk size và giới hạn buffer không phù hợp, dẫn tới pooled direct memory tăng dù heap usage không cao.
Reactor Netty phát hiện ByteBuf leak sau khi custom handler gọi retain nhưng không release ở nhánh exception; direct memory tăng dần và tiến trình cuối cùng gặp OutOfDirectMemoryError.
Một custom inbound handler giữ ByteBuf sau khi callback kết thúc nhưng không retain; buffer được giải phóng về pool và dữ liệu đọc sau đó bị hỏng hoặc gây lỗi reference count.
Ứng dụng chuyển ByteBuf sang byte[] cho mọi response nhỏ; allocation và copy tăng mạnh dưới tải cao, tạo áp lực GC dù Reactor Netty vốn dùng pooled buffers.
Client tải file lớn bằng responseContent().aggregate(); toàn bộ nội dung được gom vào một buffer và request song song làm direct memory tăng đột biến.
Metrics Reactor Netty được bật nhưng URI tag giữ path thực tế có order ID; số chuỗi thời gian tăng theo từng request và Prometheus cardinality bùng nổ.
Dashboard chỉ xem connection pool active count mà không theo dõi pending acquire, idle, total connections và acquire time; tình trạng pool cạn chỉ được phát hiện khi request timeout.
Micrometer metrics ghi response status nhưng không phân biệt connection timeout, response timeout, TLS failure và pool acquire timeout; đội trực không xác định được giai đoạn lỗi.
Wiretap được bật ở mức DEBUG trong production để điều tra payload; log chứa authorization header và dữ liệu người dùng, đồng thời tăng CPU và I/O.
Reactor Netty access log chưa được cấu hình hoặc bị tắt ở một số server; đội trực không có thông tin request duration và status để đối chiếu với application traces.
Context propagation từ Reactor Context sang MDC không được thiết lập; trace ID có trong controller nhưng log được ghi từ operator downstream thiếu correlation ID.
Ứng dụng dùng ThreadLocal lưu user context trong reactive chain; event loop thread được tái sử dụng giữa nhiều request và dữ liệu context có thể rò sang request khác.
HttpClient tạo nhiều connection nhưng DNS, connect và TLS handshake đều mất thời gian; nhóm chỉ đo tổng request duration và không tách phase để xác định nguồn latency.
Connection pool metrics cho thấy active connections thấp nhưng pending acquire cao; một số connection bị giữ bởi response body chưa consume và không được trả về pool.
HttpServer bind thành công nhưng server không được dispose khi ứng dụng shutdown; test hoặc redeploy để lại port đang mở và lần khởi động sau gặp address already in use.
Ứng dụng dùng custom LoopResources nhưng không gọi disposeLater khi đóng context; event loop threads tồn tại sau shutdown và làm test JVM không kết thúc.
Reactor Netty client và server cùng dùng global resources nhưng một bean gọi HttpResources.disposeLoopsAndConnections; các thành phần khác trong JVM đột ngột mất event loop và pool.
Load test chỉ gửi request nhỏ với response đã cache; production truyền file lớn và response streaming, nên kết quả benchmark không phát hiện direct memory, backpressure và socket pressure.
