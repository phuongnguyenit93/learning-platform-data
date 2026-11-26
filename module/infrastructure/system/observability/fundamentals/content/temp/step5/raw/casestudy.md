Một nền tảng đặt hàng phát hiện khách liên tục báo lỗi thanh toán nhưng máy chủ vẫn báo CPU thấp và tiến trình đang chạy; đội trực chỉ có health check nên không xác định được yêu cầu đã hỏng ở bước nào.
Sau khi tách ứng dụng nguyên khối thành sáu microservice, mỗi nhóm lưu log theo cách riêng và chỉ theo dõi CPU máy chủ; một yêu cầu đặt hàng đi qua nhiều service thất bại nhưng không có góc nhìn chung để giải thích.
Một nhóm dự án đầu tư thêm hệ thống giám sát uptime rồi tuyên bố đã có observability; trong sự cố trả kết quả sai cho khách, mọi thành phần vẫn báo healthy và các chỉ số sẵn sàng vẫn xanh.
Trung tâm dữ liệu ghi nhận latency tăng nhưng đội vận hành chỉ kiểm tra log lỗi; dịch vụ không phát sinh exception khi hàng đợi công việc tích tụ khiến họ thiếu tín hiệu về tình trạng thực tế.
Một trang thương mại điện tử thống kê tổng số request mỗi phút nhưng không biết bao nhiêu người thực sự đặt đơn thành công; bộ phận kinh doanh báo doanh thu giảm trong khi dashboard HTTP vẫn ổn định.
Nhóm giao dịch đặt SLO 99,9% yêu cầu thanh toán thành công nhưng chọn SLI theo thời gian máy chủ hoạt động; khách hàng vẫn nhận lỗi nghiệp vụ trong khi endpoint có thể truy cập bình thường.
API tìm kiếm bị phản ánh chậm vào giờ cao điểm nhưng báo cáo hiệu năng chỉ hiển thị thời gian xử lý trung bình 120 ms; một tỷ lệ nhỏ request kéo dài nhiều giây chưa được thể hiện.
Một hệ thống có cùng khối lượng request mỗi giây trong hai ngày nhưng ngày thứ hai sử dụng nhiều I/O và người dùng phàn nàn chậm hơn; dashboard hiện chỉ theo dõi throughput.
Đội sản phẩm dùng số lượng exception trong log làm chỉ số lỗi toàn hệ thống; các request bị trả HTTP 503 do upstream timeout không tạo exception ứng dụng nên báo cáo thiếu nhiều lỗi.
Nhóm vận hành xây dashboard cho CPU, memory và disk theo từng node nhưng không gắn thông tin ứng dụng, môi trường hay dịch vụ; khi một biểu đồ tăng, đội trực không biết chủ sở hữu cần gọi.
Một backend phát metric số request dưới dạng counter nhưng người phân tích đọc chênh lệch thô giữa hai thời điểm khởi động lại pod; biểu đồ xuất hiện lưu lượng âm sau một đợt rollout.
Một worker công việc ghi metric tổng số job đã xử lý lên Prometheus nhưng sau mỗi lần restart giá trị bắt đầu lại từ không; dashboard đếm công việc trong ngày sai so với hệ thống nghiệp vụ.
Dịch vụ thanh toán dùng gauge cho số giao dịch đang xử lý nhưng dashboard cộng gauge từ nhiều pod đã bị xóa và vẫn giữ series cũ; số giao dịch đang chạy được báo cáo cao hơn thực tế.
Một ứng dụng lưu độ trễ request dưới dạng counter tổng mili giây đã tiêu thụ mà không lưu phân bố từng request; nhóm không thể phân biệt nhiều yêu cầu nhanh với ít yêu cầu cực chậm.
Nhóm thiết kế metric histogram cho thời gian truy vấn với các bucket quá rộng; cả request 300 ms và 3 giây nằm trong cùng một khoảng, khiến p95 ước lượng quá thô để đánh giá SLA.
API đặt hàng phát histogram latency bằng các bucket khác nhau giữa phiên bản cũ và mới; khi nhóm cộng số liệu toàn cụm, đường phân vị nhận kết quả không nhất quán.
Dashboard tính trung bình của các p99 đo riêng trên từng pod để đại diện p99 toàn dịch vụ; trong giờ cao điểm, dữ liệu của pod nhiều request bị đánh đồng với pod gần như không có traffic.
Một người dùng đo p95 trực tiếp từ các bản summary latency riêng lẻ trên nhiều instance rồi cộng kết quả; khi số instance tăng, con số không phản ánh phân bố request tổng thể.
Hệ thống dùng nhãn user_id trên metric số lần gọi API; sau khi có hàng triệu tài khoản, số time series tăng mạnh và hệ thống lưu metrics bị quá tải.
Nhóm gắn nguyên URL chứa order_id vào nhãn route của metric HTTP; mỗi đơn hàng tạo series mới nên dashboard tăng cardinality dù số lượng endpoint cố định.
API nhiều tenant gắn tenant_id vào mọi metric; vài doanh nghiệp rất lớn không phải nguyên nhân chính nhưng backend lưu trữ metrics phải quản lý hàng trăm nghìn chuỗi mới mỗi ngày.
Một Deployment cập nhật liên tục tạo tên pod mới cho các series có cùng metric và label pod; chi phí lưu lịch sử metrics tăng theo số lần rollout dù số replica không đổi.
Trong một cluster có 40 pod, metric CPU chỉ được thu thập mỗi 60 giây; các đợt CPU tăng vọt kéo dài 5 giây trong mỗi phút không xuất hiện rõ trên biểu đồ.
Đội vận hành tăng scrape interval lên năm phút để tiết kiệm dung lượng metrics; một worker chỉ bị nghẽn trong 30 giây nên đồ thị bỏ lỡ gần như toàn bộ tín hiệu sự cố.
Một exporter chỉ phản hồi metrics khi ứng dụng ít tải; khi CPU của ứng dụng tăng cao, Prometheus không scrape được nhưng biểu đồ tùy chỉnh lại coi dữ liệu bị thiếu như giá trị bằng không.
Prometheus nhận dữ liệu từ nhiều node có đồng hồ lệch nhau; khi đối chiếu mức tăng request với timestamp của log, chuỗi sự kiện có thứ tự khó giải thích.
Nhóm tính error rate bằng cách chia số lỗi trong 5 phút cho tổng request trong 1 giờ; tỷ lệ cảnh báo biến động bất thường khi lưu lượng thay đổi theo thời gian.
Trong ngày nghỉ lễ, API gần như không có request nhưng tỷ lệ lỗi trên cửa sổ rất ngắn hiển thị 100% chỉ vì một lần gọi thất bại; cảnh báo khẩn cấp đánh thức người trực.
Một dịch vụ xử lý 100 nghìn request mỗi phút với error rate 0,2% nhưng nhóm chỉ nhìn tỷ lệ phần trăm và không biết hàng trăm người dùng vẫn gặp lỗi mỗi phút.
Dashboard hiển thị độ trễ của API theo từng instance nhưng không theo region; sự cố chỉ tác động một vùng nhỏ bị che bởi vùng còn lại xử lý lưu lượng lớn.
Ứng dụng ghi số lượng đơn hoàn tất thành metric nhưng bộ phận nghiệp vụ dùng múi giờ địa phương trong báo cáo; tổng theo ngày không khớp với metrics được tính trên mốc UTC.
Một ứng dụng ghi nhận request retry là các request mới trong metric throughput; thời điểm backend lỗi, biểu đồ lượng truy cập tăng mạnh dù số khách hàng thực sự không thay đổi.
Nhóm triển khai metric cho số request ở gateway và ở backend rồi cộng cả hai thành tổng lưu lượng; cùng một request được đếm hai lần khiến báo cáo tăng bất thường sau khi thêm gateway.
Dịch vụ xử lý hàng đợi ghi queue depth nhưng không ghi tuổi của công việc cũ nhất; số job đang chờ ít nhưng một tác vụ của khách VIP vẫn bị treo nhiều giờ.
Một worker đọc Kafka báo throughput ổn định nhưng consumer lag tiếp tục tăng vì tốc độ tạo sự kiện cao hơn tốc độ xử lý; dashboard hiện không có góc nhìn liên kết hai tốc độ.
Đội phát triển chỉ giám sát số kết nối cơ sở dữ liệu đang mở; khi connection pool hết slot, request chờ lâu trong hàng đợi nhưng tổng kết nối vẫn dưới ngưỡng cấu hình máy chủ.
Service A ghi log dạng văn bản tự do còn service B ghi JSON; khi một request thất bại qua cả hai, công cụ tìm kiếm không thể lọc theo cùng trường service và correlation_id.
Một dịch vụ chỉ ghi thông báo lỗi chung 'request failed' vào log; trong một đợt trả 500, đội trực không biết endpoint nào, tenant nào hay upstream nào liên quan.
Ứng dụng ghi log với timestamp theo giờ địa phương còn proxy ghi UTC; khi đối chiếu lỗi 502 ở proxy với sự kiện backend, nhóm xác định sai thứ tự các bước.
Một Deployment dùng nhiều replica với mức độ log khác nhau do cấu hình từng pod; cùng một lỗi chỉ xuất hiện trong log của một số instance làm việc tái hiện trở nên khó khăn.
Một hệ thống chỉ lưu log ở ổ đĩa cục bộ của container; sau khi Kubernetes tạo pod mới vì hết bộ nhớ, các dòng log ngay trước thời điểm crash không còn trong công cụ truy vấn tập trung.
Ứng dụng ghi JSON log nhưng stack trace nhiều dòng bị shipper tách thành nhiều sự kiện độc lập; nhóm tìm nguyên nhân exception chỉ thấy một phần thông tin ở từng bản ghi.
Nhóm bật DEBUG log cho tất cả API trong giờ cao điểm; tốc độ ghi log và chi phí ingest tăng mạnh, làm độ trễ request xấu đi trong khi phần lớn log không được dùng để điều tra.
Một dịch vụ có cơ chế lấy mẫu log chỉ giữ một phần bản ghi thành công; lúc cần đối chiếu request cá biệt, nhóm thấy khoảng trống khó phân biệt với lỗi hệ thống thu thập.
Ứng dụng đưa Authorization header và thông tin thẻ thanh toán vào structured log để dễ tái hiện lỗi; hệ thống tập trung log cấp quyền tìm kiếm rộng cho nhiều nhóm vận hành.
Nhóm gửi log chứa email khách hàng đến nền tảng quan sát của bên thứ ba; yêu cầu bảo vệ dữ liệu mới làm lộ khoảng trống trong chính sách ẩn danh và thời gian lưu.
Một container bị lỗi mạng với collector log và bộ đệm shipper đầy; ứng dụng vẫn chạy nhưng các sự kiện phát sinh trong sự cố không tới được kho log tập trung.
Hệ thống log có độ trễ ingest mười phút khi nhận tải đột biến; đội trực xem dashboard thời gian thực và tưởng không có lỗi vì chưa thấy bản ghi vừa phát sinh.
Nhóm chỉ dùng level ERROR để tìm nguyên nhân lỗi đơn hàng; các event quan trọng về retry, timeout và circuit breaker lại được ghi ở WARN nên chuỗi diễn biến bị thiếu.
Một ứng dụng viết log chứa mã trạng thái HTTP và thông báo ngoại lệ nhưng thiếu trace_id; dashboard lỗi có thể đếm số lần thất bại nhưng không liên kết được một lỗi cụ thể với trace.
Một request từ ứng dụng mobile đi qua gateway, service đặt hàng và thanh toán; log mỗi nơi có request_id khác nhau nên không thể tìm toàn bộ hoạt động của một giao dịch.
Trong microservice Java, nhóm đã bật distributed tracing nhưng một lời gọi REST sang hệ thống khác không chuyển trace context; giao diện trace chỉ thể hiện service đầu tiên như thể backend không hề được gọi.
Một ứng dụng gửi message qua hàng đợi rồi worker xử lý vài phút sau; trace của request gốc không liên kết với trace của worker khiến thời gian chờ và xử lý bị nhầm là mất dấu.
Nhóm tạo một trace span cho toàn bộ batch nhập 50 nghìn bản ghi; khi phát hiện chỉ 20 bản ghi lỗi, họ không phân biệt được bước thực thi gây chậm hoặc nhánh xử lý liên quan.
Một dịch vụ gọi ba upstream song song nhưng tracer tạo các span con theo cách không thể hiện quan hệ thực tế; người điều tra tưởng tổng thời gian bằng tổng độ dài từng lời gọi.
Ứng dụng bắt đầu một span mới cho mỗi bước nhỏ nhưng không đóng span trong nhánh xử lý lỗi; giao diện trace hiển thị các đoạn kéo dài bất thường dù request đã kết thúc.
Một gateway nhận traceparent từ client không đáng tin cậy mà không có quy tắc xác định nguồn; các trace có cùng định danh bất thường gây khó khăn khi phân biệt traffic của người dùng khác nhau.
Nhóm phát triển đổi thư viện tracing trong một service nhưng vẫn dùng propagation format khác với các service còn lại; trace bị chia thành nhiều cây độc lập sau lần triển khai.
Đội vận hành thấy một trace có thời gian 1,2 giây trong khi metric endpoint ghi p95 4 giây; collector chỉ giữ một phần trace nên các request chậm nhất có thể đã bị bỏ qua.
Nền tảng dùng head-based sampling ở mức 1% cho tất cả request; một lỗi chỉ xảy ra một lần mỗi nghìn request và phần lớn sự kiện lỗi không có trace tương ứng để điều tra.
Nhóm chuyển sang tail sampling để ưu tiên trace chậm và lỗi, nhưng bộ thu thập không đủ bộ nhớ giữ dữ liệu chờ quyết định khi lưu lượng tăng; tỷ lệ trace bị mất tăng đúng giờ cao điểm.
Một dịch vụ tải cao tạo span cho mọi truy vấn SQL và lời gọi cache; chi phí truyền và lưu trace tăng nhanh nhưng người trực vẫn không biết span nào đóng góp vào độ trễ toàn request.
API thanh toán ghi nội dung số thẻ và thông tin định danh vào span attributes; một dashboard trace dùng chung cho nhiều bộ phận hiển thị những thuộc tính không phù hợp với phạm vi truy cập.
Nhóm chỉ sử dụng tên span chung 'HTTP request' cho nhiều endpoint; khi xem service map, các request thanh toán chậm bị trộn với request kiểm tra trạng thái khỏe.
Trace của một request có client span và server span ở hai service nhưng đồng hồ hai máy lệch nhau; các khoảng thời gian hiển thị chồng chéo không phù hợp với thứ tự xử lý thực tế.
Trong một luồng tác vụ bất đồng bộ, service ghi nhận sự kiện kết thúc sau khi phản hồi HTTP; trace ban đầu kết thúc sớm nên giao diện không thể hiện toàn bộ thời gian từ đặt đơn đến giao việc.
Một số request được proxy retry sang backend khác; trace chỉ có span cho lần gọi cuối thành công, khiến đội vận hành không nhận ra hai lần thử lỗi đã làm tăng latency.
Ứng dụng thay đổi SDK observability và phát log có trace_id nhưng exporter traces chưa bật ở production; công cụ tìm log hiện liên kết đến trace không tồn tại.
Collector OpenTelemetry nhận OTLP từ nhiều dịch vụ nhưng chỉ một số service xuất hiện trên dashboard; một nhóm ứng dụng dùng resource attribute service.name trống hoặc không nhất quán.
Nhóm cùng đẩy metrics, logs và traces qua một collector duy nhất; khi backend lưu traces ngừng phản hồi, hàng đợi exporter đầy và cả telemetry của các tín hiệu khác cũng bị ảnh hưởng.
Đội vận hành cấu hình exporter telemetry gửi trực tiếp ra Internet từ mỗi pod; khi mạng egress của một namespace bị chặn, dashboard mất dữ liệu dù service vẫn trả request thành công.
Một đội triển khai collector với cấu hình sampling giống nhau cho cả môi trường thử nghiệm và production; khi traffic tăng gấp trăm lần, lượng traces hữu ích bị giới hạn bởi ngân sách ingest.
Collector nhận dữ liệu với thuộc tính environment lúc là 'production' lúc là 'prod'; service map và bộ lọc dashboard chia cùng một hệ thống thành hai nhóm quan sát riêng.
Một ứng dụng phát metric số tiền giao dịch dưới đơn vị đồng còn một service khác dùng nghìn đồng; dashboard tổng hợp không có thông tin unit rõ ràng và hiển thị doanh thu lệch lớn.
Nhóm đặt tên metric và labels theo tên lớp Java thay vì khái niệm nghiệp vụ; sau refactor, dashboard giám sát dịch vụ không còn hiển thị chuỗi dữ liệu trước đó.
Một hệ thống dùng histogram duration ở đơn vị giây nhưng dashboard hiển thị nhãn mili giây; người xem đánh giá độ trễ cao hơn hoặc thấp hơn thực tế theo sai đơn vị.
Máy chủ xử lý ảnh có CPU gần 100% khi chạy tác vụ; log không có exception và số request thấp, nhưng người trực chưa có CPU profile để xác định phần tính toán tiêu thụ thời gian.
Ứng dụng Java có độ trễ p99 tăng theo thời gian chạy; heap sử dụng tăng từng giờ rồi giảm đột ngột sau GC, trong khi metric CPU trung bình chỉ biến động nhẹ.
Đội kỹ thuật thấy container Java bị OOMKilled trong giờ cao điểm; heap dump và heap profile có nhiều đối tượng lớn nhưng chưa rõ đó là cache chủ động hay đối tượng không được giải phóng.
Một worker xử lý message có số lượng object allocation tăng mạnh sau khi đổi thư viện JSON; GC pauses kéo dài, nhưng log ứng dụng chỉ ghi nhận thời gian xử lý tổng.
Ứng dụng báo thread count tăng qua từng đợt gọi đối tác; throughput không tăng và nhiều thread đợi khóa hoặc I/O, khiến biểu đồ CPU không giải thích được độ trễ.
Một API bị nghẽn khi nhiều thread cùng cập nhật bộ nhớ chia sẻ; CPU profile không cho thấy hàm nóng rõ ràng, nhưng dữ liệu thread contention cho thấy phần lớn thời gian nằm ở chờ khóa.
Nhóm bật profiling liên tục ở mức lấy mẫu cao trên dịch vụ latency-sensitive; một số phiên bản ứng dụng bị chậm thêm dù nhu cầu quan sát ban đầu là tìm điểm nóng CPU.
Trong lúc điều tra, kỹ sư lấy một CPU profile trong 10 giây khi hệ thống đang nhàn rỗi; kết quả không thể giải thích lỗi chỉ xuất hiện trong đợt nhập dữ liệu hàng giờ.
Một backend có p95 xử lý request tốt nhưng p99 tăng khi GC stop-the-world; biểu đồ latency không được đối chiếu với sự kiện GC và dữ liệu profiler.
Ứng dụng xử lý tệp nén bằng nhiều thư viện; flame graph cho thấy nhiều stack CPU liên quan việc sao chép dữ liệu, nhưng đội phát triển chỉ kiểm tra thời gian truy vấn database.
Nhóm tạo dashboard tổng quan với hơn 40 biểu đồ nhưng không có phần mô tả trạng thái dịch vụ, error rate và latency; khi sự cố xảy ra người trực mất nhiều thời gian tìm biểu đồ liên quan.
Một dashboard so sánh request rate từ hai môi trường nhưng trục tung dùng đơn vị và mức scale khác nhau; người xem kết luận lưu lượng production giảm dù dữ liệu không có thay đổi tương ứng.
Biểu đồ dùng mức trung bình 1 giờ cho error rate trong khi outage chỉ kéo dài bốn phút; đường xu hướng trông ổn định dù nhiều request đã thất bại trong khoảng ngắn.
Nhóm ghép dashboard từ các metric theo namespace khác nhau nhưng biến lọc môi trường không áp dụng cho tất cả panel; một màn hình hiển thị các con số lẫn giữa staging và production.
Màn hình giám sát dịch vụ thể hiện hai đường p95 và p99, nhưng không ghi tỷ lệ request lỗi hoặc lưu lượng; đội trực không phân biệt tình huống ít request chậm với sự cố diện rộng.
Đội sản phẩm đặt SLO độ trễ cho thao tác tạo đơn nhưng dashboard chỉ tính latency của gateway; thời gian chờ các bước bất đồng bộ sau HTTP response không nằm trong phạm vi quan sát.
Một báo cáo SLO dùng tổng số lần trả HTTP 200 làm số thành công; dịch vụ thanh toán có response 200 chứa mã lỗi nghiệp vụ khiến chỉ số trông tốt hơn trải nghiệm thực tế.
Một dịch vụ có error budget còn rất ít sau ba đợt lỗi liên tiếp; nhóm chỉ xem trạng thái hiện tại xanh và tiếp tục phát hành mà không có góc nhìn xu hướng tiêu hao ngân sách.
Hệ thống gửi cảnh báo CPU cao mỗi khi chạy batch đêm, dù batch nằm trong lịch vận hành bình thường; người trực bỏ qua nhiều cảnh báo và bỏ lỡ một sự cố khác thực sự ảnh hưởng khách.
Đội vận hành đặt alert error rate trên cửa sổ một phút; khi traffic thấp, một request lỗi làm điện thoại trực reo, còn khi lỗi tăng từ từ qua nhiều phút thì cảnh báo đến muộn.
Một API có latency p99 cao nhưng số request rất ít và không ảnh hưởng thao tác quan trọng; mức độ khẩn cấp của alert đang ngang với dịch vụ thanh toán ngừng hoạt động.
Prometheus alert firing nhưng Alertmanager không gửi thông báo do một silence từ ca bảo trì trước còn hiệu lực; đội trực chỉ quan sát hệ thống nhận cảnh báo nên không biết dữ liệu vẫn được thu thập.
Một cảnh báo thành công sau khi nhóm đổi receiver sang kênh chat mới nhưng không có runbook, dashboard hoặc link trace đi kèm; người trực nhận tin mà vẫn thiếu dữ kiện để bắt đầu điều tra.
Trong sự cố mất kết nối database, nhiều service đồng thời phát cảnh báo timeout, queue length và retry; đội trực nhận hàng trăm notification phụ thuộc trong khi nguyên nhân gốc chỉ nằm ở một cụm DB.
Nhóm chỉ kiểm tra rằng alert rule hợp lệ và firing ở môi trường thử nghiệm; khi sự cố production thật diễn ra, kênh nhận cuối đã đổi thông tin tích hợp và không ai được thông báo.
Đội SRE đánh giá sau sự cố rằng hệ thống đã phục hồi nhưng dashboard còn hiển thị lỗi; metrics, logs và traces có độ trễ ingest khác nhau khiến một số nguồn trông như dữ liệu quá khứ.
Một dịch vụ xuất metrics đều đặn nhưng log và trace biến mất sau một lần deploy; nhóm trực chưa có phép kiểm tra tính đầy đủ và health của từng pipeline telemetry riêng biệt.
Ứng dụng trải qua sự cố hiệu năng sau một bản phát hành nhưng không gắn version/deployment metadata vào telemetry; kỹ sư không thể so sánh p99 theo phiên bản code trước và sau đổi.
Nhóm lưu metrics ngắn hạn chỉ bảy ngày trong khi sự cố hiệu năng có chu kỳ theo tháng; lúc so sánh dịp trả lương, dữ liệu tuần tương ứng tháng trước không còn.
Hệ thống lưu log debug toàn bộ trong một năm nhưng xóa traces sau một giờ; khi khách báo lỗi hôm qua, log còn nhiều nhưng trace phân tán giúp liên kết các service đã hết hạn.
Một cụm đa vùng phát metrics về cùng nơi lưu trữ mà không gắn region nhất quán; khi một vùng mất mạng, biểu đồ tổng thể giảm còn nhóm không biết đó là mất lưu lượng hay mất telemetry.
Người vận hành xem hai biểu đồ request rate và CPU có xu hướng tăng cùng lúc rồi kết luận CPU gây lỗi; trace các request lỗi lại cho thấy nhiều thời gian nằm ở upstream chờ I/O.
Một dịch vụ bị p99 tăng sau khi cấu hình log thay đổi; đội trực chỉ dựa vào log mới nhiều hơn để kết luận traffic tăng mà chưa đối chiếu số request thực tế và profile CPU.
Đội ứng cứu bắt đầu điều tra bằng các giả thuyết khác nhau ở từng nhóm; metrics chỉ ra thời điểm lỗi, logs mô tả thông điệp và trace chỉ ra service chậm nhưng chưa ai liên kết cả ba theo một timeline chung.
Một API chỉ lỗi khi gọi đối tác thứ ba với tenant cụ thể; dashboard tổng hợp xanh, nhưng trace và structured log của các request đó chứa nhãn tenant không nhất quán nên khó truy vấn đúng tập sự kiện.
Trong một sự cố, alert được kích hoạt sau khi latency tăng nhưng log chỉ xuất hiện ở một pod; danh sách version, region và pod từ metric không được liên kết với log khiến việc khoanh vùng tốn nhiều thời gian.
Một nhóm thử thêm agent quan sát vào tất cả service trong một ngày mà không có baseline về CPU, memory, p95 và chi phí; sau triển khai, ứng dụng chậm hơn nhưng chưa biết phần overhead do telemetry.
