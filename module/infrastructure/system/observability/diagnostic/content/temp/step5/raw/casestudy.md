Một API đặt hàng ghi nhận tỷ lệ lỗi tăng từ 0,2% lên 7% trong 20 phút, nhưng dashboard CPU và bộ nhớ của service vẫn bình thường; các log lỗi đến từ ba loại HTTP status khác nhau và chưa có biểu đồ chia theo endpoint.
Khách hàng ở khu vực miền Trung phản ánh màn hình thanh toán chậm vào buổi tối, trong khi số liệu latency gộp của toàn hệ thống vẫn dưới SLO; nhóm trực chưa phân biệt lưu lượng theo vùng, phiên bản ứng dụng và loại kết nối.
Một dịch vụ báo lỗi ngay sau khi deploy nhưng request chạy lại thành công; báo cáo sự cố chỉ ghi thời gian phát hành mà chưa đối chiếu thời điểm thay đổi cấu hình, tăng replica và biến động lưu lượng.
Người dùng báo không tạo được đơn, còn hệ thống giám sát chỉ báo tỷ lệ HTTP 2xx cao; một số response 200 chứa mã lỗi nghiệp vụ trong JSON mà metric proxy không phân biệt được.
Một endpoint có độ trễ trung bình 120 ms nhưng p99 vượt 9 giây vào giờ cao điểm; đội phát triển muốn tăng số pod dựa trên giá trị trung bình mà chưa có dữ liệu phân phối độ trễ theo loại request.
Dashboard hiển thị tỷ lệ lỗi 50% trong một cửa sổ một phút nhưng chỉ có hai request, trong khi một giờ cao điểm với hàng chục nghìn request lại có 1% lỗi; hai cảnh báo bị xếp cùng mức ưu tiên.
API tra cứu tồn kho có throughput giảm một nửa sau bảo trì, song số request từ người dùng cũng giảm đúng thời điểm đó; đội vận hành chưa phân biệt suy giảm năng lực phục vụ với thay đổi lưu lượng đầu vào.
Nhóm nhận ba cảnh báo CPU, memory và HTTP timeout của cùng service trong vòng 30 giây; mỗi người xử lý một cảnh báo riêng và chưa xác định được thứ tự các tín hiệu trong cùng chuỗi sự cố.
Một ứng dụng chỉ chậm sau khi người dùng chuyển từ Wi-Fi sang 4G, nhưng bộ đo synthetic luôn chạy từ một máy trong trung tâm dữ liệu; các lần kiểm thử hiện tại chưa đại diện cho đường mạng thực tế.
Trong một đợt lỗi phân tán, log database ghi UTC, log ứng dụng ghi giờ Việt Nam và một node Kubernetes lệch đồng hồ 90 giây; các sự kiện của cùng trace có timestamp dường như đảo thứ tự.
Một nhóm đánh giá hiệu quả sửa lỗi chỉ bằng việc không còn alert trong năm phút, trong khi lưu lượng tại thời điểm kiểm tra thấp hơn 90% so với lúc sự cố xảy ra.
Sau khi bật tính năng cache, số lần truy vấn database giảm rõ rệt nhưng p99 của API không cải thiện; trace của một số request chậm vẫn có thời gian chờ trước khi logic nghiệp vụ bắt đầu.
Prometheus ngừng scrape một số pod sau khi đổi nhãn ServiceMonitor, khiến biểu đồ CPU xuất hiện khoảng trống; đội trực nhầm giá trị không thu thập được với việc CPU thực sự bằng không.
Một counter số request của service giảm từ 500.000 về 0 ngay khi pod restart; dashboard tính chênh lệch thô giữa hai mẫu tạo giá trị âm và phát cảnh báo lưu lượng bất thường.
Metric lỗi HTTP được gắn nhãn theo request_id và user_id; số series tăng hàng triệu sau một tuần khiến backend lưu metric tốn bộ nhớ, còn lượng request thực tế gần như không đổi.
Đội vận hành lấy trung bình các giá trị p95 từ từng pod để suy ra p95 toàn hệ thống; khi một pod nhận lưu lượng gấp mười lần pod khác, kết quả tổng hợp không phản ánh đúng các request thực tế.
Một API báo latency 90 ms trong histogram còn log client ghi 2 giây; metric server chỉ đo thời gian handler mà không tính DNS, chờ kết nối và thời gian truyền body về thiết bị.
Trong một dashboard, số request lỗi tăng sau khi bật retry tự động; bộ đếm tại sidecar tính từng attempt, còn bộ đếm ở ingress tính mỗi request của người dùng một lần.
Một histogram latency có bucket lớn nhất là 1 giây nhưng nhiều request kéo dài 30 giây; biểu đồ quantile ước lượng từ bucket không giải thích được đuôi độ trễ quan sát ở log.
Một bộ xuất metric JVM chỉ thu thập mỗi 60 giây; các đợt stop-the-world GC kéo dài vài trăm mili giây xuất hiện trong log nhưng không thể hiện rõ trên đồ thị CPU lấy mẫu thưa.
Một cảnh báo dựa vào giá trị bộ nhớ của container tăng ngay sau khi pod khởi động; biểu đồ không tách được page cache, RSS và lượng heap Java đang sử dụng.
Nhóm thiết lập cảnh báo CPU trên trung bình tất cả replica; một pod gặp hotspot đạt 100% CPU liên tục nhưng các pod còn lại nhàn rỗi nên cảnh báo tổng không kích hoạt.
Một dashboard gộp số lượng hàng đợi của nhiều instance bằng phép trung bình; khi một instance có hàng nghìn request chờ và những instance khác bằng không, biểu đồ tổng khiến vấn đề trông nhỏ hơn thực tế.
Một chuỗi metric tồn tại trong staging nhưng biến mất tại production sau khi thêm relabeling; log ứng dụng và traffic vẫn có nhưng cảnh báo phụ thuộc metric đó không còn hoạt động.
Một server có tải cao nhưng tỉ lệ lỗi vẫn dưới ngưỡng SLO; nhóm vận hành chưa có cảnh báo về độ trễ, độ bão hòa queue và khả năng chịu thêm lưu lượng trước chiến dịch khuyến mãi.
Một cảnh báo dao động giữa OK và CRITICAL mỗi phút do ngưỡng đặt sát giá trị tải tự nhiên; trong cùng thời gian, các request của người dùng không bị ảnh hưởng rõ rệt.
Nhóm kiểm tra hiệu năng sau một bản sửa bằng cách so thời gian phản hồi của hai ngày khác nhau; số replica, phân bố endpoint và tỷ lệ cache hit trong hai ngày lại khác đáng kể.
Một bộ thu log bị quá tải và drop 15% bản ghi vào giờ cao điểm; metric request từ gateway vẫn tăng đều trong khi tổng số log truy cập bị giảm, khiến báo cáo tần suất lỗi có vẻ tốt hơn.
Ứng dụng Java ghi log text tự do với ba cách đặt tên transaction ID; khi cần tìm hành trình của một đơn hàng, các bản ghi thuộc cùng giao dịch không thể liên kết bằng truy vấn nhất quán.
Trong lúc sự cố, một service ghi stack trace liên tục cho cùng exception; khối lượng log tăng gấp 40 lần và truy vấn tìm những sự kiện quan trọng khác trở nên chậm.
Một đội bật log mức DEBUG cho toàn bộ HTTP body trong production để tái hiện lỗi; hệ thống lưu log chứa token, dữ liệu cá nhân và dung lượng đĩa trên node tăng nhanh.
Ứng dụng báo lỗi database timeout nhưng log chỉ chứa thông điệp 'operation failed' mà thiếu tên thao tác, correlation ID và thời gian chờ; đội trực không biết request nào liên quan tới pool kết nối.
Log của một batch job ghi 'success' trước khi callback bất đồng bộ hoàn thành; dashboard cho thấy số job thành công cao hơn số bản ghi thực sự xuất hiện trong database.
Trong Kubernetes, log của container trước khi restart không còn được hiển thị qua lệnh xem log mặc định; đội điều tra chỉ thấy tiến trình vừa khởi động lại và bỏ sót exception ở lần chạy trước.
Một service chỉ ghi log lỗi cuối cùng ở gateway, trong khi trace cho thấy request đã đi qua bốn hop; mỗi nhóm microservice không có cùng trace_id nên khó xác định hop đầu tiên bắt đầu chậm.
Một dịch vụ gọi API đối tác bằng HTTP client bất đồng bộ nhưng không chuyển tiếp trace context; trace dừng tại request nội bộ còn log đối tác ghi một request cùng thời điểm mà không có quan hệ cha-con.
Trace sampling được cấu hình chỉ lấy 1% lưu lượng thông thường; một lỗi thanh toán hiếm xảy ra khoảng 20 lần mỗi ngày và phần lớn request lỗi không có trace đầy đủ để phân tích.
Một hệ thống áp dụng tail-based sampling nhưng collector bị thiếu bộ nhớ; những trace kéo dài nhiều phút thường bị mất span hoặc bị loại trước khi quyết định lấy mẫu hoàn tất.
Trong trace, service A mất 3 giây còn tổng duration của các span con chỉ 100 ms; phần thời gian nằm ngoài các span con chưa được instrument và đội phát triển đang quy trách nhiệm cho database.
Trace hiển thị ba request con chạy song song, mỗi span dài 800 ms; dashboard cộng trực tiếp duration thành 2,4 giây và báo đường đi chậm hơn latency 1 giây mà người dùng quan sát.
Một chuỗi trace đi qua message broker, nhưng consumer tạo trace gốc mới khi xử lý sự kiện; việc xác định độ trễ từ lúc publish đến khi dữ liệu được cập nhật không thực hiện được bằng trace hiện tại.
Service A gọi B bằng gRPC rồi B gửi sự kiện tới worker C; log có cùng mã đơn hàng nhưng span tại worker C xuất hiện sau vài phút mà không có quan hệ link tới giao dịch ban đầu.
Hệ thống tracing dùng tên span bao gồm ID sản phẩm trong URL; số operation name tăng rất nhanh khiến giao diện thống kê endpoint khó nhóm các request cùng loại.
Một bộ sưu tập trace có các span timestamp âm so với parent vì hai node lệch đồng hồ; đội điều tra tưởng có lỗi truyền ngược thời gian dù tổng duration được đo bằng đồng hồ monotonic riêng.
API p99 tăng sau khi nâng cấp nhưng trace của các request thành công vẫn ngắn; các request timeout bị mất trace vì tiến trình chết trước khi exporter gửi batch span.
OpenTelemetry Collector bị lỗi kết nối với backend lưu trữ trace trong 15 phút; ứng dụng tiếp tục xử lý bình thường nhưng dashboard mất dấu vết và đội trực nhầm là ứng dụng ngừng nhận request.
JVM của dịch vụ hóa đơn có heap usage dao động từ 35% tới 85% sau mỗi vài phút; log GC ghi nhiều young collection nhưng nhóm phát triển chưa phân biệt nhịp thu gom bình thường với áp lực cấp phát bất thường.
Old generation sau mỗi đợt major GC tăng từ 2 GiB lên 5 GiB trong ba giờ; số request không tăng tương ứng và heap dump cho thấy số lượng đối tượng cache của ứng dụng ngày càng lớn.
Một service Java bị OutOfMemoryError: Java heap space sau khi import file lớn; heap dump ghi nhận nhiều mảng byte giữ nội dung file nhưng metric CPU trước sự cố vẫn bình thường.
Container Java bị OOMKilled ở giới hạn 2 GiB dù -Xmx chỉ đặt 1 GiB; biểu đồ heap dưới 800 MiB nhưng RSS và bộ nhớ ngoài heap tăng đáng kể trước khi pod biến mất.
Ứng dụng WebFlux trả request bằng direct ByteBuffer và tiêu thụ native memory tăng đều; heap dump không chứa lượng dữ liệu tương ứng, trong khi số kết nối mạng dài hạn cũng tăng theo tải.
Một dịch vụ tự động tải class từ plugin trong lúc hot reload; heap ổn định nhưng Metaspace tiếp tục tăng và ứng dụng gặp lỗi liên quan tới vùng nhớ metadata sau nhiều lần cập nhật.
Log GC xuất hiện các lần stop-the-world dài 2 giây đúng khi p99 API tăng, nhưng thời điểm CPU tổng hệ thống không tăng; nhóm cần đối chiếu loại GC, kích thước heap và trạng thái các thread trong những khoảng dừng.
Trong production, allocation rate của JVM tăng gấp bốn sau khi thêm bước serialize JSON; số lượng object sống sau GC gần như không đổi nhưng CPU dành cho GC và tần suất young collection tăng.
Một API tạo báo cáo có chuỗi xử lý dùng nhiều String concatenation; CPU profile hiển thị phần lớn mẫu tại các hàm xây chuỗi còn trace database chỉ chiếm 5% tổng thời gian.
JVM có 500 thread nhưng CPU thấp và latency cao; ba lần thread dump cách nhau 10 giây cho thấy nhiều thread ở trạng thái WAITING trên cùng bộ khóa tài nguyên.
Một ứng dụng nhận request nhưng không phản hồi; thread dump cho thấy hai thread nắm giữ hai monitor theo thứ tự ngược và đều BLOCKED, trong khi health endpoint chạy trên thread pool khác vẫn trả 200.
Pool xử lý HTTP có 200 worker đều chờ CompletableFuture kết quả từ một executor nhỏ đã đầy; metric thread count tăng còn CPU application thấp hơn bình thường trong suốt đợt lỗi.
Sau khi bật virtual threads ở một thành phần Java, throughput không tăng như kỳ vọng; JFR ghi nhiều sự kiện pinning khi thực hiện I/O trong khối đồng bộ và số carrier thread đang bận tăng.
Service Java có nhiều request timeout khi gọi API ngoài; async-profiler ở chế độ CPU chỉ hiển thị ít mẫu, trong khi wall-clock profile lại tập trung vào thời gian chờ socket.
Một nhóm chụp CPU profile trong 30 giây khi hệ thống nhàn rỗi rồi kết luận backend không có hotspot; sự cố thực tế chỉ xuất hiện khi lượng request tăng gấp sáu trong chiến dịch cuối ngày.
Profiling sản xuất bật thu thập stack trace ở tần suất cao và làm CPU tăng thêm đáng kể; trong lúc điều tra, latency đo được khác với thời điểm chưa bật profiler.
CPU của pod billing chạm ngưỡng 100% limit dù CPU node vẫn còn nhiều lõi rảnh; metric throttled periods tăng ngay sau khi giới hạn CPU bị giảm trong bản Helm chart mới.
Biểu đồ CPU usage của container chỉ khoảng 400 millicore nhưng p99 tăng mạnh; CPU quota được cấp 500 millicore và throttling time tăng theo các đợt xử lý đồng thời.
Một node Kubernetes có load average cao nhưng tiến trình Java chỉ sử dụng một lõi; hàng đợi runnable tăng và dashboard chưa tách CPU saturation khỏi số thread chờ I/O.
Máy ảo cloud báo CPU sử dụng cao và request chậm, nhưng metric CPU steal time tăng đúng lúc các workload khác cùng host bùng tải; tiến trình ứng dụng không thay đổi lượng công việc.
CPU user thấp nhưng CPU system tăng mạnh sau khi thêm nhiều kết nối HTTP ngắn; số lần context switch và syscall xử lý network tăng theo throughput.
Một API có độ trễ cao trong lúc iowait của node tăng lên 40%; disk latency và queue depth tăng nhưng bộ xử lý HTTP chỉ ghi mỗi thời gian thực thi handler.
Server lưu cache dữ liệu trên ổ đĩa, sau khi chạy job sao lưu thì throughput API giảm; disk read/write latency tăng và bộ nhớ page cache biến động dù số request không đổi.
Một container bị OOMKilled trong khi node còn nhiều RAM; sự kiện Kubernetes ghi vượt memory limit ở container đó, nhưng cảnh báo hạ tầng chỉ kiểm tra tổng RAM node.
Pod chưa bị OOMKilled nhưng thường xuyên nhận memory pressure và bị eviction ở node có nhiều workload; cùng image chạy trên node khác lại không có sự cố.
Ứng dụng bị nghẽn sau khi tăng số pod từ 4 lên 20; metrics cho thấy tất cả pod mới đều dùng CPU thấp nhưng backend database có số connection đạt mức tối đa.
HPA mở rộng từ 5 tới 30 pod khi CPU tăng nhưng latency tiếp tục xấu đi; metric queue ở dịch vụ phía sau tăng theo số pod mới và không có dấu hiệu xử lý tổng thể nhanh hơn.
Autoscaler không tăng số replica dù request đang backlog; HPA sử dụng CPU utilization nhưng mỗi pod đang WAITING trên kết nối database nên CPU vẫn rất thấp.
Pod mới phải tải mô hình ML mất 90 giây nhưng readiness probe trở thành true ngay sau khi cổng HTTP mở; một phần request được gửi tới pod trước khi dữ liệu sẵn sàng.
Liveness probe phụ thuộc vào database và thường thất bại khi DB chậm vài giây; Kubernetes restart hàng loạt pod đúng lúc hệ thống cần giữ kết nối đang có và tỷ lệ lỗi tăng.
Một Deployment có restart count cao sau khi tăng cấu hình bảo mật; sự kiện pod báo CrashLoopBackOff, nhưng log hiện tại chỉ có những dòng khởi động thành công trước lần crash.
Trong một lần nâng cấp node, nhiều pod có trạng thái Pending dù cluster còn CPU tổng; scheduler event cho thấy ràng buộc affinity và tài nguyên từng node không đáp ứng yêu cầu đặt pod.
Kubernetes Service trả 503 ngắt quãng mặc dù tất cả pod đều Running; danh sách endpoints thay đổi liên tục vì readiness probe thất bại dưới tải và không tương ứng với trạng thái Running.
Một request từ ingress phải mất 4 giây trước khi vào ứng dụng, nhưng trace của Java chỉ dài 50 ms; log ingress ghi thời gian chờ upstream connection tăng trong cùng khoảng thời gian.
Pod chỉ gặp timeout DNS khi chạy trên hai node nhất định; log CoreDNS chung không thấy lỗi, còn node-local DNS cache tại hai node có số request chờ và lỗi tăng.
Ứng dụng tăng tỷ lệ lỗi mạng sau khi bật mTLS service mesh; trace tại sidecar kết thúc trước backend, còn log ứng dụng đích không có request và log proxy xuất hiện lỗi TLS handshake.
Một proxy sidecar bị nghẽn connection pool sau khi service tăng traffic; CPU Java vẫn thấp, nhưng metric upstream pending requests của proxy tăng và các request bị trả 503.
Một API chỉ chậm trên một availability zone; các lần traceroute và đo TCP RTT liên vùng cho thấy đường mạng thay đổi đúng lúc p99 tăng nhưng không thấy lỗi trong log handler.
TCP retransmission tăng đột ngột trên đường từ gateway đến database; số SYN thành công không giảm nhiều nhưng các truy vấn lớn chậm rõ rệt hơn truy vấn nhỏ.
DNS lookup cho endpoint đối tác kéo dài 800 ms ở một số pod nhưng gần như tức thì ở pod khác; trace client chỉ có một span HTTP tổng nên đội phát triển đổ lỗi cho thời gian xử lý server đối tác.
Kết nối TLS tới API ngân hàng mất nhiều thời gian sau khi thay proxy egress; log client chỉ cho thấy timeout, trong khi packet capture ghi nhiều lần handshake lại trước khi có HTTP response.
Một API nhận HTTP 504 từ gateway còn ứng dụng backend ghi đã xử lý thành công; gateway timeout ngắn hơn thời gian backend hoàn tất và khách hàng gửi retry tạo thêm transaction trùng.
Người dùng ở một vùng nhận dữ liệu cũ dù write thành công; log ứng dụng không báo lỗi nhưng metric replication lag tại read replica ở vùng đó tăng lên hàng chục giây.
Connection pool JDBC có 50 connection, active đạt 50 và pending acquire tăng lên 300 request; CPU database còn thấp nhưng thread dump Java cho thấy nhiều request chờ lấy connection.
Database CPU tăng ngay sau triển khai tính năng tìm kiếm; slow query log cho thấy hàng nghìn truy vấn gần giống nhau và metric rows scanned tăng trong khi số lượng request frontend không đổi.
Một endpoint hiển thị danh sách đơn hàng gọi database hơn 200 lần cho một response; trace thể hiện chuỗi nhiều span SQL ngắn, nhưng tổng duration lớn gấp hàng chục lần một lần truy vấn riêng.
Query chậm chỉ xuất hiện với một tenant lớn sau khi thay cấu hình chỉ mục; execution plan ở môi trường test dùng index scan còn tại production planner chọn sequential scan cho dữ liệu của tenant này.
Một tác vụ cập nhật hàng loạt giữ transaction mở hơn năm phút; metric lock wait time tăng ở các API khác dù số truy vấn và tải CPU database không thay đổi.
Ứng dụng gặp deadlock DB ngắt quãng; log database chỉ ra hai transaction khóa tài nguyên theo thứ tự khác nhau, còn log ứng dụng ghi lỗi HTTP 500 mà không nêu transaction ID.
Một query trả nhanh khi chạy thủ công nhưng endpoint chứa query đó vẫn timeout; trace cho thấy thời gian chờ connection pool lớn hơn thời gian thực thi câu SQL sau khi được cấp connection.
Sau khi tăng pool từ 20 lên 100 connection trên mỗi pod, số timeout ở ứng dụng giảm ngắn hạn nhưng database chạm giới hạn tổng session khi autoscaler tăng số pod.
Một hệ thống dùng cache Redis để giảm truy vấn, nhưng khi khóa cache hết hạn đồng loạt, QPS database tăng gấp 30 và nhiều endpoint timeout dù tỷ lệ cache hit trung bình cả ngày vẫn cao.
Cache của một tenant chứa dữ liệu lớn, dẫn đến thời gian deserialize và áp lực cấp phát heap tăng; metric latency Redis thấp nhưng profile ứng dụng cho thấy thời gian CPU tiêu tốn sau khi nhận response.
Một job nhập dữ liệu sử dụng batch insert vào database và tạo hàng triệu bản ghi WAL; disk throughput chạm ngưỡng và các request đọc độc lập cũng chậm, dù slow query log không có truy vấn bất thường.
Một API phụ thuộc vào message broker, queue depth tăng từ 1.000 lên 80.000 nhưng tỷ lệ HTTP 2xx vẫn bình thường; người dùng thấy dữ liệu cập nhật trễ trong vài chục phút.
Consumer xử lý sự kiện có CPU thấp nhưng consumer lag tiếp tục tăng; log chứa nhiều lần retry cùng một message và trace của worker cho thấy thời gian chờ dịch vụ thứ ba.
Một job bất đồng bộ bị xử lý lại sau khi worker crash ngay sau khi commit database; log broker ghi redelivery, còn dashboard nghiệp vụ đếm hai lần hoàn thành cho một job.
Hệ thống có metric error rate của API ổn định nhưng số request chờ trong thread pool tăng liên tục; khi queue đầy, thời gian đợi bắt đầu chiếm phần lớn độ trễ trước khi handler được thực thi.
Sau khi thêm một lớp nén phản hồi, bandwidth giảm 35% nhưng CPU backend tăng và p99 của endpoint JSON nhỏ xấu hơn; metric profile cho thấy thời gian CPU tập trung ở xử lý nén.
Một sự cố chỉ xảy ra khi feature flag được bật cho 10% người dùng; metric gộp không cho thấy khác biệt, trong khi log có phiên bản cấu hình flag và nhóm người dùng bị lỗi nhiều hơn.
Trong một đợt rollback ứng dụng, lỗi 5xx giảm nhưng p99 vẫn cao; metric sidecar cho thấy retry attempts tiếp tục tăng và các pod chạy phiên bản cũ vẫn còn trên đường phục vụ.
Nhóm muốn xác nhận sửa lỗi memory leak sau khi phát hành bản vá; mức heap sau GC giảm trong 30 phút nhưng lưu lượng test thấp hơn production, trong khi bộ nhớ ngoài heap chưa được theo dõi.
Sau khi thêm index cho truy vấn chậm, p95 đọc giảm từ 800 ms xuống 90 ms nhưng latency ghi tăng và kích thước WAL lớn hơn; đội triển khai chỉ nhìn cải thiện của một endpoint để đánh giá thay đổi.
Một thay đổi timeout làm số phản hồi 504 giảm nhưng các request giao dịch tạo trùng tăng; nhóm vận hành chưa đối chiếu số giao dịch thực với số request và số lần retry ở các hop.
Đội phát triển khắc phục sự cố bằng cách tăng giới hạn CPU container; p99 giảm trong bài test đầu nhưng CPU throttling đã hết trong khi queue database tiếp tục tăng ở tải tương đương giờ cao điểm.
Sau khi đổi chiến lược autoscaling, hệ thống chịu tải bình thường ở 2.000 RPS nhưng lỗi xuất hiện lại ở 4.000 RPS; phép đo kiểm chứng trước đó không bao gồm thời gian scale-out và các dependency phía sau.
Một hotfix chỉ được áp dụng ở một trong hai vùng cloud, nhưng dashboard tổng hiển thị tỷ lệ thành công cải thiện; phân tích theo region cho thấy vùng chưa cập nhật vẫn có cùng mẫu lỗi cũ.
Một cảnh báo trễ dữ liệu biến mất sau khi tăng số worker, song lag tiếp tục tăng trong các đợt peak mới; chưa có phép đo throughput xử lý bền vững so với tốc độ sự kiện đến.
Một đội trực kết luận vấn đề do GC sau khi nhìn thấy spike GC đúng lúc lỗi; khi so các trace chậm với log network, nhiều request khác cũng lỗi trong lúc không có pause GC.
Trong một đợt khắc phục, đội vận hành thay đồng thời cấu hình JVM, timeout gateway và số replica; sau khi tỷ lệ lỗi giảm, không có mốc so sánh riêng để xác định thay đổi nào thực sự có tác dụng.
Một lỗi đã giảm sau thay đổi cấu hình nhưng lại xuất hiện vào cuối tuần khi khối lượng batch cao; quy trình post-incident chưa liên kết runbook, dashboard, log query và các điều kiện tải tái hiện sự cố.
