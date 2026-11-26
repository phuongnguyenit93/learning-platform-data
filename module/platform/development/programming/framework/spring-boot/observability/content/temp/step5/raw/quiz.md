Câu 1. Khi điều tra độ trễ tăng trên nhiều request, tín hiệu nào thường phù hợp để thấy xu hướng ban đầu?
A. Logs chứa stack trace cho một request cụ thể
B. Trace mô tả chuỗi span của một request riêng
C. Baggage chứa metadata được truyền qua dịch vụ
D. Metrics về latency và throughput theo thời gian
Đáp án đúng: D

Câu 2. Khi cần biết request đi qua những service nào và chậm ở đâu, nên ưu tiên gì?
A. Counter tổng request của từng service không có nhãn
B. Log startup chứa các thông số cấu hình của JVM
C. Dùng distributed trace nối các span cùng trace ID
D. Gauge số connection hiện tại ở mỗi connection pool
Đáp án đúng: C

Câu 3. Thông tin nào phù hợp nhất để tra chi tiết exception xảy ra tại một thời điểm?
A. Timer tổng hợp thời gian phản hồi của endpoint
B. Histogram độ trễ đã gom theo các bucket
C. Metric gauge đang đo số worker thread hoạt động
D. Xem log có timestamp, ngữ cảnh và stack trace
Đáp án đúng: D

Câu 4. Trong Micrometer, ObservationRegistry chủ yếu giữ vai trò gì?
A. Quản lý observation và thông báo các handler
B. Lưu mọi log message để truy vấn theo trace ID
C. Cung cấp kho lưu bền vững toàn bộ trace span
D. Tự mở HTTP endpoint exporter cho mọi registry
Đáp án đúng: A

Câu 5. Micrometer Observation tích hợp được nhiều tín hiệu bằng cơ chế nào?
A. MeterFilter tự phát hiện mọi child span trong request
B. Slf4jLogger tự tạo histogram cho mỗi dòng log
C. ObservationHandler xử lý sự kiện vòng đời observation
D. HealthIndicator tự xuất cả metric và trace span
Đáp án đúng: C

Câu 6. Vì sao phải stop một Observation đã start khi công việc kết thúc?
A. Hoàn tất lifecycle để handler ghi độ trễ và kết quả
B. Đăng ký lại tên metric trước khi mở observation mới
C. Xóa toàn bộ parent trace để tránh vượt cardinality
D. Buộc exporter đồng bộ trước khi trả HTTP response
Đáp án đúng: A

Câu 7. Khi Observation.openScope() được dùng, điều nào cần chú ý khi thoát scope?
A. Đóng scope để khôi phục observation hiện hành trước đó
B. Stop toàn bộ registry để ngăn tiếp tục ghi metrics
C. Xóa tất cả tags của những observation cùng tên
D. Đổi span hiện tại thành root span của trace mới
Đáp án đúng: A

Câu 8. Trong một Observation, low-cardinality key-value thường phù hợp với dữ liệu nào?
A. Order ID duy nhất được sinh cho mỗi request
B. Email người dùng được gửi trong header xác thực
C. Session token thay đổi giữa các lần đăng nhập
D. Dùng route mẫu và HTTP method có tập giá trị ổn định
Đáp án đúng: D

Câu 9. High-cardinality key-value trong Observation phù hợp với cách dùng nào?
A. Tạo một time series riêng cho từng request ID trong metrics
B. Giữ chi tiết trong trace, hạn chế đưa vào metric label
C. Dùng làm tên metric động khi một request sinh span mới
D. Thay toàn bộ low-cardinality tags để histogram chính xác
Đáp án đúng: B

Câu 10. Một Metric Counter trong Micrometer thích hợp để đo điều gì?
A. Tổng số sự kiện như lỗi xử lý được ghi nhận
B. Thời gian trung bình của từng request ở một route
C. Giá trị hàng đợi hiện tại có thể tăng hoặc giảm
D. Độ dài một transaction theo từng trace ID
Đáp án đúng: A

Câu 11. Khi cần ghi nhận số item đang chờ trong queue tại thời điểm đọc, meter nào phù hợp?
A. Counter cộng thêm mỗi lần hàng đợi tăng một item
B. Timer tổng hợp duration của các item đã xử lý
C. Gauge lấy giá trị hiện tại từ nguồn trạng thái
D. DistributionSummary đo số request mỗi giây
Đáp án đúng: C

Câu 12. Timer của Micrometer chủ yếu đo tập thông tin nào?
A. Số item trong cache tại thời điểm scrape hiện tại
B. Số message chưa được xác nhận trong message broker
C. Số lần gọi và phân bố tổng thời gian thực thi
D. Số thread đã bị tạo trong suốt vòng đời JVM
Đáp án đúng: C

