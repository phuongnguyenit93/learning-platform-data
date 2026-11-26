Trong những tình huống vận hành nào bạn sẽ sử dụng Spring Boot Actuator thay vì tự xây API quản trị?
Bạn giải thích vai trò của Spring Boot Actuator trong một ứng dụng Spring Boot như thế nào?
Bạn phân biệt monitoring, observability và application management khi sử dụng Actuator ra sao?
Bạn lựa chọn những dấu hiệu nào để biết một ứng dụng đang chạy nhưng chưa sẵn sàng phục vụ lưu lượng?
Bạn xác định ranh giới giữa endpoint quản trị và API nghiệp vụ công khai như thế nào?
Bạn phân tích những rủi ro nếu coi phản hồi HTTP 200 từ trang chủ là bằng chứng toàn bộ hệ thống khỏe mạnh ra sao?
Bạn thiết kế mục tiêu giám sát cho dịch vụ có nhiều dependency bên ngoài như thế nào?
Bạn phân biệt một triệu chứng ở tầng ứng dụng với nguyên nhân ở database, network hoặc hạ tầng ra sao?
Bạn chọn chỉ số nào để phản ánh độ tin cậy và trải nghiệm người dùng ngoài trạng thái health?
Bạn đánh giá mức độ phù hợp của Actuator với môi trường local, staging và production như thế nào?
Bạn thiết kế chiến lược cấu hình Actuator thống nhất giữa nhiều microservice mà không lộ thông tin nhạy cảm ra sao?
Bạn xác định những endpoint nào cần cho tự động hóa vận hành và endpoint nào chỉ dành cho điều tra sự cố?
Bạn so sánh Actuator với việc chỉ thu thập log khi chẩn đoán một vấn đề hiệu năng như thế nào?
Bạn giải thích vai trò của Micrometer trong hệ sinh thái quan sát Spring Boot như thế nào?
Bạn phân biệt health check theo trạng thái hiện tại với metric thể hiện xu hướng theo thời gian ra sao?
Bạn xác định cách liên hệ thông tin từ endpoint với dashboard và alerting ngoài ứng dụng như thế nào?
Bạn thiết kế quy ước tên dịch vụ và môi trường để dễ tổng hợp dữ liệu quan sát từ Actuator ra sao?
Bạn đánh giá chi phí CPU, bộ nhớ và I/O do các tính năng quan sát gây ra như thế nào?
Bạn xác định khi nào cần bổ sung health indicator hoặc metric tùy chỉnh cho logic nghiệp vụ?
Bạn thiết kế quy trình đưa Actuator vào một ứng dụng cũ mà không làm thay đổi hành vi API hiện tại ra sao?
Bạn thêm dependency Spring Boot Actuator và xác minh endpoint được tạo trong ứng dụng như thế nào?
Bạn phân biệt endpoint được kích hoạt với endpoint được expose qua HTTP như thế nào?
Bạn cấu hình management.endpoints.web.exposure.include theo nguyên tắc ít quyền nhất ra sao?
Bạn lựa chọn management.endpoints.web.exposure.exclude trong trường hợp nào?
Bạn phân biệt exposure qua web với exposure qua JMX khi cấu hình Actuator như thế nào?
Bạn giải thích ý nghĩa của đường dẫn cơ sở /actuator và cách cấu hình web base path ra sao?
Bạn thay đổi đường dẫn của một endpoint quản trị mà không làm xung đột với route nghiệp vụ như thế nào?
Bạn kiểm tra các liên kết được Actuator discovery page công bố trong môi trường đã cấu hình bằng cách nào?
Bạn chọn cách tắt một endpoint Actuator không sử dụng để giảm bề mặt tấn công ra sao?
Bạn xác định những thuộc tính configuration có thể thay đổi giữa các phiên bản Spring Boot và kiểm chứng chúng như thế nào?
Bạn tổ chức application properties hoặc YAML cho Actuator theo các profile triển khai như thế nào?
Bạn sử dụng environment variables hoặc cấu hình bên ngoài để cấp endpoint settings theo môi trường ra sao?
Bạn cấu hình management.server.port khi muốn tách cổng quản trị khỏi cổng nghiệp vụ như thế nào?
Bạn đánh giá lợi ích và rủi ro của cổng quản trị riêng so với dùng chung cổng HTTP như thế nào?
Bạn lựa chọn management.server.address hoặc các chính sách mạng tương đương để hạn chế phạm vi truy cập ra sao?
Bạn kiểm tra health và metrics có được phục vụ trên đúng management context sau khi đổi cổng như thế nào?
Bạn xử lý các khác biệt cấu hình Actuator khi ứng dụng chạy trong servlet stack và reactive stack ra sao?
Bạn phân biệt cấu hình được nạp thành công với cấu hình endpoint không có tác dụng do property sai tên như thế nào?
Bạn thiết kế smoke test xác nhận chỉ những endpoint được phép mới truy cập được sau khi deploy ra sao?
Bạn đánh giá tác động của việc bật toàn bộ endpoint bằng wildcard trong production như thế nào?
Bạn kiểm tra endpoint nào sẵn có tùy thuộc dependency và điều kiện auto-configuration như thế nào?
Những thành phần nào đóng góp vào trạng thái tổng hợp của /actuator/health?
Bạn phân biệt các trạng thái UP, DOWN, OUT_OF_SERVICE và UNKNOWN khi đánh giá health ra sao?
Bạn lựa chọn tiêu chí nào khiến một dependency không khỏe phải kéo health tổng thể xuống DOWN?
Bạn giải thích cách HealthIndicator đóng góp status và details vào kết quả health như thế nào?
Bạn triển khai HealthIndicator tùy chỉnh kiểm tra một hệ thống phụ thuộc theo yêu cầu nào?
Bạn thiết kế tên và cấu trúc details của custom HealthIndicator để tránh tiết lộ secret ra sao?
Bạn xác định timeout phù hợp cho một health check phụ thuộc API bên ngoài như thế nào?
Bạn xử lý ngoại lệ từ custom HealthIndicator để vẫn trả trạng thái có ý nghĩa ra sao?
Bạn lựa chọn ReactiveHealthIndicator thay cho HealthIndicator khi ứng dụng dùng WebFlux như thế nào?
Bạn ngăn health check thực hiện truy vấn nặng làm tăng tải database trong giờ cao điểm ra sao?
Bạn thiết kế health check cho connection pool khác gì phép thử một truy vấn nghiệp vụ hoàn chỉnh?
Bạn phân biệt health của database với việc toàn bộ nghiệp vụ dùng database đang hoạt động bình thường như thế nào?
Bạn lựa chọn health indicator nào nên kiểm tra cache, message broker hoặc object storage theo vai trò của chúng?
Bạn xác định trường hợp dependency không thiết yếu bị lỗi nhưng ứng dụng vẫn có thể trả lời một phần như thế nào?
Bạn thiết kế degraded-mode health status mà hệ thống giám sát hiểu đúng ra sao?
Bạn tùy chỉnh ánh xạ Status sang HTTP response status code theo chính sách vận hành như thế nào?
Bạn giải thích thứ tự ưu tiên trạng thái của StatusAggregator ảnh hưởng tới kết quả health tổng hợp ra sao?
Bạn cấu hình health group để chỉ đưa các indicator thích hợp vào từng nhóm như thế nào?
Bạn kiểm tra thành phần nào thực sự nằm trong health group khi sửa cấu hình include/exclude ra sao?
Bạn thiết kế health group riêng cho chức năng quan trọng thay vì một health tổng hợp duy nhất như thế nào?
Bạn đánh giá rủi ro hiển thị thông tin cấu trúc hạ tầng qua health details khi chưa xác thực ra sao?
Bạn sử dụng management.endpoint.health.show-details theo mức quyền phù hợp như thế nào?
Bạn phân biệt show-details và show-components khi muốn giới hạn thông tin từ health endpoint ra sao?
Bạn thiết kế phân quyền cho người vận hành xem health details trong khi hệ thống kiểm tra chỉ nhận status như thế nào?
Bạn xác định cách cảnh báo health flapping khi dependency thay đổi trạng thái liên tục ra sao?
Bạn kiểm thử một HealthIndicator tùy chỉnh khi dependency trả timeout, lỗi xác thực và dữ liệu sai ra sao?
Bạn phân biệt trạng thái tiến trình còn sống với mức sẵn sàng nhận request trong Kubernetes như thế nào?
Bạn giải thích liveness probe khác readiness probe về quyết định restart và điều phối traffic ra sao?
Bạn lựa chọn những điều kiện nào phải ảnh hưởng tới readiness nhưng không ảnh hưởng tới liveness?
Vì sao đưa database dùng chung vào liveness có thể khiến nhiều instance restart đồng loạt?
Bạn thiết kế readiness cho dịch vụ cần warm-up cache hoặc tải cấu hình trước khi phục vụ như thế nào?
Bạn xác định lúc nào readiness cần chuyển sang trạng thái từ chối traffic trong quá trình shutdown ra sao?
Bạn bật và kiểm tra các health probe endpoint liveness, readiness theo phiên bản và môi trường Spring Boot như thế nào?
Bạn giải thích vai trò của ApplicationAvailability trong việc biểu diễn LivenessState và ReadinessState như thế nào?
Bạn thiết kế cập nhật trạng thái availability khi một giai đoạn khởi tạo quan trọng chưa hoàn tất ra sao?
Bạn phân biệt readiness của instance với tình trạng khỏe mạnh của toàn cluster như thế nào?
Bạn điều chỉnh initialDelay, period và failureThreshold của Kubernetes probes theo thời gian khởi động thực tế ra sao?
Bạn quyết định sử dụng Kubernetes startup probe cho ứng dụng khởi động chậm dựa trên những điều kiện nào?
Bạn phân tích hệ quả của timeoutSeconds quá ngắn khi CPU bị contention như thế nào?
Bạn tổ chức readiness endpoint để Kubernetes ngừng gửi traffic trước khi ứng dụng đóng kết nối ra sao?
Bạn kiểm thử liveness failure và readiness failure tạo ra hành vi orchestration khác nhau như thế nào?
Bạn đánh giá nguy cơ health probe kết nối qua management port riêng không phản ánh đúng cổng nghiệp vụ như thế nào?
Bạn cấu hình đường dẫn bổ sung cho probe trên cổng ứng dụng khi cần theo đúng khả năng phiên bản như thế nào?
Bạn phân biệt liveness UP nhưng latency API tăng cao với tình trạng ứng dụng thực sự sẵn sàng như thế nào?
Bạn thiết kế cảnh báo khi nhiều pod đồng thời chuyển readiness xuống DOWN như thế nào?
Bạn đo tác động của probe chạy quá thường xuyên lên dịch vụ phụ thuộc như thế nào?
Bạn xây dựng runbook khi pod bị restart lặp do health indicator phụ thuộc hạ tầng ngoài ra sao?
Bạn lựa chọn những thông tin ứng dụng nào nên công bố qua /actuator/info?
Bạn xác định dữ liệu build, version và commit nào hữu ích cho điều tra sự cố nhưng không chứa secret?
Bạn cấu hình build information để đối chiếu phiên bản đang chạy với artifact đã phát hành như thế nào?
Bạn lựa chọn cách đưa thông tin Git vào info endpoint mà không lộ chi tiết nhạy cảm ra sao?
Bạn phân biệt info contributor mặc định với InfoContributor tự viết như thế nào?
Bạn xây dựng custom InfoContributor cho thông tin phiên bản dữ liệu hoặc tính năng theo tiêu chí nào?
Bạn bảo vệ info endpoint khi metadata tiết lộ môi trường nội bộ như thế nào?
Bạn sử dụng /actuator/env để kiểm tra nguồn cấu hình và thứ tự ưu tiên property như thế nào?
Bạn phân biệt /actuator/env và /actuator/configprops trong chẩn đoán cấu hình ra sao?
Bạn xác định thông tin nào cần được che hoặc sanitize trong env và configprops ra sao?
Bạn phân tích nguy cơ lộ password, token hoặc kết nối database khi expose endpoint cấu hình ra sao?
Bạn kiểm tra một giá trị cấu hình lấy từ profile, environment hay command line bằng phương pháp nào?
Bạn xử lý trường hợp thuộc tính xuất hiện ở /env nhưng không bind đúng vào @ConfigurationProperties như thế nào?
Bạn dùng /actuator/conditions để giải thích lý do auto-configuration được kích hoạt hoặc bỏ qua ra sao?
Bạn so sánh conditions report với việc xem log DEBUG khi tìm nguyên nhân thiếu bean như thế nào?
Bạn dùng /actuator/beans để kiểm tra wiring phụ thuộc trong điều kiện nào?
Bạn xác định các thông tin nội bộ có nguy cơ lộ qua danh sách bean và cấu hình bằng cách nào?
Bạn sử dụng /actuator/mappings để xác định route HTTP nào đang thực sự được đăng ký như thế nào?
Bạn phân biệt endpoint Actuator mappings với việc lấy tài liệu OpenAPI của ứng dụng ra sao?
Bạn dùng endpoint scheduledtasks để điều tra một job bị thiếu hoặc chạy khác lịch như thế nào?
Bạn lựa chọn endpoint caches để quan sát thông tin cache và những giới hạn của nó ra sao?
Bạn phân tích rủi ro thao tác xóa cache qua endpoint quản trị trong production như thế nào?
Bạn sử dụng endpoint startup để điều tra thời gian khởi động khi có cơ chế ghi nhận startup phù hợp ra sao?
Bạn xác định phương án thu thập startup steps khi endpoint không có dữ liệu như thế nào?
Bạn đánh giá sự khác nhau giữa cấu hình nhận diện phiên bản và thay đổi cấu hình runtime như thế nào?
Bạn dùng loggers endpoint để quan sát effective logging level của một package ra sao?
Bạn thay đổi log level tạm thời qua Actuator trong tình huống điều tra nào?
Bạn phân biệt configured level với effective level khi xem loggers endpoint như thế nào?
Bạn đánh giá hậu quả của việc bật DEBUG hoặc TRACE trên package có lưu lượng lớn như thế nào?
Bạn thiết kế quy trình hoàn nguyên log level sau khi điều tra xong sự cố ra sao?
Bạn giới hạn quyền ghi loggers endpoint chỉ cho nhóm vận hành có thẩm quyền như thế nào?
Bạn xử lý rủi ro log DEBUG ghi dữ liệu cá nhân hoặc credentials như thế nào?
Bạn phân biệt thay đổi log level runtime với cập nhật cấu hình persistent sau restart như thế nào?
Bạn kiểm tra logs từ nhiều instance khi chỉ một instance được đổi logging level ra sao?
Bạn thiết kế nhật ký kiểm toán khi người vận hành chỉnh log level động như thế nào?
Bạn xác định điều kiện nào cần đáp ứng để endpoint logfile có nội dung phục vụ điều tra sự cố?
Bạn bảo vệ endpoint truy xuất logfile khỏi việc tải xuống dữ liệu nhạy cảm ra sao?
Bạn kết hợp correlation ID với log level để thu thập dấu vết chính xác trong một đợt lỗi ra sao?
Bạn lựa chọn thời gian bật TRACE hợp lý để tránh ảnh hưởng hiệu năng và chi phí lưu trữ như thế nào?
Bạn sử dụng /actuator/threaddump khi nghi ngờ thread bị chặn hoặc deadlock ra sao?
Bạn xác định điểm nào trên thread dump giúp phân biệt blocked, waiting và runnable threads như thế nào?
Bạn phân tích thread dump của ứng dụng WebFlux và ứng dụng servlet với đặc điểm thread model khác nhau ra sao?
Bạn tìm dấu hiệu thread pool cạn hoặc blocking call trên event loop qua thread dump như thế nào?
Bạn xác định thời điểm thu nhiều thread dump liên tiếp để phát hiện tác vụ bị treo như thế nào?
Bạn đánh giá rủi ro của việc expose thread dump cho người dùng ngoài ra sao?
Bạn dùng heapdump khi bộ nhớ tăng liên tục và cần phân tích object retention như thế nào?
Bạn xác định tài nguyên và dung lượng ổ đĩa cần dự trù trước khi thu heap dump như thế nào?
Bạn bảo vệ heap dump chứa dữ liệu nhạy cảm trong quá trình tạo, lưu và chia sẻ như thế nào?
Bạn kết hợp thông tin heap dump với GC metrics để phân biệt leak và áp lực tải bình thường ra sao?
Bạn quyết định sử dụng JFR hoặc profiler ngoài Actuator dựa trên những nhu cầu phân tích hiệu năng nào?
Bạn kiểm tra endpoint shutdown có được bật hay không và kiểm soát quyền gọi như thế nào?
Bạn đánh giá rủi ro của các endpoint quản trị hỗ trợ thao tác thay đổi trạng thái ứng dụng ra sao?
Bạn xây dựng quy trình phê duyệt cho hành động quản trị nguy hiểm trong production như thế nào?
Bạn phân biệt chức năng của /actuator/metrics với hệ thống lưu trữ time-series như Prometheus ra sao?
Bạn giải thích cơ chế auto-configuration của Micrometer trong Spring Boot khi có registry thích hợp như thế nào?
Bạn chọn Counter cho những sự kiện nghiệp vụ hoặc lỗi xảy ra theo số lần như thế nào?
Bạn dùng Timer để đo latency và số lần thực thi của một operation theo thiết kế nào?
Bạn lựa chọn DistributionSummary để quan sát kích thước payload hoặc batch như thế nào?
Bạn giải thích vì sao Gauge phù hợp với trạng thái tức thời hơn sự kiện tăng dần ra sao?
Bạn phân biệt Counter với Gauge khi hiển thị số yêu cầu đang xử lý như thế nào?
Bạn thiết kế tên metric và unit nhất quán giữa các service dựa trên quy ước nào?
Bạn thêm meter qua MeterRegistry trong service Spring Boot mà không tạo meter mới vô hạn như thế nào?
Bạn xác định các tags cần thiết cho một HTTP request metric theo mục tiêu giám sát nào?
Bạn ngăn tag URI chứa user ID hoặc order ID làm bùng nổ số time series như thế nào?
Bạn đánh giá rủi ro dùng exception message động làm tag của metric như thế nào?
Bạn tổ chức CommonTags như application, environment hoặc cluster theo quy tắc nào?
Bạn xác định khi nào cần MeterFilter để chặn meter hoặc giới hạn số tag values?
Bạn giải thích quan hệ giữa meter tên logic của Micrometer và tên metric khi export sang Prometheus như thế nào?
Bạn thiết kế metric có thể so sánh qua nhiều instance mà không gắn instance ID ở application code ra sao?
Bạn phân biệt metric xuất từ JVM với metric tự tạo cho nghiệp vụ như thế nào?
Bạn lựa chọn JVM heap usage, GC pause và CPU usage để điều tra áp lực tài nguyên ra sao?
Bạn theo dõi thread count và executor metrics để phát hiện thiếu worker như thế nào?
Bạn quan sát connection pool database qua metrics và phân biệt active, idle, pending ra sao?
Bạn thiết kế metric backlog của message queue theo khả năng thu thập hiện có như thế nào?
Bạn xác định khi nào kết quả Gauge bằng NaN hoặc biến mất cần được xử lý đặc biệt ra sao?
Bạn kiểm thử MeterRegistry không đăng ký metric trùng tên nhưng khác kiểu hoặc tag schema như thế nào?
Bạn phân biệt tỷ lệ lỗi tính từ Counter với metric trạng thái health tức thời như thế nào?
Bạn thiết kế histogram cho latency để Prometheus có thể tính phân vị trên nhiều instance ra sao?
Bạn phân biệt percentiles tính tại client với histogram buckets có thể tổng hợp phía server ra sao?
Bạn lựa chọn SLO buckets theo ngưỡng latency quan trọng của hệ thống như thế nào?
Bạn xác định chi phí cardinality khi bật histogram cho nhiều endpoint và tag như thế nào?
Bạn thiết kế một Timer đo tác vụ bất đồng bộ để không dừng đồng hồ trước khi Mono hoàn tất ra sao?
Bạn kiểm tra metric có phản ánh lỗi hoặc cancellation của luồng reactive hay không như thế nào?
Bạn tính tỷ lệ HTTP 5xx từ counter của Micrometer và giải thích các bẫy khi dùng rate ra sao?
Bạn xác định những metric nào phù hợp cho alert và những metric nào chỉ để hỗ trợ điều tra?
Bạn thiết kế metric cho một custom HealthIndicator mà không làm trùng lặp ý nghĩa với health status như thế nào?
Bạn xác định cách đối soát metric nghiệp vụ với số lượng bản ghi thực tế trong database ra sao?
Bạn đánh giá tác động của tags mức độ chi tiết cao tới heap của ứng dụng như thế nào?
Bạn thực hiện kiểm thử tải để đo overhead từ metric instrumentation ra sao?
Bạn cấu hình dependency cần thiết để Spring Boot Actuator expose Prometheus scrape endpoint như thế nào?
Vì sao chỉ thêm Actuator dependency chưa bảo đảm endpoint /actuator/prometheus sẵn sàng?
Bạn phân biệt cơ chế Prometheus pull scraping với việc ứng dụng chủ động push số liệu như thế nào?
Bạn xác định điều kiện để Prometheus server scrape thành công /actuator/prometheus như thế nào?
Bạn cấu hình Prometheus scrape interval dựa trên độ phân giải metric và overhead như thế nào?
Bạn đánh giá vì sao scrape interval khác evaluation interval trong hệ thống cảnh báo ra sao?
Bạn sử dụng PromQL rate và increase khi quan sát counter có thể reset sau restart như thế nào?
Bạn phân biệt counter reset với việc metric bị thiếu do pod ngừng hoạt động như thế nào?
Bạn xử lý nhãn instance, job, service và environment để truy vấn nhiều replica dễ dàng như thế nào?
Bạn thiết kế dashboard latency p95 từ histogram thay vì cộng trung bình các p95 độc lập ra sao?
Bạn xây dựng cảnh báo error rate tăng bền vững và tránh báo động từ lượng request quá ít như thế nào?
Bạn định nghĩa burn-rate alert theo SLO cho một API quan trọng như thế nào?
Bạn phân biệt up metric của Prometheus với health status và readiness của Spring Boot như thế nào?
Bạn xử lý trường hợp Prometheus scrape được endpoint nhưng biểu đồ không hiển thị một metric vừa tạo như thế nào?
Bạn kiểm tra metric name hoặc tag translation khi chuyển từ Micrometer sang Prometheus như thế nào?
Bạn giảm chi phí lưu metric dài hạn khi số pod và số tags tăng mạnh như thế nào?
Bạn xác định rủi ro expose Prometheus metrics chứa tenant name hoặc business identifiers ra sao?
Bạn lựa chọn authentication và network policy cho scrape endpoint theo kiến trúc nào?
Bạn phân biệt Prometheus registry với OpenTelemetry metrics exporter khi thiết kế pipeline quan sát ra sao?
Bạn lập kế hoạch đổi backend metric mà không phải viết lại toàn bộ instrumentation như thế nào?
Bạn giải thích cách Micrometer Observation kết nối measurements với tracing trong một request như thế nào?
Bạn lựa chọn điểm bắt đầu và kết thúc observation cho một tác vụ nghiệp vụ như thế nào?
Bạn xác định trường hợp cần custom Observation thay vì chỉ dùng Timer như thế nào?
Bạn phân biệt low-cardinality key-value và high-cardinality key-value trong observation như thế nào?
Bạn thiết kế trace context propagation từ HTTP inbound sang WebClient outbound ra sao?
Bạn xác định các điều kiện để tracing tự động hoạt động khi có dependency tương ứng như thế nào?
Bạn phân biệt trace ID với request ID và correlation ID trong điều tra sự cố như thế nào?
Bạn thiết kế sampling policy để cân bằng độ chi tiết và chi phí traces ra sao?
Bạn nhận diện điểm nào trong trace cho thấy vấn đề ở database, external API hoặc code nội bộ như thế nào?
Bạn liên kết log với trace ID mà không ghi payload nhạy cảm ra sao?
Bạn xác định khi nào observation có metric nhưng chưa có trace do cấu hình exporter hay sampling ra sao?
Bạn kiểm thử context propagation qua async tasks hoặc scheduler trong ứng dụng như thế nào?
Bạn phân tích tác động của việc mất tracing context giữa thread hoặc reactive operators như thế nào?
Bạn tổ chức span và metric để không phát sinh thông tin định danh người dùng trong tags ra sao?
Bạn kiểm tra latency do network khác với latency do application logic bằng traces và metrics ra sao?
Bạn phân biệt dữ liệu từ /actuator/httpexchanges với request log ở proxy khi chẩn đoán HTTP ra sao?
Bạn xác định điều kiện cần có HttpExchangeRepository để lưu thông tin HTTP exchanges theo thiết lập Spring Boot như thế nào?
Bạn đánh giá rủi ro lưu quá nhiều HTTP exchanges trong bộ nhớ khi traffic lớn như thế nào?
Bạn giới hạn dữ liệu nhạy cảm trong thông tin HTTP exchanges và tracing ra sao?
Bạn dùng httpexchanges để nhận diện response status hoặc thời gian bất thường của request như thế nào?
Bạn xác định khi nào cần access log của web server thay vì Actuator HTTP exchanges ra sao?
Bạn lựa chọn custom endpoint thông qua @Endpoint để cung cấp dữ liệu vận hành nào?
Bạn so sánh @Endpoint với @RestController khi xây API quản trị được expose qua nhiều công nghệ như thế nào?
Bạn thiết kế @ReadOperation, @WriteOperation và @DeleteOperation theo mức rủi ro của từng thao tác ra sao?
Bạn lựa chọn @WebEndpoint hoặc extension endpoint cho yêu cầu chỉ hoạt động qua HTTP trong trường hợp nào?
Bạn đánh giá nguy cơ public custom endpoint trả về dữ liệu quá lớn hoặc có secret như thế nào?
Bạn thực hiện validation và phân quyền cho các thao tác write trên custom endpoint như thế nào?
Bạn kiểm soát timeout hoặc tác vụ tốn tài nguyên được gọi từ custom endpoint như thế nào?
Bạn thiết kế kết quả từ endpoint quản trị để dễ dùng bởi automation nhưng không tiết lộ chi tiết nội bộ ra sao?
Bạn dựa trên tiêu chí nào để chọn custom HealthIndicator thay cho custom Actuator endpoint?
Bạn kiểm thử khả năng discovery và exposure của custom endpoint trên các môi trường khác nhau ra sao?
Bạn bảo vệ Actuator endpoints bằng Spring Security và network controls theo lớp như thế nào?
Bạn phân biệt authentication với authorization cho nhóm endpoint read-only và endpoint thay đổi trạng thái ra sao?
Bạn thiết kế SecurityFilterChain cho Actuator khi ứng dụng cũng có các route nghiệp vụ như thế nào?
Bạn kiểm tra matcher dành riêng cho Actuator không vô tình mở quyền của các route khác ra sao?
Bạn xác định hành vi bảo mật mặc định thay đổi như thế nào khi ứng dụng tự cấu hình SecurityFilterChain?
Bạn lựa chọn chỉ công khai health status mà yêu cầu xác thực với metrics, env và loggers như thế nào?
Bạn đánh giá tác động của việc chỉ dùng security by obscurity thông qua đổi đường dẫn /actuator ra sao?
Bạn triển khai phân quyền theo role cho loggers, heapdump và shutdown dựa trên nguyên tắc nào?
Bạn sử dụng mTLS, VPN hoặc private ingress để bảo vệ management port khi cần ra sao?
Bạn cấu hình firewall và Kubernetes NetworkPolicy để chỉ Prometheus truy cập endpoint metrics như thế nào?
Bạn phân biệt bảo vệ endpoint ở ingress với bảo vệ ngay trong Spring application ra sao?
Bạn lựa chọn tắt hẳn endpoint nhạy cảm thay vì chỉ yêu cầu xác thực mạnh dựa trên tiêu chí nào?
Bạn thiết kế bảo vệ chống brute-force, excessive requests hoặc DoS cho endpoint quản trị như thế nào?
Bạn che thông tin cấu hình nhạy cảm trong env, configprops và error responses như thế nào?
Bạn quản lý token hoặc chứng chỉ được Prometheus và hệ thống giám sát dùng để scrape metrics như thế nào?
Bạn phân tích rủi ro nếu bật endpoint management trên 0.0.0.0 mà thiếu kiểm soát mạng ra sao?
Bạn ghi nhận audit event của người dùng truy cập endpoint quản trị nhạy cảm như thế nào?
Bạn xác định cơ chế giới hạn quyền download heapdump và thread dump khi xảy ra sự cố ra sao?
Bạn thiết kế thử nghiệm bảo mật để bảo đảm tài khoản ẩn danh không truy xuất được thông tin cấu hình như thế nào?
Bạn kiểm tra cấu hình security không cản trở Kubernetes liveness/readiness probes như thế nào?
Bạn đánh giá phương án tách management context khi triển khai ingress public và internal ra sao?
Bạn thực hiện review thay đổi cấu hình exposure endpoint trước mỗi bản phát hành như thế nào?
Bạn chọn cách bật các endpoint chẩn đoán tạm thời trong production có phê duyệt và thời hạn như thế nào?
Bạn xây dựng quy trình rollback khi thay đổi security khiến Prometheus không còn scrape được như thế nào?
Bạn thiết kế checklist bảo vệ Actuator cho một dịch vụ kết nối database, Redis và message broker như thế nào?
Bạn sử dụng Testcontainers để kiểm thử custom HealthIndicator trên database thực trong môi trường kiểm thử như thế nào?
Bạn viết unit test HealthIndicator trả về UP, DOWN và chi tiết an toàn khi dependency lỗi ra sao?
Bạn kiểm thử ReactiveHealthIndicator mà không chặn event loop bằng những công cụ nào?
Bạn kiểm tra health group chỉ tổng hợp đúng indicator đã cấu hình bằng bài test như thế nào?
Bạn dùng MockMvc hoặc WebTestClient để kiểm thử endpoint Actuator được expose và security hoạt động đúng ra sao?
Bạn kiểm thử readiness trước, trong và sau giai đoạn khởi động bằng các tình huống nào?
Bạn mô phỏng mất kết nối database để xác minh readiness và liveness phản ứng khác nhau như thế nào?
Bạn kiểm thử custom metric Counter tăng chính xác sau một số lời gọi service ra sao?
Bạn xác minh Timer đo cả request thất bại và request thành công theo yêu cầu nào?
Bạn dùng SimpleMeterRegistry để kiểm thử metric mà không cần chạy Prometheus thực như thế nào?
Bạn xây dựng integration test /actuator/prometheus chỉ khi registry thích hợp được cấu hình như thế nào?
Bạn kiểm thử metric tags không chứa URI động hoặc customer ID qua các request giả lập ra sao?
Bạn thiết kế kiểm thử quyền cho thao tác thay đổi loggers và xác minh người không đủ quyền bị từ chối như thế nào?
Bạn kiểm thử custom @WriteOperation xử lý input lỗi mà không sửa trạng thái ứng dụng ra sao?
Bạn thực hiện load test để kiểm tra overhead khi bật histogram, tracing và logging chi tiết như thế nào?
Bạn đánh giá tác động của scrape interval dày đặc tới CPU và bộ nhớ ứng dụng ra sao?
Bạn xác minh hành vi HTTP khi một Actuator endpoint bị tắt hoặc không được expose như thế nào?
Bạn kiểm tra khả năng thay đổi environment profile ảnh hưởng tới endpoint exposure như thế nào?
Bạn xây dựng smoke test sau deploy xác minh health, readiness, metrics và đường dẫn quản trị ra sao?
Bạn thiết kế kiểm thử sự cố scrape timeout và kết luận khác với application readiness như thế nào?
Bạn xác định tiêu chí pass/fail cho một lần nâng cấp Spring Boot làm thay đổi hành vi Actuator ra sao?
Nếu /actuator/health trả UP nhưng API thường xuyên 500, bạn sẽ đối chiếu health và error metrics như thế nào?
Nếu liveness probe gây restart hàng loạt khi database gián đoạn, bạn sẽ sửa cách tổ chức indicator ra sao?
Nếu pod sẵn sàng quá sớm khi cache chưa warm-up, bạn sẽ thay đổi readiness và thời điểm nhận traffic như thế nào?
Nếu Prometheus scrape báo 404 cho /actuator/prometheus, bạn sẽ kiểm tra dependency, enablement và exposure theo thứ tự nào?
Nếu /actuator/metrics có metric nhưng dashboard Prometheus trống, bạn sẽ truy tìm sự cố registry và scrape như thế nào?
Nếu một custom tag chứa user ID làm Prometheus tăng cardinality đột biến, bạn sẽ khoanh vùng và sửa instrumentation ra sao?
Nếu p95 latency tăng sau khi bật histogram cho nhiều URI, bạn sẽ đánh giá overhead và buckets như thế nào?
Nếu loggers endpoint bị sử dụng để bật DEBUG toàn cục, bạn sẽ giới hạn quyền và khôi phục cấu hình như thế nào?
Nếu env endpoint bị lộ thông tin nội bộ, bạn sẽ thực hiện cô lập, audit và rà soát secret ra sao?
Nếu thread dump cho thấy nhiều thread WAITING nhưng CPU vẫn cao, bạn sẽ thu thêm bằng chứng nào?
Nếu ứng dụng bị OutOfMemoryError và heapdump chưa được bật, bạn sẽ thiết kế phương án điều tra an toàn như thế nào?
Nếu heap dump chứa dữ liệu cá nhân và được tải xuống trái phép, bạn sẽ tổ chức ứng phó sự cố ra sao?
Nếu connection pool cạn nhưng health database vẫn UP, bạn sẽ xây dựng metric và alert bổ sung như thế nào?
Nếu /actuator/mappings không hiển thị endpoint mà nhóm phát triển mong đợi, bạn sẽ kiểm tra routing và context như thế nào?
Nếu một custom HealthIndicator gọi API ngoài bị treo, bạn sẽ thêm timeout và giới hạn tài nguyên ra sao?
Nếu readiness liên tục flapping do dependency phụ không thiết yếu, bạn sẽ điều chỉnh health groups như thế nào?
Nếu management port hoạt động nhưng cổng nghiệp vụ không nhận request, bạn sẽ thay đổi chiến lược probe ra sao?
Nếu build info và version trên dashboard khác artifact vừa deploy, bạn sẽ kiểm tra pipeline và info contributor như thế nào?
Nếu Prometheus báo target DOWN nhưng pod readiness UP, bạn sẽ phân biệt lỗi network scrape với lỗi ứng dụng như thế nào?
Nếu metric counter reset sau khi pod restart khiến biểu đồ lỗi giảm bất thường, bạn sẽ sửa truy vấn PromQL như thế nào?
Nếu một custom metric không hiển thị sau khi deploy, bạn sẽ kiểm tra vòng đời đăng ký meter và dữ liệu sample ra sao?
Nếu tracing không có span của một HTTP client dù metrics có đủ, bạn sẽ kiểm tra propagation và exporter như thế nào?
Nếu Kubernetes probe thường xuyên timeout khi ứng dụng GC pause, bạn sẽ kiểm tra threshold và JVM metrics ra sao?
Nếu CPU tăng do Actuator scrape thường xuyên, bạn sẽ điều chỉnh endpoint, số liệu và scrape interval như thế nào?
Bạn xây dựng runbook phục hồi một dịch vụ Spring Boot khi health DOWN, error rate tăng và metrics scrape bị gián đoạn như thế nào?
