Một dịch vụ Java chạy trên Kubernetes thường xuyên bị throttling CPU dù node còn nhiều lõi rảnh; biểu đồ CPU trung bình thấp nhưng cgroup cpu.stat ghi nhận thời gian throttled tăng đúng lúc p99 latency xấu đi.
Một JVM được cấp CPU request cao nhưng CPU limit thấp; nhóm vận hành chỉ nhìn CPU utilization so với request nên không nhận ra giới hạn quota đang làm các đợt tải ngắn bị chậm.
Một ứng dụng có nhiều worker thread chạy CPU-bound và tổng CPU gần 100%; tăng số thread làm throughput giảm do context switching, khiến đội phát triển cần xác định mức concurrency phù hợp với số CPU thực sự được cấp.
Một JVM có CPU cao trong thời gian dài và GC log ghi nhận nhiều chu kỳ garbage collection; nhóm SRE cần phân biệt CPU tiêu thụ bởi business code với chi phí GC trước khi tăng replica.
Một ứng dụng Java dùng thread pool lớn hơn số CPU nhiều lần cho tác vụ chủ yếu tính toán; hàng đợi runnable tăng và thời gian chuyển ngữ cảnh cao khiến latency tăng dù số request không đổi.
Một pod bị OOMKilled dù Java heap chưa chạm -Xmx; tổng memory cgroup còn bao gồm metaspace, thread stack, direct buffer, native library và các vùng native khác nên giới hạn container bị vượt.
Một dịch vụ có heap usage tăng đều sau mỗi đợt tải và không giảm sau major GC; heap dump cho thấy cache giữ reference tới session đã hết hạn, làm object không thể được thu hồi.
Một ứng dụng có heap sau GC ổn định nhưng RSS tăng qua nhiều ngày; nhóm vận hành cần kiểm tra native memory, direct buffers, metaspace và thread stacks thay vì tiếp tục tăng heap.
Một JVM gặp OutOfMemoryError: Metaspace sau nhiều lần hot reload; classloader cũ vẫn bị giữ bởi static registry và thread context classloader nên metadata của các class đã ngừng dùng không được giải phóng.
Một service Netty sử dụng direct ByteBuffer để giảm copy dữ liệu nhưng direct memory tăng tới giới hạn; heap dump không chỉ ra nơi giữ bộ đệm và nhóm phải đối chiếu native memory, allocator metrics và vòng đời reference.
Một ứng dụng dùng Netty pooled ByteBuf và quên release ở nhánh exception; leak detector phát cảnh báo theo allocation site, trong khi bộ nhớ off-heap tăng dần sau mỗi lần xử lý lỗi.
Một service dùng memory-mapped file để đọc dữ liệu lớn; heap usage thấp nhưng RSS và page cache tăng, khiến nhóm SRE nhầm rằng ứng dụng không dùng bộ nhớ dù container gần chạm giới hạn.
Một JVM có số lượng thread tăng dần sau mỗi lần deploy và không giảm khi tải hạ; thread dump cho thấy tác vụ tạo executor mới nhưng không shutdown, gây tiêu thụ stack memory và scheduler overhead.
Một ứng dụng tạo thread-per-request khi nhận burst traffic; số thread tăng vượt giới hạn container, context switching tăng và hệ thống không còn đủ tài nguyên để xử lý request mới.
Một service dùng cached thread pool cho tác vụ gọi API đối tác có thời gian chờ dài; khi đối tác chậm, pool tạo thêm nhiều thread thay vì giới hạn concurrency, khiến tài nguyên máy chủ cạn dần.
Một ứng dụng chạy trên JDK 21–23 dùng synchronized quanh đoạn blocking I/O; virtual threads bị pin vào carrier threads trong lúc chờ, làm số carrier thread khả dụng giảm và throughput thấp hơn kỳ vọng.
Một service có ScheduledExecutorService dùng để refresh cache nhưng tác vụ đôi khi chạy lâu hơn chu kỳ; các lần chạy chồng lấn và backlog tăng, làm số thread cùng truy cập tài nguyên vượt dự kiến.
Một ứng dụng dùng ThreadLocal để lưu request context trong pool; tác vụ không xóa giá trị sau khi hoàn tất nên worker thread giữ reference tới object lớn và dữ liệu người dùng của request trước.
Một tiến trình Java báo Too many open files sau vài giờ chạy; số file descriptor của PID tăng đều vì một nhánh đọc file không đóng stream khi gặp exception, dù heap và CPU bình thường.
Một service tải file lên object storage nhưng response stream không được đóng trong nhánh timeout; socket và file descriptor bị giữ lại, khiến số kết nối mở tăng sau mỗi lần upload lỗi.
Một ứng dụng mở socket tới nhiều host nhưng không đặt giới hạn pool; khi danh sách endpoint thay đổi, số socket ESTABLISHED tăng vượt dự kiến và tiến trình chạm giới hạn file descriptor.
Một API client tạo kết nối TCP mới cho từng request thay vì tái sử dụng keep-alive; số socket TIME_WAIT tăng mạnh trong đợt tải, cổng ephemeral bị áp lực và độ trễ kết nối tăng.
Một dịch vụ outbound bị lỗi kết nối sau khi tăng replica; mỗi replica tạo connection pool với max size cố định nên tổng số kết nối đồng thời vượt giới hạn database, dù cấu hình từng pod có vẻ an toàn.
Một ứng dụng dùng HikariCP nhưng connection acquisition time tăng cao; số connection đang active đạt maximum và thread request chờ trong pool, trong khi database CPU vẫn thấp.
Một service không trả connection về pool khi transaction ném exception; active connections tăng dần tới maximum và leak detection log chỉ ra stack trace nơi connection được mượn nhưng không được đóng.
Một ứng dụng giữ connection database trong lúc gọi API bên ngoài; thời gian giữ connection tăng theo độ trễ đối tác, làm pool cạn dù thời gian thực thi query rất ngắn.
Một HTTP client pool không đóng response body sau khi đọc status code; connection không được trả về pool, pending acquisition tăng và request bắt đầu timeout dù backend vẫn khỏe.
Một service có idle connection tồn tại lâu hơn firewall timeout; request đầu tiên sau thời gian nhàn rỗi nhận reset, retry làm tăng latency và đội vận hành cần đồng bộ keepalive, idle eviction và timeout của các lớp mạng.
Một ứng dụng đặt connect timeout dài nhưng không đặt read timeout cho API đối tác; các thread chờ vô thời hạn khi server giữ kết nối mà không trả dữ liệu, làm thread pool và connection pool dần cạn.
Một nhóm đặt timeout database ngắn nhưng retry ngay nhiều lần khi gặp lỗi; một sự cố database quá tải bị khuếch đại bởi retry storm và số request mới tiếp tục tăng.
Một hệ thống có retry policy ở cả HTTP client, service layer và message consumer; một thao tác có thể được thực hiện nhiều lần, làm tăng tải và tạo giao dịch trùng khi không có idempotency key.
Một ứng dụng không hủy tác vụ downstream khi client đã timeout; các truy vấn database và HTTP call vẫn tiếp tục chạy nền, tiêu thụ thread và connection dù kết quả không còn được sử dụng.
Một service dùng CompletableFuture với executor riêng nhưng không giới hạn queue; khi dependency chậm, số tác vụ chờ tăng không giới hạn và heap bị lấp đầy bởi các future cùng payload.
Một pipeline xử lý sự kiện dùng LinkedBlockingQueue không giới hạn; producer nhanh hơn consumer trong nhiều giờ và queue giữ toàn bộ message trong heap cho tới khi JVM hết bộ nhớ.
Một đội đổi queue sang bounded capacity nhưng handler rejection chỉ ghi log rồi bỏ message; hệ thống không OOM nữa nhưng dữ liệu nghiệp vụ bị mất âm thầm và không có metric về rejected tasks.
Một ứng dụng dùng ArrayBlockingQueue nhỏ để giới hạn bộ đệm nhưng producer không có cơ chế backpressure; khi queue đầy, request bị reject hàng loạt và người dùng thấy lỗi dù downstream chỉ chậm tạm thời.
Một hệ thống dùng semaphore để giới hạn số tác vụ đồng thời nhưng permit không được trả trong nhánh exception; số permit khả dụng giảm dần và throughput cuối cùng về 0 dù không còn tác vụ thực sự chạy.
Một service dùng rate limiter chung cho nhiều tenant; một tenant gửi burst traffic chiếm hết quota và các tenant còn lại bị từ chối dù tài nguyên tổng thể vẫn còn.
Một ứng dụng cache kết quả API không đặt giới hạn kích thước; traffic truy vấn nhiều khóa duy nhất làm heap tăng liên tục và GC thường xuyên, khiến đội phát triển cần chọn eviction policy và maximum weight.
Một cache dùng TTL dài nhưng không có giới hạn số entry; các khóa không được truy cập lại vẫn tồn tại tới khi hết hạn và bộ nhớ tăng vượt mức dự kiến trong thời gian tải cao.
Một cache bị cache stampede khi nhiều request đồng thời hết hạn cùng một key; mọi thread cùng gọi database để làm mới dữ liệu và tạo đỉnh tải không cần thiết.
Một pipeline ghi dữ liệu ra file bằng BufferedOutputStream nhưng chỉ flush khi buffer đầy; ứng dụng trả thành công trước khi dữ liệu được chuyển xuống tầng dưới, khiến người vận hành nhầm flush với bảo đảm bền vững.
Một ứng dụng dùng producer-consumer buffer để gom batch gửi đi; batch size quá lớn làm tăng latency và bộ nhớ đệm, còn batch quá nhỏ tạo quá nhiều request và overhead hệ thống.
Một dịch vụ gửi telemetry qua queue trong bộ nhớ khi backend mất kết nối; queue tăng tới giới hạn heap và làm chính ứng dụng nghiệp vụ bị OOM, vì tài nguyên pipeline không được cô lập.
Một hệ thống có thread pool, connection pool và queue đều được cấu hình riêng nhưng không tính tổng số tác vụ có thể chờ; khi upstream tăng tải, hàng đợi cộng dồn làm request tồn tại lâu hơn timeout của người dùng.
Một ứng dụng dùng circuit breaker để ngăn gọi dependency lỗi nhưng không giới hạn số request đang chờ trước breaker; backlog vẫn tiếp tục tích tụ và tiêu thụ bộ nhớ dù cuộc gọi mới đã bị chặn.
Một service có nhiều replica và mỗi replica đặt cache 2 GB cùng pool 100 connection; autoscaling lên 20 replica làm tổng memory reservation và số kết nối vượt khả năng của cluster và database.
Một JVM chạy trong container nhưng -XX:MaxRAMPercentage được đặt cao; heap được tính gần sát memory limit và không chừa đủ không gian cho native memory, direct buffers, metaspace và thread stacks.
Một nhóm bật Native Memory Tracking để điều tra RSS tăng nhưng chỉ đọc heap metrics; NMT cho thấy phần Thread, Class và Internal tăng theo thời gian, giúp khoanh vùng vùng native cần điều tra.
Một ứng dụng có GC pause dài và allocation rate cao; nhóm chỉ tăng heap size làm footprint tăng mà không giảm tốc độ tạo object tạm, trong khi pause vẫn vượt mục tiêu và hot path mới là nơi cần tối ưu.
Một ứng dụng sử dụng G1GC nhưng đặt pause target rất thấp; collector tăng công việc concurrent và CPU overhead, khiến throughput giảm dù pause thực tế không đạt mục tiêu mong muốn.
Một JVM dùng ZGC hoặc Shenandoah để giảm pause nhưng nhóm chỉ so sánh số liệu heap occupancy; CPU overhead, native memory và throughput theo workload chưa được đo nên quyết định đổi collector thiếu cơ sở.
Một pod có CPU limit thấp và GC cần nhiều CPU concurrent; collector không kịp hoàn thành chu kỳ trước khi allocation pressure tăng, dẫn tới pause hoặc allocation stall kéo dài.
Một dịch vụ bị OOMKilled ngay sau Full GC; heap dump cho thấy live set thấp hơn -Xmx nhưng RSS vượt cgroup limit do native library và direct memory, khiến việc tăng heap không giải quyết được.
Một nhóm chỉ cảnh báo heap usage vượt 80% mà không theo dõi post-GC occupancy; heap thường tăng theo tải rồi được thu hồi bình thường, tạo cảnh báo nhiễu và che khuất leak thật.
Một ứng dụng có nhiều thread chờ synchronized lock do một thread giữ khóa trong lúc gọi dịch vụ bên ngoài; thread dump tại nhiều thời điểm cho thấy cùng monitor contention và giúp xác định lock holder.
Một service mở file, socket và connection pool nhưng chỉ theo dõi heap; số file descriptor và socket tăng tới giới hạn OS trong khi memory metrics vẫn bình thường, khiến lỗi Too many open files xuất hiện đột ngột.
Một đội SRE theo dõi process RSS nhưng không đối chiếu memory cgroup, page cache và shared memory; container bị OOM kill dù số liệu process riêng lẻ không vượt giới hạn được hiển thị.
Một ứng dụng có thời gian chờ connection pool tăng nhưng dashboard chỉ hiển thị số connection active; không có pending threads, acquisition timeout và leak detection nên nhóm không phân biệt được pool quá nhỏ với connection leak.
Một service có request latency tăng khi queue depth và buffer utilization cùng tăng; nhóm chỉ scale CPU mà không xem tốc độ producer/consumer và downstream capacity, khiến backlog tiếp tục phình.
Một hệ thống xử lý batch có giới hạn concurrency theo cấu hình nhưng không điều chỉnh theo số CPU và connection database; khi scale ngang, tổng concurrency vượt capacity và hiệu năng toàn hệ thống giảm.
Một nhóm sửa lỗi bằng cách tăng heap, thread pool và connection pool cùng lúc; throughput có cải thiện ngắn hạn nhưng database, CPU và memory đều chạm ngưỡng mới, khiến không xác định được thay đổi nào có ích và điểm nghẽn kế tiếp ở đâu.
Một service được triển khai bản mới và thấy memory giảm sau restart; đội vận hành kết luận đã sửa leak nhưng chưa quan sát đủ chu kỳ tải, GC và số lượng object sống để xác nhận xu hướng tăng dài hạn đã biến mất.
Một ứng dụng dùng shutdown hook để đóng executor, connection pool và flush buffer nhưng container gửi SIGKILL khi grace period quá ngắn; tác vụ cleanup không hoàn tất và tài nguyên hoặc dữ liệu chưa flush bị bỏ lại.
Một nhóm thiết kế readiness probe chỉ kiểm tra process còn sống; connection pool đã cạn và worker queue đầy nhưng pod vẫn nhận traffic, làm lỗi lan rộng dù liveness chưa thất bại.