Câu 13. Khi đo kích thước payload tính bằng byte thay vì duration, nên cân nhắc meter nào?
A. Timer vì mọi kích thước đều biểu diễn bằng thời gian
B. Gauge đếm mọi payload đã hoàn tất trong lịch sử
C. LongTaskTimer thay cho tổng dung lượng response
D. DistributionSummary cho phân bố giá trị kích thước
Đáp án đúng: D

Câu 14. Tại sao tag userId trên mỗi metric request là thiết kế rủi ro?
A. Làm trace ID không còn được truyền qua HTTP header
B. Tạo nhiều tổ hợp nhãn và chi phí lưu trữ time series
C. Buộc timer chuyển thành counter do label không ổn định
D. Khiến một observation tự động mất trạng thái parent
Đáp án đúng: B

Câu 15. Cách nào giúp theo dõi độ trễ theo API mà không gây cardinality quá cao?
A. Dùng HTTP route mẫu thay cho URI chứa ID thực
B. Dùng URL đầy đủ gồm ID để giữ từng request riêng
C. Dùng request ID làm tag để lọc mọi mẫu độ trễ
D. Dùng timestamp đến mili giây làm tên metric
Đáp án đúng: A

Câu 16. Nếu cần p95 latency bằng histogram, cần lưu ý cấu hình gì?
A. Chỉ tạo Counter vì percentile lấy từ số lượng request
B. Chỉ bật debug log để collector tự tạo mọi bucket
C. Bật xuất phân bố hoặc histogram phù hợp với backend
D. Dùng Gauge để lưu một duration của request mới nhất
Đáp án đúng: C

Câu 17. Vì sao không nên lấy trung bình các p95 theo từng instance để suy ra p95 toàn hệ thống?
A. Mỗi instance phải có cùng giá trị p95 dù tải khác nhau
B. Histogram chỉ được tạo tại collector không có dữ liệu gốc
C. Percentile không thể gộp bằng trung bình số học đơn giản
D. Timer chỉ ghi số request chứ không ghi duration
Đáp án đúng: C

Câu 18. Khi tạo metric tuỳ chỉnh, tên và unit nên được chọn thế nào?
A. Tên ổn định và unit nhất quán để truy vấn dễ hiểu
B. Tên ghép trace ID để phân biệt từng lần gọi
C. Đổi unit theo từng request để giảm phép chuyển đổi
D. Tên trùng nhau nhưng unit thay đổi theo backend
Đáp án đúng: A

Câu 19. MeterRegistry trong Micrometer thực hiện trách nhiệm nào?
A. Giữ toàn bộ HTTP request body cho mọi observation
B. Quản lý meter để backend lấy hoặc nhận telemetry
C. Sinh parent span mới cho mỗi log record của ứng dụng
D. Xác thực OAuth token của hệ thống nhận telemetry
Đáp án đúng: B

Câu 20. Trong Spring Boot, Actuator endpoint nào dùng để xem danh sách metric đã ghi nhận?
A. /actuator/health khi cần duyệt các timer theo tên
B. /actuator/conditions khi cần xem bucket histogram
C. /actuator/loggers khi cần số lần gọi từng endpoint
D. Dùng /actuator/metrics khi endpoint đã được expose
Đáp án đúng: D

Câu 21. Để Prometheus scrape metrics của Spring Boot qua HTTP, thông thường cần gì?
A. Chỉ thêm Zipkin exporter để nhận counters từ trace
B. Thêm Prometheus registry và expose actuator/prometheus
C. Chỉ bật trace sampling để nhận metric trên endpoint
D. Chỉ dùng logging.file.name để sinh định dạng Prometheus
Đáp án đúng: B

Câu 22. Trong mô hình Prometheus pull, ai chủ động thu thập metric?
A. Prometheus định kỳ scrape endpoint metric ứng dụng
B. Ứng dụng gửi từng request trace tới Prometheus scraper
C. Collector đợi ứng dụng gửi toàn bộ log qua stdin
D. Browser của người dùng gửi kết quả timer tới registry
Đáp án đúng: A

Câu 23. Khi dùng OTLP exporter cho metric, cơ chế phổ biến là gì?
A. Đẩy metric qua giao thức OTLP đến collector/backend
B. Mở endpoint /actuator/prometheus để collector tự scrape
C. Chuyển mọi meter thành câu SQL để database ingest
D. Dùng traceparent HTTP header để đính kèm time series
Đáp án đúng: A

Câu 24. Nếu một backend export tạm thời không truy cập được, ứng dụng nên ưu tiên gì?
A. Chặn mọi request đến khi nhận đủ ACK cho từng metric
B. Tạo thêm một exporter cho mỗi request thất bại
C. Xóa tất cả meter khỏi registry khi mất kết nối
D. Giới hạn retry và buffer để tránh cản request chính
Đáp án đúng: D

