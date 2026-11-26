Bạn giải thích observability khác logging đơn thuần ở mục tiêu và khả năng suy luận trạng thái hệ thống như thế nào?
Bạn phân biệt monitoring và observability khi điều tra một lỗi chỉ xuất hiện trên production ra sao?
Bạn mô tả vai trò riêng của metrics, logs và distributed traces trong một ứng dụng Spring Boot như thế nào?
Bạn sẽ lựa chọn tín hiệu quan sát nào để điều tra một API có tỷ lệ lỗi tăng nhưng CPU vẫn thấp ra sao?
Bạn xác định những câu hỏi vận hành cần được trả lời trước khi thiết kế instrumentation như thế nào?
Bạn phân tích mối liên hệ giữa độ tin cậy của hệ thống và khả năng quan sát hành vi thực tế ra sao?
Bạn phân biệt triệu chứng ở tầng HTTP với nguyên nhân gốc tại database hoặc dịch vụ phụ thuộc như thế nào?
Bạn sẽ xác định ranh giới quan sát giữa controller, service và repository trong ứng dụng Spring Boot ra sao?
Bạn đánh giá chi phí hiệu năng và lưu trữ khi bổ sung thêm tín hiệu observability như thế nào?
Bạn mô tả một yêu cầu HTTP đi qua nhiều dịch vụ và những tín hiệu cần thu thập ở từng chặng ra sao?
Bạn phân biệt telemetry do framework tự sinh và telemetry cần instrument theo nghiệp vụ như thế nào?
Bạn quyết định khi nào nên thêm custom metric thay vì chỉ dựa vào các chỉ số JVM và HTTP có sẵn ra sao?
Bạn xác định cách giữ tên và ý nghĩa của tín hiệu nhất quán giữa các service trong một hệ thống ra sao?
Bạn sẽ ưu tiên các chỉ số nào để quan sát một API mới trước khi có dữ liệu production như thế nào?
Bạn giải thích vì sao log nhiều không đồng nghĩa với khả năng chẩn đoán tốt hơn như thế nào?
Bạn xây dựng quy trình từ một cảnh báo đến phân tích metric, tìm trace và đọc log chi tiết ra sao?
Bạn đánh giá những hạn chế khi chỉ dùng dashboard tổng hợp để phát hiện lỗi ở một nhóm người dùng nhỏ như thế nào?
Bạn mô tả vai trò của Spring Boot Actuator trong việc công bố thông tin vận hành và observability như thế nào?
Bạn phân biệt health, readiness, liveness và metrics endpoints trong quyết định vận hành ra sao?
Bạn sẽ cấu hình quyền truy cập cho actuator endpoints mà vẫn đáp ứng nhu cầu giám sát như thế nào?
Bạn giải thích vai trò của Micrometer trong việc trừu tượng hóa hệ thống đo lường của ứng dụng Java ra sao?
Bạn phân biệt Micrometer Metrics với Micrometer Observation và Micrometer Tracing như thế nào?
Bạn mô tả quan hệ giữa Observation API và các hệ thống backend nhận metrics hoặc traces như thế nào?
Bạn sẽ xác định những dependency và registry cần thiết để xuất metrics từ một ứng dụng Spring Boot ra sao?
Bạn giải thích ObservationRegistry có trách nhiệm gì trong việc quản lý vòng đời các observation như thế nào?
Bạn phân biệt một Observation với một Meter khi muốn đo cả thời gian và bối cảnh của thao tác ra sao?
Bạn mô tả các giai đoạn tạo, start, stop và ghi nhận lỗi của một Observation ra sao?
Bạn sẽ đặt tên một Observation cho thao tác nghiệp vụ sao cho dễ nhóm và theo dõi như thế nào?
Bạn giải thích Observation.Context có thể mang những thông tin nào để ObservationHandler sử dụng ra sao?
Bạn phân biệt ObservationHandler với ObservationConvention trong việc xử lý tín hiệu và đặt tên ra sao?
Bạn sẽ tùy chỉnh ObservationConvention để thống nhất tên và key-value giữa nhiều service như thế nào?
Bạn đánh giá khi nào nên tạo một Observation thủ công thay vì dùng instrumentation có sẵn ra sao?
Bạn mô tả cách một ObservationHandler liên kết hoạt động nghiệp vụ với hệ thống metrics hoặc tracing như thế nào?
Bạn giải thích vì sao cùng một Observation có thể tạo ra nhiều dạng telemetry khác nhau ra sao?
Bạn lựa chọn vị trí mở và đóng Observation để không đo thiếu các công đoạn bất đồng bộ như thế nào?
Bạn sẽ bảo đảm Observation được stop cả khi thao tác thành công, thất bại hoặc bị hủy ra sao?
Bạn phân biệt cách đánh dấu error trên Observation với việc chỉ ghi log exception như thế nào?
Bạn mô tả ảnh hưởng của nested observations tới cấu trúc trace và cách tổng hợp số liệu ra sao?
Bạn xác định khi nào một thao tác quá nhỏ không nên tạo Observation riêng như thế nào?
Bạn sẽ dùng observation scope đúng vòng đời để giữ ngữ cảnh quan sát trong một đoạn mã ra sao?
Bạn đánh giá nguy cơ không đóng observation scope gây sai ngữ cảnh hoặc rò rỉ tài nguyên ra sao?
Bạn phân biệt bộ lọc ObservationFilter và bộ lọc metric MeterFilter theo đối tượng tác động ra sao?
Bạn sẽ thiết kế ObservationPredicate để tránh instrument những thao tác không có giá trị vận hành như thế nào?
Bạn phân tích tác động của việc bật hoặc tắt instrumentation theo môi trường và tính năng ra sao?
Bạn xác định cách cấu hình @Observed khi cần quan sát phương thức nghiệp vụ và kiểm tra điều kiện kích hoạt của nó như thế nào?
Bạn sẽ tránh instrument lặp hai lần cùng một thao tác khi framework đã có observation mặc định ra sao?
Bạn so sánh một observation toàn bộ request với observation chi tiết cho từng bước nghiệp vụ ra sao?
Bạn mô tả cách dùng Micrometer MeterRegistry để đăng ký và thu thập chỉ số như thế nào?
Bạn phân biệt Counter, Timer, Gauge và DistributionSummary theo ngữ nghĩa cần đo ra sao?
Bạn giải thích vì sao Counter phù hợp với số sự kiện cộng dồn nhưng không phải số kết nối đang mở như thế nào?
Bạn xác định khi nào nên sử dụng Gauge để biểu diễn số lượng tác vụ đang chờ xử lý ra sao?
Bạn phân tích hạn chế của Gauge khi giá trị được đo từ một đối tượng có vòng đời không ổn định như thế nào?
Bạn sẽ dùng Timer để ghi nhận số lần gọi và phân bố thời gian thực thi của một thao tác ra sao?
Bạn phân biệt Timer và LongTaskTimer khi theo dõi tác vụ kéo dài qua nhiều lần scrape như thế nào?
Bạn quyết định khi nào dùng DistributionSummary cho kích thước payload hoặc batch như thế nào?
Bạn giải thích cách các meter khác nhau biểu diễn dữ liệu dưới dạng time series ra sao?
Bạn xác định bộ metric tối thiểu cho tỷ lệ request thành công, lỗi và độ trễ của HTTP endpoint như thế nào?
Bạn sẽ dùng phân vị p95 và p99 để phát hiện tail latency mà giá trị trung bình che khuất ra sao?
Bạn phân biệt percentile được tính ở client với histogram phục vụ tổng hợp từ nhiều instance như thế nào?
Bạn thiết kế SLO buckets hoặc histogram boundaries cho API có giới hạn độ trễ như thế nào?
Bạn đánh giá tác động của việc bật histogram cho mọi metric tới bộ nhớ và chi phí lưu trữ ra sao?
Bạn giải thích vì sao không nên lấy trung bình trực tiếp các percentile của nhiều instance như thế nào?
Bạn sẽ xác định tốc độ request theo đơn vị thời gian từ Counter được exporter công bố ra sao?
Bạn phân biệt rate và increase khi phân tích counter tích lũy bị reset sau restart như thế nào?
Bạn sẽ sử dụng metric của thread pool để giải thích hàng đợi tăng và request latency kéo dài ra sao?
Bạn mô tả cách đo số kết nối database đang dùng, còn trống và đang chờ từ connection pool như thế nào?
Bạn sẽ liên hệ metric của HTTP server với metric của HTTP client khi dịch vụ phụ thuộc chậm như thế nào?
Bạn phân biệt throughput nghiệp vụ và throughput HTTP khi một yêu cầu có thể xử lý nhiều bản ghi ra sao?
Bạn thiết kế metric đếm kết quả xử lý thành công và thất bại theo loại nghiệp vụ như thế nào?
Bạn sẽ đo thời gian chờ hàng đợi khác với thời gian thực thi thực tế trong một tác vụ nền ra sao?
Bạn phân tích tác động của GC pause và heap pressure tới p99 latency của ứng dụng như thế nào?
Bạn lựa chọn những metric của JVM, CPU và executor để bổ sung cho metric HTTP như thế nào?
Bạn mô tả ý nghĩa của tag trong một Micrometer meter và cách nó tạo nhiều series ra sao?
Bạn phân biệt low-cardinality và high-cardinality key-value trong thiết kế observation như thế nào?
Bạn giải thích vì sao userId, orderId hoặc requestId thường không phù hợp làm label metric như thế nào?
Bạn sẽ lựa chọn tag theo HTTP method, status và route template thay vì URL chứa định danh như thế nào?
Bạn đánh giá số lượng series sinh ra khi kết hợp nhiều nhãn có số giá trị khác nhau ra sao?
Bạn xây dựng nguyên tắc đặt tên metric và tag để các đội khác nhau có thể tổng hợp dữ liệu như thế nào?
Bạn phân biệt đường dẫn HTTP thực tế với URI template khi nhóm chỉ số request ra sao?
Bạn sẽ xử lý các đường dẫn không khớp route mà không tạo label mới cho mỗi giá trị đầu vào như thế nào?
Bạn thiết kế một metric lỗi theo loại lỗi chuẩn hóa mà không đưa exception message vào tag như thế nào?
Bạn xác định chính sách giới hạn cardinality bằng MeterFilter hoặc quy tắc đặt tag như thế nào?
Bạn đánh giá ảnh hưởng của cardinality bùng nổ lên RAM ứng dụng và chi phí hệ thống metrics như thế nào?
Bạn sẽ kiểm thử không có ID cá nhân hoặc chuỗi dữ liệu tự do bị đưa vào metric labels ra sao?
Bạn phân biệt label phù hợp cho dashboard tổng hợp với thuộc tính chi tiết chỉ nên đặt trong trace như thế nào?
Bạn mô tả cách một exemplar có thể giúp liên kết phép đo với trace cụ thể như thế nào?
Bạn sẽ lựa chọn lượng thông tin theo tenant để vẫn chẩn đoán được sự cố mà không tạo hàng triệu series ra sao?
Bạn phân tích rủi ro sử dụng giá trị exception class chưa chuẩn hóa làm nhãn trong metric như thế nào?
Bạn thiết kế cách so sánh metric qua nhiều phiên bản ứng dụng mà vẫn giữ hợp đồng tên và tag ra sao?
Bạn giải thích logging level ảnh hưởng thế nào đến chi phí và khả năng chẩn đoán trong Spring Boot?
Bạn phân biệt SLF4J API với Logback hoặc logging backend trong ứng dụng Spring Boot như thế nào?
Bạn sẽ thiết kế mẫu log thống nhất cho các service để truy vấn theo timestamp, level và correlation ID ra sao?
Bạn mô tả vai trò của structured logging khi nhiều instance cùng gửi log về hệ thống tập trung như thế nào?
Bạn phân biệt log sự kiện nghiệp vụ với log kỹ thuật khi điều tra một giao dịch thất bại ra sao?
Bạn sẽ ghi log ở ranh giới HTTP và service như thế nào để tránh lặp cùng một exception qua nhiều tầng?
Bạn giải thích MDC hỗ trợ gắn traceId và spanId vào log như thế nào?
Bạn phân tích vì sao MDC dựa trên ThreadLocal có thể mất hoặc sai ngữ cảnh khi code chạy bất đồng bộ như thế nào?
Bạn sẽ xác định trường hợp cần truyền hoặc khôi phục MDC khi một request chuyển thread ra sao?
Bạn lựa chọn trường dữ liệu nào trong log để điều tra mà không làm lộ token hoặc dữ liệu cá nhân như thế nào?
Bạn giải thích vì sao không nên log toàn bộ HTTP body hoặc query string trong những request nhạy cảm như thế nào?
Bạn xây dựng quy tắc mask và redact bí mật trước khi đẩy log vào hệ thống tập trung ra sao?
Bạn phân biệt correlation ID do ứng dụng tạo với trace ID của hệ thống distributed tracing như thế nào?
Bạn sẽ liên kết log và trace trong dashboard mà không cần tìm thủ công theo thời gian như thế nào?
Bạn đánh giá tác động của logging đồng bộ trong request path tới throughput và độ trễ ra sao?
Bạn xác định khi nào log sampling giúp giảm lượng dữ liệu nhưng vẫn giữ được lỗi nghiêm trọng như thế nào?
Bạn thiết kế chính sách retention khác nhau cho log thông thường, log lỗi và audit log ra sao?
Bạn sẽ kiểm tra log của các service có cùng trace ID khi đi qua HTTP client và message broker ra sao?
Bạn phân biệt thiếu log do log level, lỗi exporter và lỗi context propagation khi điều tra như thế nào?
Bạn giải thích vì sao thông tin stack trace hữu ích nhưng không thể thay thế distributed trace của toàn yêu cầu ra sao?
Bạn lựa chọn cách phát hiện một request bị ghi log thiếu spanId trong hệ thống nhiều thread như thế nào?
Bạn thiết kế cơ chế chống log injection khi nội dung người dùng chứa ký tự xuống dòng hoặc chuỗi định dạng đặc biệt ra sao?
Bạn phân biệt thay đổi log format với thay đổi semantic của các trường được hệ thống tìm kiếm sử dụng ra sao?
Bạn sẽ kiểm soát metric và log được công bố từ actuator để không tiết lộ cấu hình nội bộ như thế nào?
Bạn giải thích khái niệm trace, span, parent span và child span trong distributed tracing như thế nào?
Bạn mô tả quan hệ giữa trace ID và span ID khi một request đi qua nhiều service ra sao?
Bạn phân biệt root span và nested span khi phân tích thời gian thực thi của một giao dịch ra sao?
Bạn sẽ xác định vị trí tạo span cho một lời gọi HTTP đi ra và một tác vụ nghiệp vụ bên trong như thế nào?
Bạn giải thích Micrometer Tracing cung cấp lớp trừu tượng nào so với một tracing SDK cụ thể ra sao?
Bạn phân biệt bridge dùng OpenTelemetry với bridge dùng Brave theo cách tích hợp và vận hành như thế nào?
Bạn sẽ chọn một tracing backend để điều tra đường đi yêu cầu dựa trên các tiêu chí nào?
Bạn mô tả cách trace và span được kết nối khi Spring Boot instrument HTTP server và HTTP client như thế nào?
Bạn sẽ thiết kế custom span cho bước gọi database hoặc cache mà không nhân đôi span framework đã tạo ra sao?
Bạn phân biệt span name với span attributes và events khi mô tả một thao tác ra sao?
Bạn lựa chọn thuộc tính span để tìm lỗi theo nghiệp vụ mà không làm lộ dữ liệu nhạy cảm như thế nào?
Bạn sẽ biểu diễn exception và trạng thái lỗi trên span sao cho dễ truy vấn ra sao?
Bạn phân tích lý do một trace có nhiều span ngắn không nhất thiết là tốt hơn một trace với cấu trúc rõ ràng ra sao?
Bạn sẽ dùng trace waterfall để tìm công đoạn làm tăng tổng latency của một yêu cầu như thế nào?
Bạn đánh giá ảnh hưởng của các lời gọi song song lên hình dạng span tree và critical path ra sao?
Bạn phân biệt thời gian tổng trace và tổng duration các span khi span có thể chồng lấn nhau ra sao?
Bạn sẽ phân tích một trace có khoảng trống lớn giữa các span để tìm thời gian chờ không được instrument như thế nào?
Bạn giải thích sự khác nhau giữa span server, client, producer và consumer trong các tương tác phân tán ra sao?
Bạn xác định khi nào một trace mới nên được tạo thay vì tiếp tục trace của request đến ra sao?
Bạn phân tích rủi ro tin tưởng tuyệt đối trace ID do client bên ngoài tự gửi trong header như thế nào?
Bạn sẽ liên hệ một span báo lỗi với log và metric cùng thời điểm để xác nhận nguyên nhân ra sao?
Bạn xác định chiến lược đặt tên span ổn định khi URL có tham số hoặc ID động như thế nào?
Bạn đánh giá tác động của việc ghi nhiều span events lên chi phí thu thập và dung lượng trace ra sao?
Bạn sẽ phân biệt trace context và business correlation ID khi một workflow kéo dài qua nhiều tác vụ ra sao?
Bạn mô tả mục tiêu của context propagation khi request chuyển từ một service sang service khác như thế nào?
Bạn phân biệt W3C traceparent và B3 headers khi truyền trace context qua HTTP ra sao?
Bạn sẽ quyết định sử dụng định dạng propagation nào khi hệ thống có nhiều tracing library khác nhau ra sao?
Bạn mô tả cách Spring Boot truyền ngữ cảnh trace từ HTTP server sang RestClient hoặc WebClient như thế nào?
Bạn đánh giá tác động của việc tạo HTTP client thủ công không đi qua cấu hình instrumentation mặc định ra sao?
Bạn giải thích vì sao chỉ truyền trace ID mà không giữ sampling flags có thể làm sai ý nghĩa context ra sao?
Bạn xác định khi nào cần dùng baggage để mang thông tin qua các span và service như thế nào?
Bạn phân biệt baggage với tag metric và thuộc tính span theo phạm vi và độ nhạy dữ liệu ra sao?
Bạn sẽ hạn chế việc đưa thông tin cá nhân vào baggage có thể đi qua network headers như thế nào?
Bạn giải thích cách Micrometer Context Propagation hỗ trợ bối cảnh qua ThreadLocal và reactive pipeline như thế nào?
Bạn phân tích sự khác nhau giữa ThreadLocal và Reactor Context khi một request dùng WebFlux ra sao?
Bạn sẽ truyền context khi chuyển từ servlet request thread sang Executor hoặc CompletableFuture như thế nào?
Bạn xác định cách giữ trace context khi một Reactor pipeline dùng publishOn hoặc subscribeOn ra sao?
Bạn sẽ kiểm tra và cấu hình context propagation phù hợp khi tích hợp Micrometer với Reactor như thế nào?
Bạn mô tả nguy cơ mất trace khi một callback chạy trên thread pool không được instrument như thế nào?
Bạn sẽ thiết kế cách capture và restore context mà vẫn dọn sạch ThreadLocal sau khi tác vụ kết thúc ra sao?
Bạn phân biệt tự truyền trace headers với để instrumentation tự động xử lý propagation như thế nào?
Bạn xác định cách truyền trace context qua Kafka hoặc message broker dựa trên message headers ra sao?
Bạn sẽ liên kết producer span với consumer span khi xử lý thông điệp bất đồng bộ như thế nào?
Bạn giải thích vì sao một message được retry hoặc xử lý lại có thể tạo nhiều span dù chỉ có một event nghiệp vụ như thế nào?
Bạn thiết kế chiến lược tracing cho scheduled job không có HTTP request cha ra sao?
Bạn phân tích mối quan hệ giữa trace context và trạng thái batch job khi công việc kéo dài nhiều giờ như thế nào?
Bạn xác định khi nào span links phù hợp hơn quan hệ parent-child trong xử lý nhiều thông điệp ra sao?
Bạn sẽ kiểm tra propagation không rò rỉ traceId giữa hai request chạy đồng thời trên cùng thread pool như thế nào?
Bạn mô tả cách lộ trình trace bị đứt ở giữa hai service ảnh hưởng tới quá trình điều tra như thế nào?
Bạn xác định exporter metrics và tracing nào phù hợp với backend quan sát của tổ chức ra sao?
Bạn phân biệt mô hình Prometheus scrape metrics với mô hình đẩy telemetry qua OTLP như thế nào?
Bạn sẽ cấu hình Spring Boot xuất metrics tới Prometheus mà vẫn bảo vệ endpoint scrape ra sao?
Bạn giải thích vai trò của exporter trong việc đưa dữ liệu đo đạc từ ứng dụng tới hệ thống lưu trữ như thế nào?
Bạn phân biệt Micrometer registry nội bộ ứng dụng với collector và backend nhận telemetry như thế nào?
Bạn phân tích lợi ích của OpenTelemetry Collector khi cần xử lý, lọc và định tuyến telemetry tập trung ra sao?
Bạn lựa chọn khi nào gửi trace trực tiếp tới backend và khi nào qua collector trung gian như thế nào?
Bạn mô tả cách sử dụng OTLP endpoint, credentials và TLS để bảo vệ luồng xuất telemetry ra sao?
Bạn sẽ xử lý lỗi exporter hoặc collector mất kết nối mà không làm hỏng request nghiệp vụ ra sao?
Bạn đánh giá tác động của hàng đợi exporter, batch size và thời gian flush tới độ trễ và bộ nhớ như thế nào?
Bạn xác định cách quan sát số telemetry records bị rơi tại exporter hoặc collector ra sao?
Bạn sẽ thiết lập resource attributes như service name, environment và instance ID để phân biệt nguồn telemetry ra sao?
Bạn phân biệt deployment environment với tenant khi gắn resource attributes hoặc metric labels như thế nào?
Bạn đánh giá rủi ro cấu hình exporter gửi dữ liệu production nhầm sang môi trường thử nghiệm ra sao?
Bạn sẽ thiết kế phương án chuyển exporter giữa các backend mà không sửa toàn bộ instrumentation ứng dụng như thế nào?
Bạn phân biệt lỗi collector không nhận dữ liệu với lỗi ứng dụng không tạo observation ra sao?
Bạn mô tả cơ chế sampling ảnh hưởng tới lượng trace được lưu và chi phí vận hành như thế nào?
Bạn phân biệt head-based sampling với tail-based sampling theo thời điểm và thông tin dùng để quyết định ra sao?
Bạn giải thích tradeoff giữa sampling rate thấp và khả năng điều tra sự cố hiếm như thế nào?
Bạn sẽ xác định tỷ lệ sampling hợp lý cho dịch vụ có lưu lượng rất cao và tỷ lệ lỗi thấp ra sao?
Bạn phân tích vì sao chọn lấy mẫu ngẫu nhiên có thể bỏ lỡ một nhóm request lỗi hiếm gặp như thế nào?
Bạn sẽ thiết kế chính sách giữ trace lỗi hoặc trace chậm theo khả năng của hệ thống quan sát ra sao?
Bạn phân biệt quyết định sampling lan truyền từ upstream với quyết định lấy mẫu cục bộ ở từng service như thế nào?
Bạn xác định khi nào cần giữ nhất quán sampling decision giữa nhiều service trong cùng một trace ra sao?
Bạn sẽ đánh giá tác động của tail sampling tới bộ nhớ và độ trễ tại collector như thế nào?
Bạn mô tả sự khác nhau giữa giảm số trace và giảm cardinality của metrics về hệ quả chẩn đoán ra sao?
Bạn sẽ thiết kế phép thử để xác nhận sampling không làm sai lệch cách diễn giải tỷ lệ lỗi từ metrics ra sao?
Bạn phân biệt telemetry mất vì sampling với telemetry mất vì quá tải pipeline export như thế nào?
Bạn xác định những dữ liệu nào cần được thu thập không lấy mẫu để phục vụ đối soát hoặc audit như thế nào?
Bạn đánh giá khi nào nên đặt sampling policy theo endpoint, lỗi hoặc độ trễ thay vì một tỷ lệ chung ra sao?
Bạn sẽ thiết kế cảnh báo khi lượng trace nhận được giảm bất thường do lỗi cấu hình sampling như thế nào?
Bạn mô tả cách xác định Service Level Indicator cho tính sẵn sàng và độ trễ của API ra sao?
Bạn phân biệt SLI, SLO và SLA khi đặt mục tiêu cho dịch vụ Spring Boot như thế nào?
Bạn sẽ lựa chọn cửa sổ thời gian và ngưỡng cảnh báo phù hợp để tránh cảnh báo nhiễu ra sao?
Bạn giải thích vì sao alert theo error budget burn rate có thể hữu ích hơn một ngưỡng lỗi cố định như thế nào?
Bạn xây dựng dashboard theo RED metrics gồm rate, errors và duration cho HTTP endpoint như thế nào?
Bạn sẽ áp dụng mô hình USE metrics để điều tra nghẽn CPU, thread pool hoặc connection pool ra sao?
Bạn phân biệt lỗi 4xx do người dùng với lỗi 5xx do hệ thống khi thiết kế SLI như thế nào?
Bạn xác định cách quan sát một luồng async khi HTTP request trả thành công nhưng xử lý nền thất bại ra sao?
Bạn sẽ điều tra p99 latency tăng cùng lúc với garbage collection và pool saturation như thế nào?
Bạn mô tả quy trình bắt đầu từ alert, khoanh vùng service rồi lần theo trace tới dependency chậm ra sao?
Bạn sẽ tìm nguyên nhân một request timeout nhưng không có span con nào báo lỗi như thế nào?
Bạn phân tích cách các retry tự động có thể che lỗi backend trong metric HTTP thành công như thế nào?
Bạn sẽ nhận diện retry storm bằng cách đối chiếu request rate, dependency errors và latency ra sao?
Bạn xác định nguyên nhân dashboard cho thấy metric ổn định nhưng người dùng một vùng địa lý vẫn bị lỗi như thế nào?
Bạn thiết kế cách so sánh telemetry trước và sau deploy để xác định regression ra sao?
Bạn sẽ đánh giá một alert false positive do thay đổi nhãn hoặc instrumentation như thế nào?
Bạn phân biệt traffic thấp với exporter bị gián đoạn khi series biến mất khỏi dashboard ra sao?
Bạn sẽ thiết kế runbook điều tra sự cố dựa trên log query, metric dashboard và trace link như thế nào?
Bạn xác định những thông tin nào cần đính kèm vào báo cáo sự cố mà không tiết lộ dữ liệu nhạy cảm như thế nào?
Bạn mô tả cách dùng TestObservationRegistry để kiểm chứng observation và key-value trong unit test như thế nào?
Bạn sẽ viết test xác nhận một thao tác thành công tạo Observation đúng vòng đời như thế nào?
Bạn kiểm thử trường hợp exception làm Observation được ghi nhận lỗi và đóng đúng cách ra sao?
Bạn xác định cách kiểm tra không phát sinh metric tag có cardinality cao trong các request thử nghiệm như thế nào?
Bạn phân biệt unit test cho custom ObservationConvention với integration test cho instrumentation tự động như thế nào?
Bạn sẽ kiểm thử cấu hình MeterRegistry khi ứng dụng có nhiều exporter khác nhau ra sao?
Bạn mô tả cách viết test xác nhận metric Counter hoặc Timer thay đổi sau khi gọi service ra sao?
Bạn kiểm thử custom ObservationHandler hoạt động với cả success và failure như thế nào?
Bạn sẽ tạo test cho việc propagation trace context qua HTTP client giả lập ra sao?
Bạn kiểm tra traceId được giữ qua CompletableFuture hoặc Reactor pipeline trong các tình huống nào?
Bạn thiết kế kiểm thử chống rò rỉ MDC hoặc baggage giữa hai request chạy song song như thế nào?
Bạn kiểm thử tracing khi một scheduled task tạo root span mới mà không có incoming HTTP request ra sao?
Bạn sẽ mô phỏng exporter timeout để bảo đảm API nghiệp vụ vẫn phản hồi theo SLA như thế nào?
Bạn xây dựng bài kiểm thử sampling để xác nhận các trace bị bỏ qua theo chính sách dự kiến như thế nào?
Bạn đánh giá sự khác nhau giữa kiểm thử local registry và tích hợp với collector thật như thế nào?
Bạn kiểm tra endpoint actuator metrics không lộ thông tin bí mật hoặc vượt quyền truy cập ra sao?
Bạn sẽ kiểm thử log masking khi một exception chứa access token hoặc dữ liệu cá nhân như thế nào?
Bạn xây dựng kiểm thử tải để đo overhead instrumentation trên CPU, RAM và latency ra sao?
Bạn đánh giá tiêu chí nghiệm thu observability trước khi rollout một Spring Boot service lên production như thế nào?
Nếu một API có p95 ổn định nhưng p99 tăng mạnh sau deploy, bạn sẽ dùng metrics và trace như thế nào để xác định nguyên nhân?
Nếu trace chỉ xuất hiện ở service đầu nhưng mất ở service sau, bạn sẽ kiểm tra propagation headers và HTTP client ra sao?
Nếu một WebFlux pipeline đổi scheduler làm traceId trong log biến mất, bạn sẽ kiểm tra Reactor Context và MDC như thế nào?
Nếu Prometheus đột ngột có hàng triệu series sau khi thêm tag requestId, bạn sẽ khắc phục và phòng ngừa như thế nào?
Nếu exporter tracing bị lỗi kết nối nhưng business API vẫn khỏe, bạn sẽ phân biệt tác động và cảnh báo ra sao?
Nếu một request 200 OK nhưng công việc async sau đó thất bại, bạn sẽ thiết kế metric, log và trace để thấy lỗi như thế nào?
Nếu người dùng báo chậm nhưng dashboard chỉ có latency trung bình, bạn sẽ bổ sung histogram và SLO như thế nào?
Nếu hệ thống có lượng request lớn và chỉ giữ một phần trace, bạn sẽ chọn sampling policy để vẫn điều tra lỗi hiếm ra sao?
Nếu một log ở worker thread mang traceId của request trước, bạn sẽ xác định và sửa lỗi context propagation như thế nào?
Nếu cần chuyển từ Zipkin sang backend OpenTelemetry, bạn sẽ phân tách instrumentation, exporter và collector như thế nào?
Nếu một health check bị trace và log quá nhiều, bạn sẽ điều chỉnh instrumentation mà vẫn giữ khả năng phát hiện lỗi như thế nào?
Nếu hai instance cùng xuất metrics nhưng tag deployment khác nhau, bạn sẽ chuẩn hóa dimensions và dashboard ra sao?
Nếu cần giám sát batch job kéo dài hàng giờ, bạn sẽ kết hợp LongTaskTimer, logs và traces như thế nào?
Nếu một nhóm endpoint có lỗi cao nhưng alert tổng thể không kích hoạt, bạn sẽ điều chỉnh SLI và chiều phân tách metric ra sao?
Nếu phải xây dựng observability cho một Spring Boot service từ đầu, bạn sẽ triển khai instrumentation, exporter, bảo mật, sampling, kiểm thử và runbook theo các bước nào?
