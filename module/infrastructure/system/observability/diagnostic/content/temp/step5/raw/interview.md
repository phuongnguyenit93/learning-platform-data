Bạn sẽ bắt đầu chẩn đoán như thế nào khi chỉ nhận được một cảnh báo ứng dụng chậm mà chưa biết phạm vi ảnh hưởng?
Bạn sẽ đặt những câu hỏi nào để xác định triệu chứng, thời gian bắt đầu và mức độ ảnh hưởng của một sự cố?
Bạn sẽ phân biệt triệu chứng quan sát được với nguyên nhân gốc qua một ví dụ hệ thống phân tán như thế nào?
Bạn sẽ xây dựng chuỗi giả thuyết có thể kiểm chứng thay vì thay đổi cấu hình theo phỏng đoán ra sao?
Bạn sẽ chọn phép đo đầu tiên dựa trên tác động người dùng và dấu hiệu lỗi hiện có như thế nào?
Bạn sẽ so sánh dữ liệu từ hệ thống đang lỗi với baseline của những thời điểm vận hành bình thường ra sao?
Bạn sẽ xác định khoảng thời gian điều tra khi một cảnh báo chỉ xuất hiện sau một đợt triển khai như thế nào?
Bạn sẽ dựng timeline sự cố từ deploy event, alert, metric, log và trace như thế nào?
Bạn sẽ xác định điều gì là tương quan thời gian và điều gì đủ bằng chứng về quan hệ nhân quả ra sao?
Bạn sẽ thiết kế phép thử thay đổi một biến để chứng minh hoặc bác bỏ một giả thuyết về hiệu năng như thế nào?
Bạn sẽ khoanh vùng lỗi theo vùng địa lý, tenant, phiên bản ứng dụng và endpoint bằng những cách nào?
Bạn sẽ phân biệt lỗi ổn định với lỗi ngắt quãng và chọn chiến lược thu thập bằng chứng phù hợp ra sao?
Bạn sẽ xác định mức độ tin cậy của dữ liệu quan sát khi chính hệ thống telemetry đang gặp sự cố như thế nào?
Bạn sẽ ưu tiên điều tra tỷ lệ lỗi, độ trễ hay mức sử dụng tài nguyên trong một sự cố ảnh hưởng người dùng ra sao?
Bạn sẽ tổ chức phân công các nhánh điều tra song song mà vẫn tránh thay đổi môi trường thiếu kiểm soát như thế nào?
Bạn sẽ xác định thời điểm cần rollback, cô lập tải hoặc chuyển lưu lượng dựa trên bằng chứng và mức rủi ro nào?
Bạn sẽ ghi lại giả thuyết, phép đo, kết quả và quyết định để nhóm khác có thể tái hiện quá trình chẩn đoán như thế nào?
Bạn sẽ xác định tiêu chí khôi phục dịch vụ khác với tiêu chí đã tìm được nguyên nhân gốc ra sao?
Bạn sẽ trình bày mức độ chắc chắn và những điểm chưa biết trong quá trình cập nhật sự cố cho các bên liên quan như thế nào?
Bạn sẽ phân biệt mục tiêu monitoring và observability khi điều tra những lỗi hệ thống chưa từng gặp ra sao?
Bạn sẽ kết hợp metrics, logs, traces và profiling để trả lời những loại câu hỏi chẩn đoán khác nhau như thế nào?
Bạn sẽ quyết định bắt đầu bằng dashboard hay truy vấn log khi một service đồng thời tăng latency và HTTP 5xx ra sao?
Bạn sẽ áp dụng bốn golden signals gồm latency, traffic, errors và saturation để phân loại triệu chứng như thế nào?
Bạn sẽ áp dụng mô hình RED cho một API để nhận diện dịch vụ bất thường ra sao?
Bạn sẽ sử dụng mô hình USE để kiểm tra CPU, bộ nhớ, đĩa hoặc mạng của một node như thế nào?
Bạn sẽ chọn SLI và SLO phản ánh trải nghiệm người dùng thay vì chỉ độ khỏe của hạ tầng bằng tiêu chí nào?
Bạn sẽ sử dụng error budget và burn rate để quyết định mức độ khẩn cấp của một lỗi như thế nào?
Bạn sẽ phân biệt cảnh báo theo triệu chứng với cảnh báo theo tài nguyên để tránh bị nhiễu trong quá trình ứng cứu ra sao?
Bạn sẽ gom các cảnh báo liên quan đến cùng một sự cố mà không che khuất triệu chứng độc lập như thế nào?
Bạn sẽ phát hiện alert flapping và xác định nên điều chỉnh ngưỡng hay sửa hệ thống nguồn ra sao?
Bạn sẽ so sánh p50, p95 và p99 latency để giải thích hiện tượng trung bình bình thường nhưng người dùng vẫn than phiền như thế nào?
Bạn sẽ phân tích một histogram latency khác với phép tính trung bình từ các sample phân tán ra sao?
Bạn sẽ lựa chọn cửa sổ thời gian và độ phân giải metric để nhìn thấy spike ngắn mà không nhầm với nhiễu như thế nào?
Bạn sẽ phân biệt counter, gauge và histogram để tránh đọc sai số liệu vận hành như thế nào?
Bạn sẽ xử lý counter reset hoặc scrape bị gián đoạn khi tính tốc độ request và tỷ lệ lỗi ra sao?
Bạn sẽ phát hiện missing metrics khác với giá trị metric bằng không trong một dashboard như thế nào?
Bạn sẽ phân tích vì sao tổng hợp latency của nhiều instance có thể che giấu một instance gặp vấn đề như thế nào?
Bạn sẽ chọn nhãn service, endpoint, instance và version để truy vấn khoanh vùng mà không làm tăng cardinality quá mức ra sao?
Bạn sẽ xác định nguy cơ dùng user ID hoặc request ID làm nhãn metric trong quá trình điều tra như thế nào?
Bạn sẽ kiểm tra sự khác nhau giữa telemetry tại client và tại server khi báo cáo độ trễ không khớp ra sao?
Bạn sẽ sử dụng exemplars hoặc liên kết metric với trace để tìm một request cụ thể trong đợt tăng độ trễ như thế nào?
Bạn sẽ kiểm chứng độ mới của metric khi có độ trễ ingest, scrape hoặc aggregation như thế nào?
Bạn sẽ xác định metric nào cần đo thêm khi dashboard hiện tại không thể phân biệt CPU throttling và tải CPU cao ra sao?
Bạn sẽ thiết kế dashboard theo từng lớp client, gateway, service và database để nhận biết nơi lỗi bắt đầu như thế nào?
Bạn sẽ sử dụng tỷ lệ giữa request lỗi và request tổng để tránh bị đánh lừa bởi số lỗi tuyệt đối ra sao?
Bạn sẽ đối chiếu tăng request rate với tăng p99 latency để kiểm tra giả thuyết quá tải như thế nào?
Bạn sẽ phân biệt lỗi ứng dụng thật với lỗi client hủy request khi tính tỷ lệ thành công của dịch vụ như thế nào?
Bạn sẽ thiết kế log có cấu trúc để truy vấn theo timestamp, severity, service và correlation ID như thế nào?
Bạn sẽ xác định các trường log tối thiểu để liên hệ một lỗi ứng dụng với request và phiên bản triển khai ra sao?
Bạn sẽ phân biệt log phát sinh tại gateway, service và database khi một request thất bại như thế nào?
Bạn sẽ theo dõi một lỗi cụ thể qua nhiều service bằng trace ID hoặc request ID trong log ra sao?
Bạn sẽ phân tích nguy cơ đồng hồ các node lệch nhau khi ghép log thành timeline như thế nào?
Bạn sẽ xác định nguyên nhân log xuất hiện trễ, thiếu hoặc bị lặp do pipeline thu thập như thế nào?
Bạn sẽ đánh giá log sampling và giới hạn ingest có làm mất bằng chứng của các lỗi hiếm gặp như thế nào?
Bạn sẽ xác định thời điểm cần tăng log level và cách giảm chi phí hoặc rủi ro khi bật debug trong production ra sao?
Bạn sẽ thiết kế bộ lọc log theo exception type, endpoint và thời gian để tách tín hiệu khỏi thông báo nhiễu như thế nào?
Bạn sẽ phân biệt root exception với các exception được bọc lại khi đọc stack trace từ một lời gọi thất bại ra sao?
Bạn sẽ phát hiện một exception xảy ra nhiều lần do cùng một request bị retry bằng chứng nào trong log?
Bạn sẽ kiểm tra trường hợp log thông báo thành công nhưng response vẫn thất bại ở proxy hoặc client ra sao?
Bạn sẽ xử lý log có chứa token, thông tin người dùng hoặc dữ liệu nhạy cảm trong khi vẫn đủ khả năng điều tra như thế nào?
Bạn sẽ đối chiếu log của ứng dụng với sự kiện Kubernetes hoặc hệ điều hành khi process đột ngột biến mất như thế nào?
Bạn sẽ xác định log của một Pod đã bị thay thế còn truy xuất được ở đâu và giới hạn lưu giữ ra sao?
Bạn sẽ tổ chức truy vấn log trước và sau một thay đổi cấu hình để kiểm tra xem lỗi đã thực sự giảm như thế nào?
Bạn sẽ giải thích span, trace và quan hệ parent-child để mô tả một request đi qua nhiều service như thế nào?
Bạn sẽ xác định đường đi chậm nhất của một request qua cây span mà không nhầm với tổng thời lượng các span con ra sao?
Bạn sẽ sử dụng distributed tracing để tìm service gây độ trễ tăng trong chuỗi gọi đồng bộ như thế nào?
Bạn sẽ kiểm tra context propagation bị đứt khi request đi qua queue, gateway hoặc tác vụ bất đồng bộ ra sao?
Bạn sẽ phân biệt thời gian xử lý tại một span với thời gian chờ network hoặc upstream theo dữ liệu trace như thế nào?
Bạn sẽ đối chiếu span error status với HTTP status và exception log để tránh hiểu sai lỗi ra sao?
Bạn sẽ nhận diện fan-out calls và các request chạy song song trong trace khi điều tra tail latency như thế nào?
Bạn sẽ xử lý trace thiếu span do sampling hoặc instrumentation chưa đầy đủ như thế nào?
Bạn sẽ quyết định dùng head sampling hay tail sampling theo mục tiêu giữ lại trace lỗi và trace chậm ra sao?
Bạn sẽ xác định lý do hai service ghi trace ID khác nhau cho cùng một request bằng những phép kiểm tra nào?
Bạn sẽ sử dụng baggage hoặc trace attributes đúng cách để khoanh vùng theo tenant mà không lộ thông tin nhạy cảm ra sao?
Bạn sẽ phân biệt service dependency map là dữ liệu quan sát được với sơ đồ kiến trúc mong đợi khi tìm request đi lạc ra sao?
Bạn sẽ truy từ một metric lỗi sang trace đại diện rồi xuống log cụ thể để chứng minh nguyên nhân như thế nào?
Bạn sẽ phát hiện telemetry của proxy cho thấy request timeout nhưng ứng dụng backend ghi nhận hoàn thành thành công như thế nào?
Bạn sẽ quyết định khi nào trace chưa đủ bằng chứng và cần dùng profiling hoặc packet capture bổ sung ra sao?
Bạn sẽ giải thích sampling profiler khác instrumentation profiler về overhead và độ chính xác như thế nào?
Bạn sẽ lựa chọn CPU profiling, allocation profiling hay wall-clock profiling theo triệu chứng ứng dụng ra sao?
Bạn sẽ đọc flame graph để tìm call stack tiêu tốn thời gian CPU nhiều nhất như thế nào?
Bạn sẽ phân biệt self time và total time khi đánh giá một hàm nóng trong profiler ra sao?
Bạn sẽ xác định hot path thực sự trong một trace chậm khi profiler cho thấy nhiều khung hàm gọi lồng nhau như thế nào?
Bạn sẽ kiểm tra ảnh hưởng của profiling đến tải production và chọn thời lượng lấy mẫu phù hợp ra sao?
Bạn sẽ dùng Java Flight Recorder hoặc công cụ JVM tương đương để tìm dấu hiệu GC pause và thread contention như thế nào?
Bạn sẽ phân biệt heap dump, thread dump và JFR recording theo mục đích điều tra như thế nào?
Bạn sẽ bảo vệ dữ liệu nhạy cảm trong heap dump, thread dump và profile khi chia sẻ cho nhóm hỗ trợ ra sao?
Bạn sẽ so sánh profile trước và sau tối ưu để chứng minh thay đổi làm giảm CPU thực tế thay vì chỉ đổi luồng thực thi như thế nào?
Bạn sẽ kiểm tra CPU sử dụng cao do ứng dụng hay do process khác trên cùng node bằng những công cụ nào?
Bạn sẽ phân biệt CPU utilization, load average và runnable queue khi node có độ trễ cao như thế nào?
Bạn sẽ xác định CPU throttling trong container dù dashboard host vẫn hiển thị nhiều CPU rảnh ra sao?
Bạn sẽ dùng top, pidstat hoặc công cụ tương đương để tìm process và thread tiêu thụ CPU như thế nào?
Bạn sẽ liên hệ thread ID ở hệ điều hành với stack trace của JVM để truy tìm luồng đang chiếm CPU ra sao?
Bạn sẽ phân biệt vòng lặp bận, lock contention và công việc tính toán hợp lệ dựa trên CPU profile như thế nào?
Bạn sẽ phân tích CPU system time tăng do syscall hoặc network I/O so với CPU user time tăng như thế nào?
Bạn sẽ tìm nguyên nhân context switch quá nhiều khi ứng dụng có hàng nghìn thread và throughput thấp ra sao?
Bạn sẽ xác định một tiến trình bị giới hạn bởi CPU, I/O hay lock thông qua các bằng chứng nào?
Bạn sẽ chứng minh hiệu quả của việc thay đổi số worker threads bằng throughput, latency và CPU metric như thế nào?
Bạn sẽ phân biệt memory usage tăng tự nhiên do cache với memory leak bằng chuỗi số liệu theo thời gian như thế nào?
Bạn sẽ theo dõi RSS, virtual memory, page cache và heap để tránh kết luận sai một process đang rò rỉ bộ nhớ ra sao?
Bạn sẽ kiểm tra memory pressure, swap và major page fault khi latency tăng nhưng CPU không cao như thế nào?
Bạn sẽ xác định vì sao container bị OOMKilled dù JVM heap chưa đạt giới hạn cấu hình ra sao?
Bạn sẽ phân biệt Java heap, metaspace, direct buffer, thread stack và native memory khi tiến trình JVM dùng nhiều RAM như thế nào?
Bạn sẽ phân tích biểu đồ heap used trước và sau GC để nhận biết dấu hiệu rò rỉ đối tượng ra sao?
Bạn sẽ lựa chọn thời điểm thu heap dump để tìm retaining path mà không làm gián đoạn dịch vụ như thế nào?
Bạn sẽ dùng allocation profile để xác định đoạn mã tạo nhiều object ngắn hạn dẫn tới GC liên tục như thế nào?
Bạn sẽ phân biệt GC throughput, pause time và frequency khi đánh giá ảnh hưởng của garbage collector tới API latency ra sao?
Bạn sẽ đối chiếu thời điểm Full GC kéo dài với spike p99 latency trong metrics và traces để kiểm tra mối liên hệ ra sao?
Bạn sẽ xác định dấu hiệu memory leak trong cache, listener hoặc collection không giới hạn bằng heap analysis ra sao?
Bạn sẽ kiểm tra native memory khi RSS tăng nhưng Java heap vẫn ổn định bằng những dữ liệu nào?
Bạn sẽ phân biệt lỗi OutOfMemoryError và tình trạng hệ điều hành kill process do cgroup limit như thế nào?
Bạn sẽ kiểm chứng một thay đổi cấu hình heap hoặc GC có hiệu quả khi tải thay đổi giữa hai lần đo ra sao?
Bạn sẽ sử dụng thread dump để xác định thread BLOCKED, WAITING hoặc RUNNABLE trong một ứng dụng Java bị treo như thế nào?
Bạn sẽ phân biệt deadlock với lock contention kéo dài qua nhiều thread dump liên tiếp ra sao?
Bạn sẽ chẩn đoán một thread pool đã đầy khi request vẫn đến nhưng không có thread xử lý bằng metric nào?
Bạn sẽ phát hiện queue backlog và thời gian chờ trong executor từ log, queue metric và trace như thế nào?
Bạn sẽ xác định connection pool exhaustion với database khi nhiều request chờ lấy kết nối nhưng CPU ứng dụng thấp ra sao?
Bạn sẽ phân biệt request timeout do chờ connection pool với timeout khi database đang thực hiện truy vấn như thế nào?
Bạn sẽ điều tra hiện tượng thread starvation do các lời gọi chặn trong ứng dụng dùng async runtime ra sao?
Bạn sẽ kiểm tra số lượng thread tăng không kiểm soát dẫn tới áp lực RAM và context switching như thế nào?
Bạn sẽ kết hợp flame graph và thread dump để xác định các thread đang bận chờ lock hay đang thực sự tính toán ra sao?
Bạn sẽ đánh giá ảnh hưởng của thay đổi kích thước pool so với sửa nguyên nhân request chậm như thế nào?
Bạn sẽ kiểm tra disk utilization, IOPS, throughput và I/O wait để xác định nghẽn lưu trữ như thế nào?
Bạn sẽ phân biệt đọc ghi nhiều do ứng dụng, database hay log pipeline làm node bị chậm ra sao?
Bạn sẽ tìm nguyên nhân filesystem gần đầy gây lỗi ghi hoặc làm database ngừng hoạt động như thế nào?
Bạn sẽ xác định áp lực log rotation hoặc lưu quá nhiều file tạm bằng metric đĩa và log hệ điều hành ra sao?
Bạn sẽ kiểm chứng latency do lưu trữ khi CPU thấp nhưng thread đợi syscall đọc ghi file ra sao?
Bạn sẽ phân biệt vấn đề DNS resolution, TCP connection, TLS handshake và HTTP response trong một request bị timeout như thế nào?
Bạn sẽ đo riêng thời gian DNS lookup, connect, TLS và time to first byte từ client bằng công cụ nào?
Bạn sẽ đối chiếu p99 latency tăng với packet loss, RTT và TCP retransmission để kiểm tra giả thuyết mạng như thế nào?
Bạn sẽ dùng phép thử nào để chứng minh một dịch vụ TCP vẫn hoạt động dù ping thất bại do ICMP bị chặn?
Bạn sẽ dùng traceroute hoặc mtr để xác định thay đổi đường mạng mà không nhầm hop chặn ICMP với mất kết nối như thế nào?
Bạn sẽ chọn vị trí packet capture ở client, proxy và server để phân biệt SYN bị mất với SYN-ACK không quay về ra sao?
Bạn sẽ kiểm tra kết nối cứ ngắt sau một thời gian cố định có liên quan tới idle timeout ở proxy, load balancer hoặc firewall như thế nào?
Bạn sẽ phân biệt TLS certificate error với TLS handshake timeout và kiểm tra SNI hoặc mTLS ra sao?
Bạn sẽ xác định DNS cache cũ hoặc trả kết quả khác nhau giữa nhiều resolver đang ảnh hưởng đến request như thế nào?
Bạn sẽ điều tra lỗi HTTP 502, 503 và 504 bằng cách kết hợp access log của gateway, upstream metric và trace ra sao?
Bạn sẽ phân tích tình huống lỗi chỉ xuất hiện giữa hai availability zone mà không gặp trong cùng zone như thế nào?
Bạn sẽ xác định khi nào cần dùng tcpdump hoặc Wireshark thay vì chỉ dựa vào metric của service ra sao?
Bạn sẽ phân biệt application timeout với database timeout khi trace có một span truy vấn kéo dài như thế nào?
Bạn sẽ tìm truy vấn SQL gây p99 latency cao bằng slow query log, trace và số lần gọi như thế nào?
Bạn sẽ sử dụng EXPLAIN hoặc execution plan để kiểm chứng giả thuyết index không hiệu quả ra sao?
Bạn sẽ phân biệt thời gian chờ lock trong database với thời gian thực thi truy vấn bằng metric nào?
Bạn sẽ chẩn đoán deadlock transaction và xác định thứ tự khóa giữa các giao dịch như thế nào?
Bạn sẽ phát hiện connection pool saturation khi database còn CPU rảnh nhưng ứng dụng vẫn timeout như thế nào?
Bạn sẽ xác định replica lag dẫn đến đọc dữ liệu cũ mà ứng dụng nhầm thành lỗi nghiệp vụ ra sao?
Bạn sẽ đánh giá tác động của replication lag, failover hoặc leader change đến chuỗi lỗi ứng dụng như thế nào?
Bạn sẽ theo dõi buffer cache hit ratio, disk I/O và memory pressure khi database có nhiều truy vấn chậm ra sao?
Bạn sẽ phân biệt tăng số query do N+1 trong ứng dụng với bản thân một truy vấn SQL chậm như thế nào?
Bạn sẽ kiểm tra giả thuyết quá nhiều transaction dài làm cản trở vacuum, compaction hoặc giải phóng tài nguyên ra sao?
Bạn sẽ đối chiếu thời gian xử lý database trong trace với thời gian query server ghi nhận để tìm phần thời gian còn thiếu như thế nào?
Bạn sẽ phân biệt độ trễ ứng dụng do chờ queue, connection pool hay kết quả database bằng cách thêm instrumentation ở đâu?
Bạn sẽ thiết kế phép thử trước và sau khi thêm index để tránh kết luận tối ưu đúng khi lưu lượng khác nhau ra sao?
Bạn sẽ bắt đầu từ node, Pod hay Service khi tỷ lệ lỗi tăng chỉ ở một phần workload Kubernetes như thế nào?
Bạn sẽ kết hợp kubectl describe, logs và events để xác định nguyên nhân Pod liên tục CrashLoopBackOff như thế nào?
Bạn sẽ phân biệt Pod OOMKilled, eviction do memory pressure và container exit do lỗi ứng dụng như thế nào?
Bạn sẽ kiểm tra request và limit CPU khi container bị throttling dù node chưa dùng hết năng lực như thế nào?
Bạn sẽ xác định liveness probe quá nhạy có làm Pod restart trong đợt tải cao bằng những dữ liệu nào?
Bạn sẽ phân biệt readiness probe thất bại với lỗi mạng Service-to-Pod khi request không được định tuyến như thế nào?
Bạn sẽ đối chiếu Service selector, EndpointSlice và trạng thái Pod khi chỉ một số backend nhận được traffic ra sao?
Bạn sẽ chẩn đoán DNS trong Kubernetes khi Pod kết nối bằng IP thành công nhưng gọi theo tên Service thất bại như thế nào?
Bạn sẽ kiểm tra NetworkPolicy hoặc cấu hình service mesh khi hai namespace không thể gọi nhau bằng cách nào?
Bạn sẽ tìm nguyên nhân chỉ một node Kubernetes có Pod bị timeout từ metric CNI, conntrack và network như thế nào?
Bạn sẽ phân biệt HPA chưa scale kịp với ứng dụng bị nghẽn do downstream bằng chuỗi dữ liệu nào?
Bạn sẽ xác định mối liên hệ giữa rolling deployment, replica readiness và sự gia tăng lỗi 503 như thế nào?
Bạn sẽ kiểm tra Pod bị scheduling delay do thiếu CPU, memory, taint hoặc affinity bằng bằng chứng nào?
Bạn sẽ xác định metric bộ nhớ của container khác với lượng heap sử dụng của JVM trong Pod như thế nào?
Bạn sẽ sử dụng thông tin node pressure và disk pressure để giải thích hiện tượng nhiều Pod bị eviction ra sao?
Bạn sẽ khoanh vùng lỗi do sidecar proxy hay do ứng dụng khi trace cho thấy độ trễ tăng ở một hop service mesh như thế nào?
Bạn sẽ thiết kế dashboard kết hợp Pod restart, throttling, memory, request latency và error rate để hỗ trợ điều tra như thế nào?
Bạn sẽ xác định cách truy xuất log và trace của Pod đã bị thay thế khi sự cố xảy ra trước lúc điều tra ra sao?
Bạn sẽ lựa chọn một phép thử an toàn trong staging để tái hiện sự cố resource limit trước khi thay đổi production như thế nào?
Bạn sẽ xác định nguyên nhân tăng latency do request fan-out và retry amplification giữa nhiều microservice như thế nào?
Bạn sẽ phân biệt saturation ở một service với lỗi lan truyền do downstream chậm bằng dependency graph và traces ra sao?
Bạn sẽ kiểm tra circuit breaker, retry policy và timeout budget khi lỗi lan rộng dù chỉ một backend gặp sự cố như thế nào?
Bạn sẽ xác định queue consumer lag, backlog và xử lý chậm khi hệ thống bất đồng bộ bị chậm cập nhật dữ liệu ra sao?
Bạn sẽ phân biệt lỗi mất sự kiện với lỗi sự kiện chưa được xử lý từ producer, broker và consumer metric như thế nào?
Bạn sẽ xác định tác động của log ingestion hoặc tracing exporter đến CPU và latency của chính ứng dụng như thế nào?
Bạn sẽ phát hiện một agent thu thập telemetry bị lỗi gây thiếu dữ liệu mà dashboard lại hiển thị giá trị bằng không như thế nào?
Bạn sẽ thiết kế canary measurement để so sánh phiên bản mới và cũ dựa trên cùng loại request và điều kiện tải ra sao?
Bạn sẽ xác định những điều kiện cần kiểm soát khi load testing để tránh quy kết sai nguyên nhân hiệu năng ra sao?
Bạn sẽ đánh giá nguy cơ quan sát gây tác động lên hệ thống khi bật profiler, log debug hoặc packet capture ở production như thế nào?
Bạn sẽ đặt những ngưỡng dừng phép thử nào để bảo vệ người dùng và dữ liệu khi thực hiện chẩn đoán production?
Bạn sẽ đặt tiêu chí xác nhận khôi phục dựa trên SLO, error rate và latency sau khi triển khai bản sửa ra sao?
Bạn sẽ giám sát những chỉ số nào qua giờ cao điểm để xác nhận sự cố không tái diễn sau khi khắc phục?
Bạn sẽ phân biệt mitigated, resolved và root cause confirmed khi tổng kết trạng thái sự cố như thế nào?
Bạn sẽ viết báo cáo nguyên nhân gốc có timeline, bằng chứng, yếu tố kích hoạt và hành động phòng ngừa như thế nào?
Bạn sẽ xác định lỗ hổng observability nào làm chậm điều tra và ưu tiên bổ sung instrumentation sau sự cố ra sao?
Nếu API tăng p99 latency nhưng CPU và memory node bình thường, bạn sẽ lần theo trace, queue, network và database theo thứ tự nào?
Nếu một đợt triển khai khiến số Pod restart tăng mà log ứng dụng không có stack trace, bạn sẽ điều tra OOM, probe và node events như thế nào?
Nếu JVM có Full GC kéo dài cùng lúc các request timeout, bạn sẽ kết hợp heap, allocation profile và trace để tìm nguyên nhân ra sao?
Nếu chỉ một tenant bị lỗi HTTP 500 trong khi mọi metric tổng hợp vẫn bình thường, bạn sẽ chọn nhãn, log và trace để khoanh vùng như thế nào?
Nếu dashboard cho thấy CPU 100% nhưng hệ điều hành còn nhiều lõi rảnh, bạn sẽ kiểm tra cgroup quota và CPU throttling ra sao?
Nếu database xuất hiện truy vấn chậm sau khi tăng số worker nhưng throughput không tăng, bạn sẽ kiểm chứng pool, lock và I/O như thế nào?
Nếu tracing thiếu một đoạn request giữa gateway và backend, bạn sẽ xác minh propagation, sampling và instrumentation trước khi kết luận như thế nào?
Nếu lỗi 502 giảm sau khi tăng timeout nhưng p99 latency xấu hơn, bạn sẽ đánh giá liệu bản sửa đã giải quyết nguyên nhân gốc hay chỉ che triệu chứng ra sao?
Bạn sẽ xây dựng playbook chẩn đoán bằng chứng cho một hệ thống Java chạy trên Kubernetes, từ metrics, logs, traces, profiling đến kiểm chứng khắc phục như thế nào?