Câu 25. Vì sao nên đặt giới hạn số tag-value trong metric production?
A. Tăng độ ngẫu nhiên của trace sampling theo request
B. Bảo đảm mọi log có chính xác một trace ID
C. Giảm số time series và chi phí lưu trữ, truy vấn
D. Làm exporter tự động đổi từ pull sang push
Đáp án đúng: C

Câu 26. Một trace trong distributed tracing thường bao gồm những gì?
A. Một dòng log duy nhất ghi lỗi của toàn bộ service
B. Các span của cùng một yêu cầu liên kết qua trace ID
C. Một metric time series duy nhất cho mỗi HTTP route
D. Một bean ObservationRegistry dùng chung cả application
Đáp án đúng: B

Câu 27. Span parent-child giúp diễn đạt quan hệ nào trong tracing?
A. Công việc con nằm trong ngữ cảnh thao tác cha
B. Một lần scrape metric thuộc về một collector cụ thể
C. Một log event luôn tạo parent request mới
D. Một exception làm thay đổi tên ứng dụng trong trace
Đáp án đúng: A

Câu 28. Khi hai service trao đổi qua HTTP, thành phần nào cần truyền để nối trace?
A. Tên metric timer trong HTTP query parameter
B. Nội dung stack trace ở header Authorization
C. Giá trị p95 được gắn cố định vào mỗi request
D. Gửi trace context qua HTTP headers theo chuẩn
Đáp án đúng: D

Câu 29. Header traceparent của W3C Trace Context thường chứa thông tin gì?
A. Username, session ID và quyền của người dùng HTTP
B. Trace ID, parent span ID và trace flags theo chuẩn
C. Giá trị hiện hành của counter và histogram bucket
D. Địa chỉ collector và API key dùng gửi telemetry
Đáp án đúng: B

Câu 30. Nếu service B không nhận được trace context từ A, hậu quả dễ gặp là gì?
A. B tự suy ra parent span từ response status của HTTP
B. Service B có thể tạo root trace nếu mất context từ A
C. A tự tạo lại toàn bộ span của B trong local process
D. Metric request của B lập tức ngừng thu thập
Đáp án đúng: B

Câu 31. Khi gửi công việc sang thread pool, tại sao có thể mất span hiện hành?
A. Mỗi thread mới đều tự dùng trace ID của thread cha
B. Counter chỉ hoạt động trên thread khởi tạo registry
C. Exporter sẽ gỡ toàn bộ parent span trước khi submit
D. Thread-local context không tự truyền sang executor
Đáp án đúng: D

Câu 32. Trong pipeline Reactor bất đồng bộ, cách nào thích hợp để giữ ngữ cảnh tracing?
A. Giữ trace ID trong biến static cho toàn bộ subscription
B. Tạo một Timer mới cho mỗi lần chuyển Scheduler
C. Bỏ sampling để span được truyền qua ThreadLocal
D. Dùng Reactor Context và context propagation phù hợp
Đáp án đúng: D

Câu 33. Khi đưa baggage chứa tenant ID qua nhiều service, cần xem xét gì?
A. Baggage chỉ được dùng nội bộ, không thể ra khỏi JVM
B. Mọi baggage key đều trở thành metric tag mặc định
C. Giới hạn nội dung nhạy cảm và chi phí truyền metadata
D. Baggage tự cấp quyền truy cập dữ liệu cho tenant
Đáp án đúng: C

Câu 34. Sự khác biệt quan trọng giữa trace ID và span ID là gì?
A. Trace ID nhận diện metric, span ID nhận diện MeterRegistry
B. Trace ID chỉ dùng cho logs, span ID chỉ dùng counters
C. Trace ID nhóm cả trace, span ID nhận diện từng span
D. Trace ID đổi mỗi bước, span ID giữ nguyên toàn request
Đáp án đúng: C

Câu 35. Khi cấu hình tỷ lệ trace sampling 10%, ý nghĩa phổ biến là gì?
A. Chỉ 10% log được phép ghi xuống file của ứng dụng
B. Chọn một phần trace theo chính sách sampling
C. Timer chỉ đo đúng 10% request trước khi export metric
D. Exporter sẽ luôn lấy đúng mỗi request thứ mười
Đáp án đúng: B

Câu 36. Vì sao head-based sampling có thể bỏ lỡ một số trace lỗi hiếm?
A. Sampler sẽ tự thêm lỗi vào các trace đã bị loại
B. Sampling chỉ áp dụng cho spans kết thúc thành công
C. Quyết định chọn trace trước khi biết kết quả cuối
D. Head-based sampling lấy mẫu sau khi backend nhận đủ span
Đáp án đúng: C

