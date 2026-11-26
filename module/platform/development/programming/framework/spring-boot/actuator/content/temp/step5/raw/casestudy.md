Một ứng dụng Spring Boot có HTTP API hoạt động bình thường nhưng endpoint Actuator health trả về DOWN vì một hệ thống báo cáo phụ trợ bị ngắt, khiến bộ cân bằng tải ngừng chuyển toàn bộ yêu cầu.
Đội vận hành dựa vào trạng thái UP của health endpoint để xác nhận hệ thống thanh toán sẵn sàng, nhưng một tác vụ nền bắt buộc chưa khởi động và yêu cầu đầu tiên của khách vẫn thất bại.
Một dịch vụ đặt hàng thêm custom HealthIndicator kiểm tra kết nối tới đối tác mỗi lần được gọi, nhưng đối tác phản hồi chậm làm chính endpoint health vượt timeout của hệ thống giám sát.
Spring Boot Actuator tổng hợp nhiều health contributors thành trạng thái DOWN khi cache dùng cho chức năng không thiết yếu gặp lỗi, trong khi các giao dịch cốt lõi vẫn phục vụ được.
Một HealthIndicator tùy biến chỉ kiểm tra cổng TCP mở nhưng không xác minh khả năng thực hiện thao tác nghiệp vụ; dashboard hiện UP dù dịch vụ đích trả lỗi cho mọi request.
Đội phát triển tạo custom health check gọi một endpoint yêu cầu xác thực bằng token ngắn hạn, nhưng token hết hạn làm cả cụm ứng dụng bị đánh dấu không khỏe.
Một hệ thống dùng PostgreSQL và Redis có health indicators riêng, nhưng một bản phát hành đổi cấu hình Redis khiến liveness của pod bị ảnh hưởng theo cách không mong muốn.
Ứng dụng điều phối đơn hàng trả health tổng hợp UP dù không thể ghi vào database ở chế độ chỉ đọc, khiến đơn mới liên tục thất bại nhưng hệ thống điều phối vẫn xem là khỏe.
Một HealthIndicator tự viết ném exception khi thiếu cấu hình URL và không trả thông tin chẩn đoán phù hợp, làm đội trực không xác định được thành phần nào đang lỗi.
Nhóm vận hành bật chi tiết health cho việc gỡ lỗi, nhưng JSON phản hồi chứa tên máy nội bộ và thông tin kết nối đến hạ tầng mà người xem không cần được biết.
Một cụm Spring Boot có ba phiên bản ứng dụng chạy đồng thời, nhưng mỗi phiên bản đặt tên custom health contributor khác nhau khiến dashboard khó so sánh tình trạng của các pod.
Ứng dụng lưu kết quả health check trong cache quá lâu để giảm tải, khiến endpoint tiếp tục báo UP nhiều phút sau khi cơ sở dữ liệu đã mất kết nối.
Nhóm triển khai health endpoint được gọi mỗi giây từ hàng trăm probe nhưng custom indicator truy vấn database nặng; số kết nối và tải truy vấn tăng mạnh mà không đến từ người dùng.
Một dịch vụ phụ thuộc vào hệ thống cấp khóa mã hóa nhưng health check chỉ xét kết nối database, khiến trạng thái UP che giấu việc không thể xử lý dữ liệu mới.
Đội tích hợp kỳ vọng health indicator của thành phần mới xuất hiện tự động, nhưng thư viện tùy biến không đăng ký contributor trong ứng dụng; endpoint health thiếu thành phần cần giám sát.
Một ứng dụng khai báo tên health group cho thanh toán và tra cứu, nhưng một thay đổi cấu hình khiến thành phần kiểm tra thanh toán xuất hiện trong group tra cứu và tạo cảnh báo sai.
Nhóm vận hành chỉnh HTTP status mapping cho một trạng thái health tùy biến, nhưng trạng thái này hiển thị bằng mã HTTP thành công khiến công cụ giám sát bỏ qua lỗi.
Ứng dụng trả chi tiết trạng thái UNKNOWN khi kho dữ liệu phản hồi không rõ ràng, nhưng đội trực đang diễn giải UNKNOWN thành DOWN nên toàn bộ hệ thống bị báo sự cố nghiêm trọng.
Một dịch vụ đính kèm thông tin vùng triển khai trong health details nhưng hai cụm dùng tên vùng không thống nhất; quá trình khoanh vùng lỗi qua dashboard bị nhầm lẫn.
Ứng dụng chứa nhiều HealthIndicator chạy song song không được giới hạn chi phí; khi một phụ thuộc chập chờn, các phép kiểm tra liên tiếp gây thêm áp lực lên hệ thống đang lỗi.
Một pod Spring Boot chỉ được cấu hình liveness probe, chưa có readiness probe cho giai đoạn khởi tạo tài nguyên; Kubernetes chuyển lưu lượng tới pod quá sớm và request đầu tiên của khách thất bại.
Đội Kubernetes trỏ liveness probe vào health group có kiểm tra database bên ngoài; khi database tạm ngắt, hàng loạt pod bị khởi động lại dù tiến trình vẫn hoạt động bình thường.
Một ứng dụng dùng readiness probe để tạm ngừng nhận request khi một dịch vụ bắt buộc ngắt kết nối, nhưng trạng thái readiness không đổi sau khi kết nối không còn khả dụng.
Nhóm vận hành cấu hình readiness và liveness dùng chung URL health tổng hợp, khiến hai cơ chế phục hồi phản ứng giống nhau trước lỗi phụ thuộc mạng.
Trong đợt rolling deployment, pod mới có health UP nhưng chưa hoàn thành warm-up cache lớn; lưu lượng bị chuyển sang quá sớm và p99 response tăng đột biến.
Một service đang shutdown để triển khai bản mới nhưng readiness vẫn báo nhận traffic thêm vài giây, khiến các request dài bị ngắt trước khi hoàn thành.
Ứng dụng thiết lập management port riêng cho Actuator, nhưng Kubernetes chỉ kiểm tra probe trên cổng quản trị; cổng HTTP nghiệp vụ hỏng vẫn không bị phát hiện.
Đội triển khai đặt actuator base-path khác giữa hai môi trường và giữ nguyên manifest readiness probe, khiến toàn bộ pod production trả 404 tại đường dẫn kiểm tra.
Một ứng dụng Spring Boot chạy dưới context path riêng, nhưng cấu hình liveness probe dùng đường dẫn mặc định và báo lỗi ngay sau nâng cấp gateway.
Nhóm đặt initialDelaySeconds của liveness probe quá ngắn cho ứng dụng cần xây dựng chỉ mục khi startup; Kubernetes liên tục restart pod trước khi quá trình khởi động hoàn tất.
Một dịch vụ batch dùng startup probe để phân biệt khởi động lâu với tiến trình treo, nhưng giới hạn thời gian không phù hợp tải thực tế nên pod không vượt qua vòng khởi động.
Pod đang xử lý hàng nghìn yêu cầu khi nhận tín hiệu scale down nhưng health endpoint vẫn báo sẵn sàng cho request mới; các giao dịch bị mất giữa quá trình dừng.
Ứng dụng được đánh dấu readiness DOWN do một phụ thuộc không thiết yếu gặp lỗi, khiến cả vùng không còn pod nhận traffic mặc dù chức năng chính có thể tiếp tục.
Nhóm chỉ kiểm tra trạng thái HTTP của readiness mà không quan sát thành phần gây lỗi; sau một sự cố liên tục, thời gian điều tra kéo dài vì không biết phụ thuộc nào đang hỏng.
Một container có endpoint liveness hoạt động qua management port nhưng hàng đợi xử lý nghiệp vụ đã bị deadlock; Kubernetes vẫn giữ pod trong trạng thái khỏe.
Trong đợt thay đổi cấu hình datasource, health probe kiểm tra connection pool trước khi migration hoàn tất; các pod luân phiên được nhận traffic rồi bị loại khỏi Service.
Một ứng dụng đặt probe timeout quá ngắn trong khi máy chủ đang chịu tải CPU cao; Kubernetes đánh dấu pod không khỏe dù ứng dụng vẫn trả request người dùng.
Đội triển khai readiness phụ thuộc một API bên ngoài đang gặp sự cố toàn khu vực, khiến việc khởi động pod thay thế không cải thiện khả năng cung cấp dịch vụ.
Service gửi tín hiệu không sẵn sàng trước khi giải phóng tài nguyên nhưng gateway giữ kết nối đã mở lâu; nhiều request tiếp tục đến pod sắp tắt và gặp lỗi ngắt kết nối.
Một ứng dụng chạy được ngoài Kubernetes nhưng không bật health probe theo profile cloud; khi triển khai container, các endpoint dự kiến không xuất hiện và rollout bị treo.
Một bản phát hành Spring Boot bật Actuator dependency nhưng người quản trị kỳ vọng mọi endpoint đều có thể truy cập; các URL như metrics và loggers trả 404 sau khi triển khai.
Nhóm triển khai cấu hình exposure qua HTTP cho tất cả Actuator endpoints để thuận tiện debug, nhưng endpoint có thể tiết lộ thông tin cấu hình ứng dụng ra ngoài mạng quản trị.
Một dịch vụ có management server port riêng nhưng firewall chỉ cho phép cổng nghiệp vụ, khiến Prometheus không thể scrape metrics dù người dùng vẫn dùng được API.
Đội vận hành đưa Actuator sau API gateway có cơ chế đổi đường dẫn, nhưng bộ công cụ gọi endpoint /actuator/metrics không biết base path mới và báo thiếu dữ liệu.
Một ứng dụng di chuyển Actuator sang cổng khác để tách lưu lượng quản trị nhưng SecurityFilterChain chỉ bảo vệ cổng nghiệp vụ, tạo ra lỗ hổng truy cập endpoint quản trị.
Nhóm tạo thêm custom Actuator endpoint phục vụ thống kê nội bộ, nhưng cấu hình quyền truy cập giống endpoint health công khai khiến khách có thể đọc số liệu vận hành.
Một hệ thống bật khả năng thay đổi log level qua endpoint loggers cho môi trường production, nhưng nhân viên không có nhiệm vụ vận hành cũng được quyền cập nhật mức log.
Nhà vận hành cho phép gọi endpoint shutdown từ mạng nội bộ mà không có xác thực phù hợp; một yêu cầu nhầm từ công cụ kiểm thử làm dịch vụ ngừng hoạt động.
Ứng dụng bật endpoint env để chẩn đoán cấu hình nhưng cấu hình sanitization không được rà soát; phản hồi chứa các giá trị môi trường ngoài mức cần thiết cho người xem.
Đội mở endpoint configprops cho mọi nhân viên để hỗ trợ tích hợp, nhưng dữ liệu phản hồi thể hiện cấu trúc cấu hình nội bộ và thông tin về dịch vụ phụ thuộc nhạy cảm.
Một frontend truy cập Actuator trực tiếp từ trình duyệt với CORS chưa được kiểm soát đúng; dashboard nội bộ không hiển thị metrics còn một origin lạ được phép gửi yêu cầu.
Ứng dụng kết hợp Spring Security với actuator endpoint matcher nhưng một lần thay đổi base path khiến quy tắc kiểm soát đường dẫn không còn bao phủ URL quản trị.
Nhóm sử dụng cùng một credential cho quản trị Actuator và truy cập API người dùng; khi credential bị lộ, kẻ tấn công có thể quan sát trạng thái hạ tầng.
Một service xuất bản endpoint beans và mappings ra mạng công cộng để hỗ trợ gỡ lỗi; người không được phân quyền có thể suy ra cấu trúc handler và thành phần ứng dụng.
Đội triển khai bảo vệ endpoints bằng role ADMIN nhưng tài khoản hệ thống giám sát chỉ có role METRICS; việc scrape bắt đầu trả 403 sau thay đổi phân quyền.
Một custom endpoint cho phép cập nhật trạng thái tính năng bằng HTTP nhưng không giới hạn phương thức và danh tính người gọi; các thao tác quản trị xuất hiện trong lịch sử request không kiểm soát.
Nhóm chỉ bảo vệ endpoint heapdump qua gateway trong khi Actuator còn có đường truy cập trực tiếp qua management port; dữ liệu bộ nhớ của ứng dụng vẫn có thể bị tải xuống.
Trong môi trường đa tenant, endpoint metrics có tag chứa tenantId và được cấp cho nhóm xem báo cáo chung; người dùng từ tenant khác nhìn thấy thông tin vận hành chéo nhau.
Ứng dụng bật endpoint auditevents nhưng hệ thống không ghi nhận các thay đổi cấu hình quản trị quan trọng; đội kiểm toán không thể đối chiếu ai đã làm biến đổi hệ thống.
Đội bảo mật xoay chứng chỉ TLS ở management port nhưng một phần công cụ health/monitoring không tin cậy chuỗi chứng chỉ mới; metrics mất dữ liệu trong nhiều giờ.
Nhóm thay đổi cấu hình network policy và vô tình cho phép truy cập Actuator từ pod không thuộc nhóm giám sát; việc phân đoạn mạng quản trị không còn đúng yêu cầu.
Ứng dụng Spring Boot nhận cấu hình từ nhiều profile, nhưng endpoint env chỉ ra giá trị datasource khác kỳ vọng và nhóm vận hành không biết nguồn thuộc tính có độ ưu tiên cao hơn.
Một bản phát hành đọc cấu hình feature flag từ biến môi trường nhưng nhà vận hành chỉ kiểm tra application properties; endpoint configprops cho thấy một giá trị đã được ràng buộc ngoài dự kiến.
Nhóm dùng endpoint conditions để tìm lý do một auto-configuration không kích hoạt, nhưng điều kiện môi trường thay đổi giữa các pod nên hành vi datasource không đồng nhất.
Một ứng dụng bổ sung starter mới và xuất hiện nhiều bean trùng chức năng; endpoint beans giúp nhận diện cấu trúc nhưng đội phát triển không biết bean nào thật sự xử lý request.
Đội nâng cấp Spring Boot làm một endpoint controller biến mất sau lần refactor; dữ liệu mappings trên production khác bản staging và gateway bắt đầu trả 404.
Service cấu hình nhiều scheduled jobs nhưng một tác vụ không chạy sau deploy; endpoint scheduledtasks hiển thị lịch khác kỳ vọng trong khi log chưa báo lỗi trực tiếp.
Nhóm triển khai cache nghiệp vụ mới nhưng số liệu endpoint caches không khớp danh sách cache mà ứng dụng thực dùng, khiến bộ phận vận hành nghĩ cache không hoạt động.
Ứng dụng dùng endpoint info để hiển thị phiên bản phát hành nhưng metadata build không được đóng gói trong container mới; đội trực không xác định được bản đang chạy.
Nhóm triển khai nhiều bản ứng dụng có cùng build version trong info, nhưng cấu hình môi trường khác nhau gây hành vi khác và làm khó việc đối chiếu rollout.
Một ứng dụng thay đổi cấu hình logging qua endpoint loggers nhưng khi restart pod thì log level trở về mức cũ, khiến buổi điều tra sự cố hôm sau mất thông tin.
Đội vận hành bật DEBUG qua endpoint loggers cho package rất rộng trong giờ cao điểm; dung lượng log tăng nhanh và thời gian phản hồi API bị ảnh hưởng.
Một sự cố chỉ xảy ra vài phút mỗi ngày nhưng endpoint loggers thay đổi log level quá muộn; các bản ghi quan trọng trước thời điểm kích hoạt đã không được giữ lại.
Nhóm triển khai endpoint logfile cho môi trường lưu log ở stdout, nhưng công cụ trực vẫn kỳ vọng có thể tải tệp log từ Actuator và nhận phản hồi không như dự kiến.
Ứng dụng ghi log vào tệp luân chuyển theo giờ nhưng endpoint logfile được cấu hình theo tệp cố định; nhân viên gỡ lỗi nhìn thấy dữ liệu cũ thay vì lỗi vừa xảy ra.
Trong đợt tải cao, endpoint threaddump cho thấy nhiều thread chờ trên cùng lock nhưng dashboard metrics chỉ báo CPU thấp; nhóm không phát hiện nguyên nhân request bị treo.
Đội gỡ lỗi sử dụng endpoint heapdump khi container gần chạm giới hạn bộ nhớ; thao tác thu thập dữ liệu tạo thêm áp lực tài nguyên và pod bị OOM trước khi tải xong.
Một heap dump được tạo để phân tích rò rỉ bộ nhớ nhưng chứa token và thông tin khách hàng trong object heap; file dump bị chuyển sang nơi lưu trữ không đủ kiểm soát.
Ứng dụng cấu hình HTTP exchanges để điều tra request thất bại nhưng không cung cấp repository lưu dấu tương ứng; endpoint không có dữ liệu lịch sử mà nhóm kỳ vọng.
Đội trực dùng dữ liệu HTTP exchanges để điều tra lỗi người dùng nhưng lượng request rất lớn khiến lịch sử giữ được quá ít bản ghi và không còn sự kiện cần tìm.
Một ứng dụng cần chứng minh thời gian khởi động theo từng bước nhưng không có cơ chế ghi sự kiện startup phù hợp; endpoint startup không hỗ trợ việc phân tích như kỳ vọng.
Nhóm vận hành mở endpoint flyway để kiểm tra migration nhưng không giới hạn quyền; tên các bảng và lịch sử thay đổi schema trở thành dữ liệu có thể xem rộng rãi.
Đội triển khai gặp lỗi Liquibase khi startup, nhưng hệ thống chỉ giám sát health và không đối chiếu trạng thái migration; pod bị restart nhiều lần mà nguyên nhân không rõ.
Một endpoint quản trị tùy biến trả danh sách các tác vụ đang xử lý, nhưng cấu trúc JSON thay đổi sau nâng cấp và dashboard vận hành không còn giải mã được phản hồi.
Nhóm sử dụng endpoint env để so sánh hai pod nhưng dữ liệu thuộc tính có giá trị được che đi; cách đối chiếu hiện tại nhầm sự khác biệt thực tế với giá trị đã được bảo vệ.
Một ứng dụng bật Micrometer metrics qua Actuator nhưng dashboard chỉ thấy JVM memory mà thiếu chỉ số số đơn hàng được xử lý thành công; nghiệp vụ không có thước đo kết quả.
Đội phát triển đo số request bằng counter riêng nhưng tăng counter cả khi request bị retry; số lượng giao dịch hoàn tất trên dashboard cao hơn dữ liệu trong database.
Một nhóm đo thời gian xử lý thanh toán bằng Timer nhưng không phân biệt thời gian chờ hàng đợi với thời gian xử lý business logic; cảnh báo latency không chỉ ra nguyên nhân.
Ứng dụng dùng Gauge để theo dõi số tác vụ đang chờ nhưng đối tượng được đo không còn được giữ tham chiếu; biểu đồ biến mất sau một đợt thu gom bộ nhớ.
Nhóm tạo một Timer mới cho từng mã đơn hàng trong Spring Boot; số meter và lượng tag tăng theo giao dịch, gây áp lực bộ nhớ trên ứng dụng và hệ thống giám sát.
Đội thêm tag request URI với ID khách hàng vào metrics HTTP, khiến số lượng chuỗi dữ liệu tăng vọt khi production có hàng triệu request mỗi ngày.
Một service gắn username vào tag Micrometer để phân tích lỗi đăng nhập; dữ liệu giám sát vừa tăng cardinality vừa lưu thông tin định danh nhạy cảm.
Ứng dụng báo số lượng active connections bằng counter chỉ tăng không giảm, nhưng dashboard diễn giải đó là số kết nối đang tồn tại và kết luận sai về rò rỉ.
Nhóm đặt tên một meter về độ trễ theo đơn vị mili giây nhưng thư viện và Prometheus hiển thị giá trị bằng đơn vị khác; ngưỡng cảnh báo bị lệch đáng kể.
Trong giờ cao điểm, Timer chỉ được phân tích bằng mean latency; một tỷ lệ nhỏ request chậm hàng chục giây bị che khuất trong báo cáo hiệu năng.
Đội vận hành muốn theo dõi p95/p99 request time nhưng histogram chưa được cấu hình cho meter tương ứng; dashboard Prometheus không tính được phân phối như kỳ vọng.
Một ứng dụng ghi metric thất bại theo nhãn exception chứa cả câu thông báo lỗi động; mỗi lỗi có mã khách hàng khác nhau làm số time series tăng nhanh.
Nhóm dùng Micrometer common tags để phân biệt môi trường nhưng một instance thiếu tag deployment, khiến dữ liệu từ staging và production bị gộp trên dashboard.
Ứng dụng đo số lượng task trong thread pool bằng một Gauge, nhưng thread pool được thay khi reload cấu hình; meter tiếp tục tham chiếu pool cũ và hiển thị số liệu không đổi.
Nhóm tích hợp @Timed cho hàm nghiệp vụ rồi kỳ vọng mọi lời gọi nội bộ đều được đo, nhưng các lời gọi qua chính object hiện tại không tạo series mà dashboard mong đợi.
Ứng dụng có hai đường xử lý đồng bộ và reactive nhưng cùng dùng một metric name với tập tag khác nhau; truy vấn báo cáo hợp nhất hai loại công việc không nhất quán.
Đội phát triển muốn đo số bản tin tồn đọng nhưng chỉ tăng counter khi nhận message, không có thước đo số message đã hoàn tất; dashboard không phản ánh queue depth.
Một hệ thống gọi API đối tác qua WebClient có độ trễ cao nhưng metrics HTTP server vẫn bình thường; đội trực thiếu tín hiệu để phân biệt chậm downstream với chậm của ứng dụng.
Ứng dụng xuất metric cho lỗi database theo tên bảng SQL riêng lẻ; một lần triển khai đa tenant khiến số nhãn và dung lượng giám sát tăng vượt ngân sách.
Nhóm thêm meter đo cache hit nhưng sử dụng cùng tên cho số request và tỷ lệ phần trăm; Prometheus báo lỗi hoặc các đồ thị khó phân biệt loại đơn vị.
Một nhà vận hành chỉnh các bộ lọc MeterFilter để giảm số nhãn, nhưng bộ lọc loại luôn meter quan trọng của giao dịch thanh toán và các cảnh báo trở nên im lặng.
Đội chuyển từ registry trong bộ nhớ sang Prometheus registry nhưng không thử endpoint Actuator mới; dashboard tiếp tục hiển thị dữ liệu cũ thay vì metrics thực tế.
Ứng dụng có nhiều thread pool và connection pool nhưng metrics mới chỉ phản ánh heap JVM; sự cố chờ connection bị nhầm là vấn đề CPU.
Nhóm tạo histogram với quá nhiều bucket cho hàng trăm loại thao tác, khiến số lượng series trên Prometheus và chi phí lưu trữ tăng bất thường.
Ứng dụng tăng số lượng MeterRegistry trong các bean cấu hình tùy biến, dẫn đến cùng giao dịch được ghi nhiều lần hoặc dữ liệu phân tán giữa các registry.
Đội triển khai /actuator/prometheus trên local thành công nhưng image production thiếu dependency cần thiết; Prometheus nhận 404 khi scrape pod mới.
Một ServiceMonitor trỏ Prometheus đến đường dẫn /metrics thay vì endpoint Actuator được cấu hình, khiến các target bị đánh dấu lỗi dù ứng dụng hoạt động bình thường.
Đội chuyển Actuator sang management port riêng nhưng cấu hình scrape vẫn dùng application port; Prometheus ngừng thu thập series từ phiên bản mới.
Ứng dụng được đặt sau ingress chỉ dùng HTTPS, nhưng Prometheus tiếp tục scrape qua HTTP và gặp lỗi chuyển hướng hoặc xác thực TLS.
Nhóm giám sát dùng authentication để bảo vệ /actuator/prometheus nhưng scrape job chưa có credential phù hợp; toàn bộ metrics của dịch vụ biến mất sau thay đổi bảo mật.
Prometheus scrape mỗi phút trong khi một container tồn tại chưa đến một phút ở giờ cao điểm; số liệu của các pod ngắn hạn bị thiếu trong báo cáo sự cố.
Đội tăng tần suất scrape lên rất cao để thu tín hiệu chi tiết, nhưng custom metrics endpoint phải tính toán số liệu tốn CPU và làm ảnh hưởng request người dùng.
Một lần autoscale tạo thêm nhiều instance và metric tổng được cộng trực tiếp không phân biệt các counter reset khi pod restart; dashboard hiển thị biến động sai.
Ứng dụng ghi counter cho các sự kiện thanh toán nhưng dashboard dùng giá trị tích lũy thay vì tốc độ tăng; cảnh báo đột biến lưu lượng không phản ánh tình huống thực.
Nhóm triển khai alert dựa trên tỷ lệ lỗi nhưng bỏ qua trường hợp lưu lượng thấp; vài request lỗi trong đêm tạo cảnh báo nghiêm trọng không tương xứng.
Một cảnh báo hệ thống dựa trên CPU cao và heap dùng nhiều, nhưng service đang chết dần do connection pool cạn; Prometheus không có tín hiệu đủ để phát hiện sớm.
Trong đợt rolling update, hai phiên bản ứng dụng xuất metric với tên khác nhau; biểu đồ một phần đột ngột về không dù nghiệp vụ vẫn hoạt động.
Một query PromQL kết hợp series có label instance và series chỉ có label service mà không khớp đúng chiều; tỷ lệ lỗi hiển thị là không có dữ liệu.
Đội triển khai nhiều cụm Kubernetes dùng chung Prometheus nhưng quên nhãn cluster, khiến dữ liệu các vùng bị gộp và việc xác định vùng sự cố trở nên khó khăn.
Nhóm dùng scrape target trạng thái UP để kết luận nghiệp vụ khỏe, nhưng endpoint Prometheus vẫn trả dữ liệu khi database đã không thể ghi đơn hàng mới.
Một service đặt metric tag chứa ID phiên làm nhãn, khiến Prometheus gần đầy bộ nhớ khi người dùng tăng nhanh; hệ thống giám sát gặp sự cố đúng lúc cần điều tra.
Trong một sự cố network partition, Prometheus không scrape được ứng dụng nhưng dashboard mặc định hiển thị giá trị gần nhất; đội trực nhầm rằng hệ thống vẫn ổn định.
Đội quản trị đặt retention rất ngắn để tiết kiệm dung lượng Prometheus, khiến không còn dữ liệu đối chiếu mức sử dụng tài nguyên trước và sau bản phát hành tuần trước.
Ứng dụng xuất metrics bằng tên tiếng Anh không thống nhất giữa các đội; khi tổng hợp nhiều service, dashboard dùng sai phép tính và đưa ra số SLA không chính xác.
Nhóm dùng histogram từ Micrometer để đo latency nhưng dashboard trộn bucket từ các cấu hình không tương thích giữa phiên bản; p99 tổng hợp trở nên không đáng tin.
Đội triển khai ghi số lượng request theo status code nhưng không theo route chuẩn hóa; những URL có mã giao dịch riêng làm bảng thống kê bùng nổ nhãn.
Một thay đổi cấu hình quản trị mở /actuator/prometheus cho bên ngoài và cho phép đọc toàn bộ nhãn dịch vụ; tên hạ tầng, vùng triển khai và loại khách hàng bị lộ.
Ứng dụng gắn trace ID vào log HTTP nhưng không truyền context sang tác vụ async; đội gỡ lỗi không ghép được lỗi xử lý nền với request ban đầu dù Actuator metrics còn đủ.
Nhóm áp dụng Micrometer Observation cho một service nhưng tạo span mới không mang ngữ cảnh cha khi gọi downstream; tracing bị chia thành nhiều luồng riêng rẽ.
Đội trực thấy tỷ lệ HTTP 500 tăng trong metrics nhưng endpoint loggers vẫn ghi quá ít chi tiết về exception; quá trình lần ra nguyên nhân kéo dài.
Ứng dụng chỉ bật actuator metrics khi profile production hoạt động nhưng tài khoản QA cần đánh giá staging; hai môi trường không có số liệu so sánh khi kiểm thử tải.
Một batch job chạy lúc nửa đêm làm CPU tăng nhưng metrics chỉ phân biệt route HTTP, khiến đợt tải nền không xuất hiện trên dashboard nghiệp vụ.
Nhóm thu thập log DEBUG để chẩn đoán lỗi auth, nhưng log chứa header xác thực và tham số nhạy cảm; rủi ro quyền riêng tư tăng trong khi hoạt động điều tra diễn ra.
Một service bị lỗi deadlock theo chu kỳ nhưng nhóm chỉ kích hoạt threaddump sau khi pod được Kubernetes restart; bằng chứng về các thread đang khóa nhau đã biến mất.
Đội vận hành xem endpoint metrics để chẩn đoán memory leak nhưng chỉ xét heap used, không xem số thread và direct memory; ứng dụng vẫn bị OOM khi heap còn dư.
Ứng dụng cấu hình health endpoint là thành công nhưng mọi request trả HTTP 429 vì pool quá tải; bộ phận trực chỉ nhìn readiness và bỏ qua tỷ lệ từ chối.
Một nhóm mở loggers endpoint trong môi trường production để điều tra ngắn hạn, nhưng không có quy trình ghi nhận ai đã đổi mức log và khi nào trả lại cấu hình.
Đội phân tích lỗi phân tán dùng tags theo tenant để lọc metrics nhưng bỏ qua giới hạn cardinality; một khách hàng phát sinh hàng nghìn mã sản phẩm làm dashboard mất ổn định.
Ứng dụng triển khai metrics tùy biến cho retry HTTP nhưng ghi một counter chung cho retry thành công và retry thất bại; nhóm vận hành không ước lượng được mức độ ảnh hưởng.
Một service có tình trạng lỗi âm thầm trong background scheduler nhưng endpoint health chỉ xét kết nối mạng; dashboard hiển thị khỏe dù dữ liệu báo cáo không cập nhật.
Nhóm thiết kế custom HealthIndicator để kiểm tra queue broker, nhưng trả DOWN khi queue rỗng; ứng dụng bị đánh dấu không khỏe vào đúng thời điểm không có công việc.
Một hệ thống có phụ thuộc optional vào dịch vụ email, nhưng readiness group bao gồm health của SMTP; sự cố gửi email làm dừng chức năng tra cứu hoàn toàn độc lập.
Ứng dụng báo OUT_OF_SERVICE khi tiến trình migration đang chạy, nhưng HTTP status mapping cho group readiness khác với tool triển khai kỳ vọng nên deployment tiếp tục sai giai đoạn.
Nhóm triển khai health nhóm có tên tùy chỉnh nhưng ứng dụng mới thiếu một contributor do điều kiện auto-configuration thay đổi; status tổng hợp trở nên quá lạc quan.
Một tổ chức cần theo dõi trạng thái nghiệp vụ của hệ thống thanh toán, nhưng custom indicator đang trả UP khi bất kỳ một trong ba kênh thanh toán còn sống, không xét cam kết dịch vụ.
Đội phát triển viết ReactiveHealthIndicator với lời gọi HTTP đồng bộ ngay trên event loop WebFlux; khi đối tác chậm, readiness check làm tăng độ trễ cả những API đang phục vụ.
Ứng dụng tạo custom endpoint ghi trạng thái bảo trì nhưng không tách truy cập đọc và ghi; một script giám sát cấu hình nhầm phương thức làm thay đổi trạng thái.
Nhóm thay cấu hình cơ chế health group theo profile, khiến staging có thông tin chi tiết còn production chỉ báo DOWN chung chung mà không đủ ngữ cảnh điều tra.
Spring Boot service có nhiều datasource khác nhau nhưng endpoint health chỉ xem datasource chính; khi kho báo cáo hỏng, tác vụ báo cáo vẫn thất bại mà trạng thái tổng thể UP.
Một ứng dụng cần giữ readiness DOWN đến khi đồng bộ dữ liệu hoàn tất, nhưng callback hoàn thành job không cập nhật ApplicationAvailability và pod bị cô lập lâu hơn dự kiến.
Đội phát triển dùng custom status cho trạng thái DEGRADED nhưng hệ thống tổng hợp không biết thứ tự ưu tiên phù hợp, khiến trạng thái nghiêm trọng hơn bị che bởi trạng thái khác.
Trong một cuộc thử tải, endpoint threaddump được gọi liên tục và tạo các phản hồi lớn; sự hiện diện của công cụ quan sát làm tăng tải trên pod vốn đang gần giới hạn.
Một custom Actuator endpoint dùng thao tác ghi để chuyển hệ thống sang chế độ bảo trì, nhưng công cụ điều hành chỉ ghi lại lần đọc trạng thái nên không truy vết được ai đã chuyển chế độ.
Một pod Spring Boot dùng ổ đĩa tạm gần cạn inode để tạo báo cáo, nhưng chỉ số health dung lượng trống vẫn tốt; thao tác ghi tệp thất bại dù Kubernetes còn đánh dấu pod sẵn sàng.
Đội triển khai điều kiện cảnh báo cho scrape thất bại nhưng không phân biệt downtime có kế hoạch với lỗi ngoài ý muốn, khiến paging liên tục trong đợt bảo trì lớn.
Một dashboard tổng hợp số request của nhiều instance nhưng không bỏ qua nhãn version thay đổi sau deploy; dữ liệu bị phân mảnh và chỉ số toàn dịch vụ thấp giả tạo.
Nhóm đo thời gian khởi động ứng dụng bằng log thủ công, nhưng các mốc startup của Spring Boot không được lưu nhất quán giữa lần khởi động nóng và lạnh.
Ứng dụng gửi metrics đến backend giám sát bên ngoài nhưng môi trường mới hạn chế egress; Actuator /metrics còn dữ liệu tại chỗ trong khi dashboard trung tâm trống.
Một hệ thống thu thập Prometheus tại cổng quản trị nhưng chính sách service discovery không tìm thấy các pod vừa autoscale; cảnh báo dựa trên dữ liệu thiếu một nửa instance.
Nhóm vận hành ghi log mức TRACE cho package xử lý thông điệp trong thời gian dài và gây tăng dung lượng disk; readiness vẫn UP dù file system gần đầy.
Một ứng dụng chạy trong container read-only filesystem nhưng cấu hình endpoint logfile trỏ tới vị trí không thể tạo file; khi có sự cố, đội trực không truy xuất được log mong đợi.
Trong đợt nâng Spring Boot, endpoint exposure và chi tiết health thay đổi theo cấu hình, nhưng bài kiểm thử hồi quy chỉ kiểm tra API nghiệp vụ nên lỗ hổng quản trị không được phát hiện.
Đội QA viết test cho HealthIndicator chỉ kiểm tra kết quả UP nhưng không mô phỏng timeout, quyền truy cập bị từ chối và lỗi downstream; sự cố thật làm trạng thái không chính xác.
Nhóm kiểm thử endpoint loggers bằng một tài khoản quản trị duy nhất, nhưng không kiểm tra tài khoản chỉ đọc; production có cấu hình phân quyền khiến nhân viên hỗ trợ thay đổi được log level.
Một bộ test Micrometer chỉ xác nhận meter tồn tại trong SimpleMeterRegistry, nhưng không kiểm tra số liệu được xuất qua Prometheus sau khi thêm tag và filter ở production.
Đội tích hợp dùng mô phỏng Prometheus scrape một pod hoạt động, nhưng bài test không có restart để phát hiện xử lý counter reset sai trong dashboard.
Nhóm thử lỗi database khi một pod đang chạy nhưng không kiểm tra readiness trong lúc toàn cụm mất DB; trên production tất cả pod đồng loạt biến mất khỏi service.
Đội kiểm thử probe chỉ gọi endpoint liveness một lần sau startup, nhưng không mô phỏng deadlock hoặc block thread; khi sự cố thật xảy ra Kubernetes không nhận ra lỗi.
Một kịch bản kiểm thử thay đổi cấu hình port Actuator nhưng không cập nhật Prometheus và Kubernetes manifest; pipeline vẫn báo thành công dù các probe ngoài ứng dụng bị mất.
Ứng dụng có một endpoint quản trị chỉ mở với role vận hành nhưng test security không chạy qua reverse proxy; khi gateway thêm prefix, quy tắc kiểm soát không còn đúng.
Đội QA đo thời gian đáp ứng health endpoint trên laptop, nhưng production có hàng chục custom indicators gọi dịch vụ ngoài; probe vượt ngưỡng dưới tải đồng thời.
Trong lần khôi phục sự cố, nhóm dùng heapdump để tìm nguyên nhân OOM nhưng chưa có quy tắc bảo vệ và xóa file sau điều tra; bản sao dữ liệu nhạy cảm tồn tại lâu hơn chính sách.
Một tổ chức triển khai Prometheus cùng bộ alert cho nhiều microservice nhưng không kiểm tra đơn vị và nhãn của từng meter; một ngưỡng cảnh báo được áp sai cho API quan trọng.
Nhóm thử readiness trên ứng dụng chạy một mình, nhưng production có service mesh chặn traffic khi sidecar chưa sẵn sàng; bộ phận vận hành không biết nguyên nhân traffic vẫn thất bại.
Đội thực hiện disaster recovery sang vùng dự phòng nhưng dashboard chỉ theo dõi endpoint Actuator ở vùng chính; sau failover không có số liệu để đánh giá hệ thống mới.
Một dịch vụ bị chậm do thread pool bão hòa nhưng endpoint health vẫn UP và metrics chưa có tín hiệu hàng đợi; nhà vận hành không thể phân biệt quá tải với lỗi mạng.
Đội kiểm thử xuất bản custom endpoint chứa tên tất cả kết nối database và không rà soát field nhạy cảm; sau deploy người dùng không được ủy quyền vẫn đọc được sơ đồ hạ tầng.
Một dịch vụ bật metrics và tracing đầy đủ trên staging nhưng tắt một phần ở production để tiết kiệm chi phí; khi sự cố xảy ra nhóm không đủ dữ liệu để xác định đoạn xử lý chậm.
Nhóm kiểm toán yêu cầu truy vết người đã thay đổi log level và xem endpoint cấu hình, nhưng hệ thống chỉ ghi access log từ gateway không giữ định danh người quản trị.
Một đội vận hành có nhiều endpoint Actuator tùy biến từ các starter khác nhau nhưng không có danh mục quyền và mục đích truy cập, khiến lần rà soát bảo mật bỏ sót endpoint mới.
Một ứng dụng tự động mở port quản trị ra mạng nội bộ khi chạy local profile; sau khi đóng gói container không đúng profile, endpoint nhạy cảm lộ trên production.
Nhóm chỉ đo availability bằng HTTP 200 từ endpoint health, nhưng các sự kiện giao dịch bị trì hoãn nhiều giờ do broker đầy; cam kết độ trễ end-to-end không được phản ánh.
Một hệ thống dùng Actuator metrics để tính SLA nhưng quá trình autoscale tạo khoảng trống scrape dữ liệu; báo cáo theo tháng ghi nhận ít lỗi hơn thực tế khách hàng gặp.
Đội triển khai thay đổi sampling tracing và histogram metrics cùng lúc để giảm chi phí, khiến khả năng nhìn thấy lỗi hiếm giảm mà không có phép kiểm chứng trước sau.
Một service trả readiness UP nhưng heap gần giới hạn và p99 tăng liên tục; công cụ giám sát chỉ đặt cảnh báo khi pod bị restart nên không phát hiện suy giảm trước sự cố.
Ứng dụng phân quyền truy cập endpoint quản trị theo role từ hệ thống đăng nhập tập trung, nhưng khi dịch vụ xác thực bị ngắt, cả đội trực không thể lấy số liệu cần thiết để xử lý sự cố.
Đội vận hành bật chỉ số tùy biến đo số giao dịch thành công, nhưng cách cập nhật meter diễn ra trước commit database; dashboard báo thành công cho cả các giao dịch đã rollback.
Trong một đợt deploy canary, nhóm muốn đối chiếu error rate và latency giữa hai phiên bản nhưng metrics thiếu tag release phù hợp, khiến việc quyết định mở rộng rollout thiếu căn cứ.