Câu 37. Tail-based sampling tại collector thường hỗ trợ việc gì?
A. Chọn giữ trace sau khi thấy kết quả và thuộc tính
B. Giảm số request được ứng dụng gửi đến service đích
C. Thay thế mọi bước propagation qua HTTP headers
D. Gộp tất cả spans khác trace ID thành một trace
Đáp án đúng: A

Câu 38. Khi thay đổi tỷ lệ sampling, tín hiệu nào thường không nên bị ảnh hưởng trực tiếp?
A. Metric vẫn đếm request theo cấu hình meter độc lập
B. Tổng số trace được ghi nhận trong backend tracing
C. Số span có mặt trong một tập trace đã lấy mẫu
D. Lưu lượng span được gửi đến hệ thống tracing
Đáp án đúng: A

Câu 39. Khi điều tra một lần request chậm, kết hợp metric và trace thế nào hữu ích?
A. Chỉ so tần suất log INFO rồi kết luận không có lỗi
B. Dùng p95 tìm route, rồi xem các trace chậm
C. Lấy trung bình các span ID để xác định bước chậm
D. Dùng endpoint health thay cho việc phân tích latency
Đáp án đúng: B

Câu 40. Log có traceId và spanId cung cấp khả năng gì?
A. Tự sinh các timer histogram cho mọi method đã log
B. Thay việc truyền traceparent qua request liên service
C. Nối log với span qua traceId và spanId tương ứng
D. Bảo đảm log không bao giờ chứa dữ liệu nhạy cảm
Đáp án đúng: C

Câu 41. Khi gặp log lỗi nhưng trace tương ứng không có trên backend, cần kiểm tra gì?
A. Chỉ số lượng bean controller do ứng dụng tạo
B. Chỉ thứ tự class được Spring component scan
C. Chỉ kích thước package JAR khi build release
D. Kiểm tra sampling, propagation và pipeline exporter
Đáp án đúng: D

Câu 42. Nếu p99 latency tăng nhưng tỷ lệ lỗi vẫn thấp, hướng khảo sát nào hợp lý?
A. Tắt metric latency vì request đã trả về thành công
B. Chỉ xem HTTP 500 vì p99 không liên quan throughput
C. Đổi toàn bộ tên metric để bắt collector tính lại
D. So trace chậm với pool, queue và downstream latency
Đáp án đúng: D

Câu 43. Một observation có error nên ghi thông tin như thế nào?
A. Gắn toàn bộ exception message làm low-cardinality metric tag
B. Đánh dấu lỗi trong observation/span mà tránh lộ secret
C. Gắn stack trace vào tên meter để phân loại từng exception
D. Thay trace ID bằng nội dung lỗi để dễ truy vấn
Đáp án đúng: B

Câu 44. Khi thiết kế custom metrics cho HTTP endpoint, cách nào giúp tránh lộ PII?
A. Dùng route template và nhãn loại kết quả đã chuẩn hóa
B. Gắn nguyên email của khách hàng vào mọi request tag
C. Đưa access token vào metric label để tái tạo request
D. Ghi payload đầy đủ trong tên timer trước khi publish
Đáp án đúng: A

Câu 45. Để kiểm thử context propagation qua hai service, assertion nào có ý nghĩa?
A. Mỗi service phải tạo trace ID khác để khỏi trùng nhau
B. Mỗi span B phải có cùng span ID với span bên A
C. B chỉ cần trả HTTP 200 mà không xem trace context
D. Trace B dùng cùng trace ID và nối parent đến A
Đáp án đúng: D

Câu 46. Khi kiểm thử export metrics ra Prometheus, nên kiểm tra điều gì?
A. Mỗi request phải tạo thêm một metric name duy nhất
B. Giá trị của gauge phải luôn bằng số lần request
C. Kiểm tra metric và nhãn tại endpoint đã expose
D. Chỉ cần actuator health trả UP là registry đã scrape
Đáp án đúng: C

Câu 47. Trong môi trường production, muốn giảm chi phí lưu trace mà vẫn tìm được sự cố, nên cân nhắc gì?
A. Đổi mọi span thành log INFO để giữ đúng quan hệ cha con
B. Sampling có mục tiêu kết hợp metrics và trace
C. Tăng số high-cardinality tag cho tất cả metric timer
D. Tắt propagation để mỗi service chỉ có trace cục bộ
Đáp án đúng: B

Câu 48. Khi backend hỗ trợ exemplar của histogram, lợi ích quan trọng nào là gì?
A. Dùng exemplar thay mọi tag route trong toàn bộ registry
B. Gắn mẫu đo metric với trace để mở chi tiết request
C. Tự động tăng sampling cho tất cả metric cùng tên
D. Chuyển toàn bộ log của trace thành metric mới
Đáp án đúng: B
