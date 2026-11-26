Bạn giải thích mục tiêu của OpenTelemetry trong việc quan sát một yêu cầu đi qua nhiều dịch vụ như thế nào?
Bạn phân biệt vai trò của traces, metrics và logs khi chẩn đoán sự cố ứng dụng ra sao?
Bạn lựa chọn điểm instrument ưu tiên trong một luồng nghiệp vụ dựa trên mục tiêu chẩn đoán nào?
Bạn so sánh tự ghi log với triển khai distributed tracing để tìm nguồn gây chậm xuyên dịch vụ ra sao?
Bạn mô tả các thành phần OpenTelemetry API, SDK, instrumentation và Collector liên hệ với nhau như thế nào?
Bạn phân biệt telemetry được tạo trong ứng dụng với telemetry được thu nhận và xử lý bởi Collector ra sao?
Bạn xác định trường hợp nên dùng auto-instrumentation và trường hợp cần bổ sung instrumentation thủ công như thế nào?
Bạn đánh giá chi phí triển khai OpenTelemetry so với giá trị chẩn đoán thu được bằng những tiêu chí nào?
Bạn tổ chức kế hoạch đưa tracing vào hệ thống nhiều dịch vụ mà không yêu cầu thay đổi đồng loạt như thế nào?
Bạn phân biệt tính độc lập với vendor của OpenTelemetry với tính năng riêng của một backend quan sát ra sao?
Bạn xác định những tín hiệu quan sát cần thiết để theo dõi một transaction nghiệp vụ xuyên HTTP, message queue và database như thế nào?
Bạn thiết kế quy ước đặt tên và quản lý cấu hình telemetry để nhiều đội cùng áp dụng ra sao?
Bạn xác định trình tự thử nghiệm instrumentation từ development đến production dựa trên các rủi ro nào?
Bạn giải thích ý nghĩa của trace, span, trace ID và span ID qua một yêu cầu thực tế như thế nào?
Bạn phân biệt root span với child span trong cấu trúc cây của một distributed trace ra sao?
Bạn mô tả quan hệ parent-child giữa các span khi một API gọi lần lượt nhiều dịch vụ như thế nào?
Bạn giải thích sự khác nhau giữa span duration và thời gian xử lý tổng thể của một transaction ra sao?
Bạn xác định điểm bắt đầu và kết thúc span để thời lượng đo phản ánh đúng thao tác như thế nào?
Bạn chọn tên span ổn định và có ý nghĩa để tránh tạo quá nhiều loại span không cần thiết ra sao?
Bạn phân biệt span name với các attribute mô tả thao tác trong quá trình thiết kế instrumentation như thế nào?
Bạn xác định những thao tác nghiệp vụ nào nên tạo span riêng thay vì tận dụng span hiện có ra sao?
Bạn phân biệt span kind CLIENT, SERVER, INTERNAL, PRODUCER và CONSUMER theo quan hệ giao tiếp như thế nào?
Bạn thiết kế các span khi một HTTP request đi qua controller, service, repository và database ra sao?
Bạn giải thích một trace có thể chứa nhiều span chạy song song thay vì chỉ có một chuỗi gọi tuần tự như thế nào?
Bạn xác định nguyên nhân thời lượng tổng các span lớn hơn thời lượng của root span ra sao?
Bạn phân tích khoảng thời gian trống giữa các span để phát hiện một bước chưa được instrument như thế nào?
Bạn xác định thời điểm nên tạo span event thay vì tạo thêm child span như thế nào?
Bạn thiết kế event cho một thao tác retry để giữ đủ bối cảnh mà không tạo tín hiệu nhiễu ra sao?
Bạn phân biệt ghi exception event với đặt span status khi ứng dụng gặp lỗi như thế nào?
Bạn quyết định khi nào đánh dấu span status ERROR dựa trên kết quả và ngữ nghĩa của thao tác ra sao?
Bạn đánh giá vì sao một HTTP 4xx không phải lúc nào cũng đồng nghĩa span lỗi hệ thống ra sao?
Bạn sử dụng attribute để mô tả loại thao tác, kết quả và thành phần đích mà không đưa dữ liệu nhạy cảm vào trace như thế nào?
Bạn xác định các span attribute cần giữ ổn định khi ứng dụng thay đổi phiên bản như thế nào?
Bạn đánh giá tác động của attribute có cardinality cao lên lưu trữ và khả năng tìm kiếm trace ra sao?
Bạn thiết kế span link để liên hệ các thao tác không có quan hệ parent-child trực tiếp như thế nào?
Bạn phân biệt span link với parent-child trong trường hợp một job xử lý nhiều thông điệp đầu vào ra sao?
Bạn tổ chức trace của một batch xử lý nhiều bản ghi để tránh tạo cây span quá lớn như thế nào?
Bạn xác định cách thể hiện fan-out và fan-in khi một request khởi chạy nhiều tác vụ song song như thế nào?
Bạn lựa chọn mức chi tiết của span cho một vòng lặp lớn mà không làm tăng chi phí instrumentation quá mức ra sao?
Bạn kiểm tra một trace có phản ánh đúng quan hệ giữa các dịch vụ bằng những dấu hiệu nào?
Bạn giải thích context propagation khác gì với việc chỉ gắn cùng trace ID trong log như thế nào?
Bạn mô tả trace context được truyền qua HTTP header giữa client và server ra sao?
Bạn giải thích vai trò của traceparent và tracestate trong W3C Trace Context như thế nào?
Bạn xác định những trường nào của traceparent cần kiểm tra khi một trace bị đứt giữa hai dịch vụ ra sao?
Bạn phân biệt trace ID, parent span ID và trace flags khi nhận một context từ upstream như thế nào?
Bạn thiết kế bước inject context ở client và extract context ở server trong chuỗi HTTP như thế nào?
Bạn xác định điều gì xảy ra khi downstream không nhận được header propagation từ upstream ra sao?
Bạn đánh giá rủi ro tạo root span mới cho mỗi dịch vụ dù request thực tế thuộc cùng một transaction như thế nào?
Bạn kiểm tra tương thích khi hệ thống đang dùng nhiều định dạng propagation khác nhau bằng cách nào?
Bạn lựa chọn composite propagator để hỗ trợ các dịch vụ đang chuyển đổi định dạng trace context như thế nào?
Bạn phân biệt trace context và baggage theo mục đích truyền thông tin xuyên dịch vụ ra sao?
Bạn quyết định dữ liệu nghiệp vụ nào có thể đặt trong baggage mà không gây rò rỉ hoặc tăng header size như thế nào?
Bạn kiểm soát baggage đến từ client không đáng tin cậy trước khi dùng trong xử lý ứng dụng ra sao?
Bạn đánh giá ảnh hưởng của header lớn hoặc bị proxy loại bỏ tới propagation như thế nào?
Bạn xác định cách truyền trace context qua Kafka, RabbitMQ hoặc hệ thống nhắn tin có message headers ra sao?
Bạn thiết kế bước extract context khi consumer nhận một message được sản xuất ở dịch vụ khác như thế nào?
Bạn phân biệt propagation của một message đơn với propagation trong một batch chứa nhiều message ra sao?
Bạn sử dụng span links trong tình huống xử lý hàng loạt message có nhiều context cha như thế nào?
Bạn mô tả cách context bị mất khi tác vụ chuyển sang thread mới mà không được truyền tường minh ra sao?
Bạn thiết kế truyền context qua ExecutorService và CompletableFuture trong Java như thế nào?
Bạn kiểm tra ngữ cảnh span hiện hành ở một callback bất đồng bộ bằng cách nào?
Bạn xác định rủi ro kết thúc span trước khi một công việc bất đồng bộ thực sự hoàn tất ra sao?
Bạn thiết kế quản lý scope và vòng đời span trong Java để tránh context bị giữ hoặc giải phóng sai như thế nào?
Bạn phát hiện lỗi context leak giữa các request khi dùng thread pool tái sử dụng như thế nào?
Bạn kiểm tra propagation khi ứng dụng dùng Reactor và thực thi qua nhiều scheduler khác nhau ra sao?
Bạn phân biệt Java ThreadLocal context với Reactor Context khi instrument luồng phản ứng như thế nào?
Bạn tổ chức trace của một chuỗi reactive không đồng bộ để tránh tạo span không đúng thời điểm ra sao?
Bạn đánh giá việc thay đổi thread hoặc dùng virtual threads ảnh hưởng tới cách giữ context như thế nào?
Bạn xác định cách kiểm tra propagation qua gRPC metadata trong một ứng dụng Java ra sao?
Bạn thiết kế truyền context cho scheduled job không có request HTTP khởi đầu như thế nào?
Bạn xác định cách tạo trace mới hoặc liên kết trace cũ khi một job được chạy lại sau thất bại ra sao?
Bạn kiểm tra trace context có còn chính xác sau retry và redelivery của message queue như thế nào?
Bạn thiết kế định danh nghiệp vụ riêng với trace ID để chẩn đoán giao dịch kéo dài qua nhiều giờ như thế nào?
Bạn xác định khi nào không nên cố giữ một trace duy nhất cho một workflow chạy trong nhiều ngày ra sao?
Bạn phân biệt OpenTelemetry Java agent với cấu hình SDK trực tiếp trong mã nguồn như thế nào?
Bạn lựa chọn cách triển khai OpenTelemetry Java agent cho ứng dụng Spring Boot mà giảm thay đổi code ra sao?
Bạn kiểm tra agent có được nạp đúng lúc JVM khởi động và gắn instrumentation vào các thư viện như thế nào?
Bạn xác định những framework hoặc client nào đã được auto-instrument trước khi viết instrumentation thủ công ra sao?
Bạn đánh giá nguy cơ tạo span trùng lặp khi bật đồng thời Java agent và instrumentation do ứng dụng tự thêm như thế nào?
Bạn tổ chức phụ thuộc OpenTelemetry API và SDK trong dự án Maven hoặc Gradle theo hướng tương thích phiên bản ra sao?
Bạn phân biệt sử dụng OpenTelemetry API để tạo span với trách nhiệm cấu hình exporter trong SDK như thế nào?
Bạn quyết định khi nào ứng dụng chỉ phụ thuộc API để tránh gắn chặt vào một SDK cụ thể ra sao?
Bạn lựa chọn cách sử dụng OpenTelemetry Spring Boot starter thay vì Java agent theo điều kiện triển khai nào?
Bạn kiểm tra khả năng kết hợp hoặc xung đột của Spring Boot Actuator, Micrometer và OpenTelemetry như thế nào?
Bạn thiết kế chiến lược instrumentation cho hệ thống Spring Boot đã dùng Micrometer metrics và tracing ra sao?
Bạn xác định quy ước tài nguyên service.name và service.namespace để phân biệt các dịch vụ Spring Boot như thế nào?
Bạn khai báo service.version và deployment.environment.name phù hợp với quy trình release như thế nào?
Bạn kiểm tra các cấu hình resource qua biến môi trường và cấu hình ứng dụng có được áp dụng đúng ra sao?
Bạn đánh giá sự khác nhau giữa cấu hình SDK trong mã nguồn và cấu hình qua biến môi trường ở production như thế nào?
Bạn thiết kế khả năng bật, tắt hoặc đổi endpoint xuất telemetry mà không phải thay đổi logic nghiệp vụ ra sao?
Bạn xác định tác động khi một thư viện ứng dụng tự khởi tạo OpenTelemetry SDK riêng thay vì dùng cấu hình chung như thế nào?
Bạn kiểm tra global OpenTelemetry instance và tracer provider trong một ứng dụng Java để tránh cấu hình trùng lặp ra sao?
Bạn chọn tracer name theo tên thư viện hoặc module để giúp người điều tra hiểu nguồn tạo span như thế nào?
Bạn phân biệt tên instrumentation scope với resource service.name khi đọc dữ liệu trace ra sao?
Bạn lựa chọn mức instrumentation tại controller, service, repository và external client theo tín hiệu cần thu thập như thế nào?
Bạn tạo custom span cho một thao tác nghiệp vụ quan trọng mà không nhân đôi span của HTTP server ra sao?
Bạn xác định cách gắn attribute và event vào current span trong luồng xử lý Spring Boot như thế nào?
Bạn tổ chức instrumentation bằng annotation hoặc interceptor khi nhiều phương thức có cùng quy tắc theo dõi ra sao?
Bạn đánh giá rủi ro instrumentation dựa trên annotation bỏ sót phương thức được gọi nội bộ do cơ chế proxy của Spring như thế nào?
Bạn thiết kế trace cho request đi qua servlet filter, security filter và controller như thế nào?
Bạn phân biệt xử lý servlet truyền thống với Spring WebFlux khi lựa chọn cách instrument như thế nào?
Bạn xác định nơi đo thời gian transaction database và thời gian xử lý nghiệp vụ khi có JDBC span tự động ra sao?
Bạn kiểm tra câu lệnh SQL hoặc tham số nào cần được loại bỏ khỏi telemetry để tránh lộ dữ liệu nhạy cảm như thế nào?
Bạn đánh giá việc instrument HTTP client như RestTemplate, WebClient hoặc client khác cần kiểm tra propagation ra sao?
Bạn thiết kế trace khi ứng dụng gọi một API ngoài có timeout rồi retry nhiều lần như thế nào?
Bạn xác định cách thể hiện cache hit và cache miss trong trace mà tránh tạo quá nhiều span vô ích ra sao?
Bạn tổ chức tracing cho message producer và consumer trong ứng dụng Spring sử dụng Kafka như thế nào?
Bạn phân biệt span của thao tác publish với span xử lý message ở consumer như thế nào?
Bạn xác định cách đánh dấu lỗi trong span khi framework bắt exception rồi trả response hợp lệ ra sao?
Bạn thiết kế instrumentation cho scheduled task có retry mà vẫn phân biệt các lần thực thi ra sao?
Bạn kiểm tra context propagation khi ứng dụng sử dụng @Async hoặc TaskExecutor của Spring như thế nào?
Bạn xử lý trường hợp span vẫn còn active sau khi request đã hoàn tất vì callback chưa đóng scope ra sao?
Bạn thiết kế integration test xác nhận một yêu cầu HTTP tạo đúng server span, client span và quan hệ cha con như thế nào?
Bạn kiểm tra tác động của instrumentation đến thời gian khởi động ứng dụng và khả năng rollback như thế nào?
Bạn giải thích OpenTelemetry Metrics API khác gì với metric được thu thập bằng Prometheus exporter truyền thống ra sao?
Bạn lựa chọn Counter, UpDownCounter, Gauge và Histogram theo ý nghĩa tín hiệu ứng dụng như thế nào?
Bạn thiết kế Counter để đo số thao tác hoàn tất và phân biệt với số thao tác đang xử lý như thế nào?
Bạn phân biệt synchronous và asynchronous instruments khi đo trạng thái thay đổi theo thời gian ra sao?
Bạn xác định loại metric phù hợp để theo dõi số tác vụ trong hàng đợi hoặc lượng bộ nhớ hiện tại như thế nào?
Bạn thiết kế histogram đo duration của một nghiệp vụ và chọn đơn vị đo phù hợp ra sao?
Bạn phân biệt metric attribute với span attribute về khả năng tổng hợp và mức cardinality cho phép như thế nào?
Bạn chọn nhãn endpoint theo route template thay vì đường dẫn chứa ID để tránh cardinality cao như thế nào?
Bạn thiết kế metric đo kết quả xử lý theo trạng thái mà không lưu user ID hoặc order ID vào attribute ra sao?
Bạn phân biệt monotonic counter với up-down counter trong một tình huống thực tế như thế nào?
Bạn đánh giá ảnh hưởng của histogram bucket boundary tới độ chính xác của latency percentile như thế nào?
Bạn xác định cách đo số request và thời lượng để hỗ trợ tính tỷ lệ lỗi và SLO như thế nào?
Bạn phân biệt cumulative temporality và delta temporality khi xuất metrics qua pipeline như thế nào?
Bạn đánh giá hệ quả khi backend nhận temporality khác với cấu hình mà nó mong đợi ra sao?
Bạn kiểm tra metric bị reset khi process khởi động lại và cách hệ thống nhận hiểu reset như thế nào?
Bạn xác định khi nào dữ liệu metric có thể liên kết đến trace bằng exemplar ra sao?
Bạn thiết kế cách giữ liên hệ giữa một điểm dữ liệu có độ trễ bất thường và trace tương ứng như thế nào?
Bạn kiểm tra metric phát sinh trùng lặp khi cùng instrument bằng Micrometer và OpenTelemetry như thế nào?
Bạn so sánh trách nhiệm của metric reader, exporter và meter provider trong Java SDK như thế nào?
Bạn lựa chọn export interval cho metrics theo độ trễ giám sát và mức tiêu thụ tài nguyên ra sao?
Bạn quyết định tổng hợp metric trước khi xuất đến backend khi nào để cân bằng độ chi tiết và chi phí?
Bạn kiểm soát cardinality của metric attributes trước khi tăng số lượng instance và tenant ra sao?
Bạn thiết kế giới hạn chi phí telemetry khi có nhiều histogram và tag biến động mạnh như thế nào?
Bạn đánh giá sự khác nhau giữa log ứng dụng và OpenTelemetry log record về thông tin ngữ cảnh ra sao?
Bạn xác định vai trò của OpenTelemetry Logs API và SDK so với các framework logging Java sẵn có như thế nào?
Bạn tích hợp SLF4J, Logback hoặc Log4j với thông tin trace context mà không phải tự truyền trace ID vào từng lời gọi log ra sao?
Bạn kiểm tra trace ID và span ID được bổ sung vào MDC hoặc log record ở đúng thời điểm như thế nào?
Bạn xác định vì sao log trong CompletableFuture không có trace ID dù log trong controller có như thế nào?
Bạn xử lý nguy cơ MDC còn dữ liệu của request trước khi thread pool tái sử dụng thread ra sao?
Bạn thiết kế định dạng structured logging để liên kết severity, service, trace ID và thông điệp lỗi như thế nào?
Bạn phân biệt các trường severity, body, attributes và resource của một log record như thế nào?
Bạn quyết định thông tin nào nên xuất hiện trong log body và thông tin nào nên đặt ở attribute ra sao?
Bạn xây dựng quy tắc tránh log token, thông tin định danh và dữ liệu nhạy cảm trước khi xuất telemetry như thế nào?
Bạn kiểm tra sự khác biệt giữa thời gian sự kiện trong log và thời gian Collector nhận được log ra sao?
Bạn xác định tình huống log không có active span và cách diễn giải trace correlation như thế nào?
Bạn thiết kế log cho background worker để có đủ ngữ cảnh nghiệp vụ khi không có HTTP request ra sao?
Bạn phân biệt lỗi được ghi nhận bằng log, span event và span status để không đếm trùng sự cố như thế nào?
Bạn tổ chức liên kết giữa log, trace và metric trên dashboard để rút ngắn thời gian tìm nguyên nhân gốc như thế nào?
Bạn xác định giải pháp khi backend log có trace ID nhưng không tìm thấy trace tương ứng do sampling ra sao?
Bạn kiểm tra log được xuất trùng qua cả agent thu thập stdout và OpenTelemetry log exporter như thế nào?
Bạn lựa chọn mức log và chính sách giữ log để kiểm soát chi phí và hạn chế nhiễu ra sao?
Bạn giải thích resource attributes giúp gắn telemetry với dịch vụ và môi trường triển khai như thế nào?
Bạn phân biệt resource attributes, scope attributes và span attributes khi phân tích dữ liệu ra sao?
Bạn thiết kế quy ước service.name, service.namespace và service.instance.id cho hệ thống nhiều dịch vụ như thế nào?
Bạn xác định ngữ nghĩa của deployment.environment.name để phân biệt production và staging như thế nào?
Bạn kiểm tra một dịch vụ bị hiển thị thành unknown service vì thiếu resource attribute bằng cách nào?
Bạn lựa chọn thông tin host, container hoặc Kubernetes làm resource attributes theo ranh giới quyền riêng tư như thế nào?
Bạn giải thích semantic conventions giúp các thành phần có chung tên trường và ý nghĩa đo lường ra sao?
Bạn xác định các HTTP semantic attributes nên dùng mà không ghi toàn bộ URL chứa tham số nhạy cảm như thế nào?
Bạn lựa chọn http.route thay cho đường dẫn thực có ID để đo và nhóm request như thế nào?
Bạn thiết kế attributes cho span database mà bảo đảm tuân theo convention nhưng không lộ nội dung câu SQL nhạy cảm ra sao?
Bạn xác định cách biểu diễn messaging system, destination và operation cho các span Kafka hoặc queue như thế nào?
Bạn kiểm tra khả năng một convention đổi tên giữa các phiên bản làm truy vấn dashboard bị hỏng ra sao?
Bạn lập kế hoạch nâng cấp semantic conventions cho nhiều ứng dụng mà không tạo hai bộ dữ liệu khó so sánh như thế nào?
Bạn phân biệt các convention ổn định và những phần cần bật tùy chọn theo phiên bản instrumentation như thế nào?
Bạn xác định thông tin nào nên là resource attribute chung và thông tin nào phải gắn từng span hoặc metric riêng như thế nào?
Bạn đánh giá tác động của trùng tên attribute nhưng khác kiểu dữ liệu giữa các service lên khả năng truy vấn ra sao?
Bạn thiết kế bước chuẩn hóa attributes tại Collector khi hai đội dùng tên nhãn khác nhau như thế nào?
Bạn giải thích sampling ảnh hưởng tới độ đầy đủ và chi phí của distributed trace như thế nào?
Bạn phân biệt head sampling với tail sampling về thời điểm quyết định giữ trace ra sao?
Bạn thiết kế parent-based sampling để các span trong cùng trace nhất quán với quyết định upstream như thế nào?
Bạn giải thích trace flags phản ánh quyết định sampling trong propagated context như thế nào?
Bạn lựa chọn sampling xác suất cho traffic lớn mà vẫn có đủ dữ liệu phân tích thông thường ra sao?
Bạn xác định tác động của sampling tỷ lệ thấp đến khả năng tái hiện lỗi hiếm nhưng nghiêm trọng như thế nào?
Bạn đánh giá vì sao sampling theo từng span độc lập có thể tạo trace thiếu quan hệ cha con ra sao?
Bạn thiết kế chính sách tail sampling ưu tiên trace lỗi hoặc trace chậm theo yêu cầu nào?
Bạn tính toán thời gian chờ và bộ nhớ cần thiết khi Collector quyết định tail sampling sau khi nhận các span như thế nào?
Bạn giải thích vì sao tail sampling thường cần tập trung các span cùng trace ở cùng điểm xử lý ra sao?
Bạn đánh giá rủi ro dùng nhiều Collector tail-sampling độc lập sau một bộ cân bằng tải thông thường như thế nào?
Bạn thiết kế trace-aware routing hoặc tầng Collector thích hợp để hỗ trợ tail sampling phân tán ra sao?
Bạn kiểm tra một trace bị thiếu span vì Collector quyết định sampling trước khi các span đến đủ như thế nào?
Bạn chọn bộ lọc để giữ trace của endpoint quan trọng mà vẫn kiểm soát tổng lưu lượng xuất ra sao?
Bạn đánh giá ảnh hưởng của sampling đến việc tính error rate nếu lấy trực tiếp từ số trace được lưu như thế nào?
Bạn phân biệt metrics đầy đủ với trace được lấy mẫu khi theo dõi SLO như thế nào?
Bạn xử lý log và trace không tương ứng do áp dụng sampling ở các pipeline khác nhau như thế nào?
Bạn kiểm tra quyết định sampling có bị thay đổi khi request đi qua các service dùng SDK khác nhau ra sao?
Bạn thiết kế sampling policy theo environment để staging dễ chẩn đoán và production kiểm soát chi phí như thế nào?
Bạn xác định khi nào nên giảm volume bằng filtering hoặc aggregation thay vì chỉ tăng sampling ra sao?
Bạn mô tả các vai trò receiver, processor, exporter và connector trong OpenTelemetry Collector như thế nào?
Bạn thiết kế pipeline traces, metrics và logs qua Collector theo đích lưu trữ tương ứng như thế nào?
Bạn lựa chọn mô hình gửi telemetry trực tiếp đến backend hay đi qua Collector theo yêu cầu vận hành ra sao?
Bạn phân biệt triển khai Collector dạng agent sát ứng dụng với dạng gateway tập trung như thế nào?
Bạn thiết kế kiến trúc agent và gateway nhiều tầng để giảm tải ứng dụng và kiểm soát traffic ra sao?
Bạn lựa chọn OTLP/gRPC hay OTLP/HTTP dựa trên yêu cầu mạng, tương thích và vận hành ra sao?
Bạn kiểm tra endpoint, protocol và port OTLP khi SDK báo kết nối exporter thất bại ra sao?
Bạn phân biệt cấu hình OTLP endpoint ở cấp chung với endpoint riêng cho traces, metrics hoặc logs như thế nào?
Bạn xác định sự khác biệt giữa tín hiệu TLS handshake lỗi và lỗi HTTP khi gửi OTLP tới Collector ra sao?
Bạn cấu hình chứng chỉ và xác thực phù hợp giữa ứng dụng, Collector và backend như thế nào?
Bạn kiểm soát việc cấp secret và token cho exporter mà không lưu thẳng trong mã nguồn như thế nào?
Bạn sử dụng batch processor để cân bằng throughput, số lần gửi và độ trễ telemetry ra sao?
Bạn đánh giá ảnh hưởng của batch size và timeout lên bộ nhớ và độ trễ xuất trace như thế nào?
Bạn thiết kế memory limiter để Collector không cạn RAM khi lưu lượng telemetry tăng đột ngột như thế nào?
Bạn kiểm tra tác động của thứ tự processor khi kết hợp memory limiter, filter, transform và batch ra sao?
Bạn sử dụng attributes hoặc resource processor để chuẩn hóa metadata theo chính sách chung như thế nào?
Bạn lựa chọn filter processor để loại bỏ health-check traces mà không vô tình mất dấu vết lỗi quan trọng ra sao?
Bạn xử lý dữ liệu nhạy cảm bằng bước xóa hoặc biến đổi attributes trước khi xuất ra backend như thế nào?
Bạn thiết kế routing dữ liệu theo tenant hoặc môi trường mà tránh gửi nhầm telemetry sang nơi không được phép ra sao?
Bạn kiểm tra một receiver đã nhận tín hiệu nhưng pipeline không có exporter phù hợp bằng cách nào?
Bạn thiết kế nhiều exporter cho cùng một pipeline và đánh giá rủi ro khi một đích bị chậm ra sao?
Bạn phân biệt lỗi SDK không thể gửi telemetry với lỗi Collector không thể đẩy dữ liệu tới backend ra sao?
Bạn đánh giá tác dụng và giới hạn của retry cùng sending queue trong exporter Collector như thế nào?
Bạn sử dụng persistent queue khi cần giảm nguy cơ mất dữ liệu lúc Collector khởi động lại như thế nào?
Bạn thiết kế backpressure cho Collector khi backend tạm thời không nhận telemetry ra sao?
Bạn xác định hành vi hệ thống khi sending queue đầy và cần ưu tiên bảo vệ ứng dụng như thế nào?
Bạn lựa chọn cấu hình giới hạn tài nguyên Collector dựa trên số span, datapoint và log record mỗi giây ra sao?
Bạn kiểm tra vì sao số spans xuất ra ít hơn số spans nhận được theo các processor và sampling policy như thế nào?
Bạn sử dụng self-observability metrics của Collector để phát hiện dropped telemetry và exporter failure ra sao?
Bạn phân biệt mất dữ liệu do sampling chủ đích với mất dữ liệu do queue overflow hoặc lỗi exporter bằng cách nào?
Bạn thiết kế cấu hình Collector trong Kubernetes dưới dạng DaemonSet hoặc Deployment theo phạm vi thu thập như thế nào?
Bạn đánh giá tác động khi một Collector pod bị restart tới dữ liệu telemetry đang nằm trong bộ nhớ như thế nào?
Bạn lựa chọn chính sách scale gateway Collector theo lưu lượng thực và mức tiêu thụ bộ nhớ như thế nào?
Bạn kiểm tra cấu hình Collector hợp lệ và tương thích các component trước khi rollout bằng cách nào?
Bạn thiết kế pipeline Collector có thể rollback khi thay đổi processor làm rơi trace quan trọng như thế nào?
Bạn xác định phiên bản component và sự khác biệt giữa Collector core và contrib khi lựa chọn cấu hình ra sao?
Bạn đánh giá chi phí và tác động của trace volume, metric cardinality và log volume lên hạ tầng quan sát như thế nào?
Bạn lựa chọn các chỉ số để đo overhead của instrumentation lên CPU, bộ nhớ và độ trễ ứng dụng ra sao?
Bạn kiểm thử hiệu năng trước và sau khi bật Java agent trên tải đại diện như thế nào?
Bạn phát hiện instrumentation tự tạo quá nhiều span do lặp gọi hàm nội bộ bằng cách nào?
Bạn xác định các đoạn code nên loại khỏi instrumentation để giảm overhead nhưng vẫn giữ tín hiệu quan trọng ra sao?
Bạn thiết kế chiến lược giảm số attribute và span event khi một service phát telemetry quá nhiều như thế nào?
Bạn kiểm soát kích thước payload và số lượng attributes trên span để tránh chi phí xuất dữ liệu cao như thế nào?
Bạn xử lý độ lệch đồng hồ giữa hai dịch vụ khi timeline của trace cho thấy span con bắt đầu trước span cha ra sao?
Bạn phân biệt lỗi lệch thời gian với lỗi parent-child relationship khi phân tích một trace không hợp lý như thế nào?
Bạn đánh giá tác động của việc Collector hoặc backend bị lỗi tới SLA của ứng dụng theo mô hình fail-open như thế nào?
Bạn quyết định chính sách flush hoặc shutdown telemetry khi ứng dụng nhận tín hiệu dừng như thế nào?
Bạn kiểm tra dữ liệu cuối cùng được xuất trong quá trình graceful shutdown của Spring Boot ra sao?
Bạn quản lý quyền truy cập telemetry vì span và log có thể bộc lộ cấu trúc hệ thống như thế nào?
Bạn thiết kế chính sách bảo vệ trace chứa thông tin định danh, header hoặc payload nhạy cảm ra sao?
Bạn phân định trách nhiệm xóa hoặc biến đổi dữ liệu nhạy cảm giữa ứng dụng và Collector như thế nào?
Bạn kiểm tra việc bật debug exporter hoặc console exporter không làm lộ dữ liệu nhạy cảm trong production ra sao?
Bạn xây dựng quy tắc giữ dữ liệu và phân quyền theo môi trường cho backend quan sát như thế nào?
Bạn giải thích vì sao trace ID không nên được xem là bằng chứng xác thực danh tính hoặc quyền truy cập ra sao?
Bạn thiết kế unit test cho custom span để kiểm tra tên, loại span, attributes và status như thế nào?
Bạn tổ chức integration test với in-memory exporter hoặc Collector thử nghiệm để xác minh dữ liệu xuất ra ra sao?
Bạn kiểm tra propagation qua HTTP giữa hai ứng dụng Spring Boot bằng cách so sánh trace ID và parent-child như thế nào?
Bạn tạo kịch bản kiểm thử context mất qua CompletableFuture hoặc Reactor để xác minh cơ chế truyền context như thế nào?
Bạn kiểm tra trường hợp nhiều request đồng thời không làm lẫn trace context và log MDC như thế nào?
Bạn xây dựng bộ kiểm thử cho message producer và consumer có retry và redelivery như thế nào?
Bạn kiểm chứng metrics instrument xuất đúng loại, đơn vị, attributes và temporality mong đợi ra sao?
Bạn kiểm tra correlation từ trace tới log khi request tạo exception ở một dịch vụ downstream như thế nào?
Bạn thiết kế smoke test để xác nhận một deployment mới có service.name và resource attributes chính xác ra sao?
Bạn tổ chức thử nghiệm tail sampling với trace lỗi, trace chậm và trace hoàn thành trễ như thế nào?
Bạn kiểm thử Collector bị mất kết nối backend để đo drop rate, queue growth và ảnh hưởng đến ứng dụng ra sao?
Bạn điều tra trace chỉ có một span tại gateway dù request đã đi qua nhiều dịch vụ như thế nào?
Bạn điều tra tình huống span của HTTP client có nhưng span HTTP server downstream không xuất hiện như thế nào?
Bạn phân biệt thiếu span do auto-instrumentation chưa hỗ trợ với thiếu span do sampling hoặc lỗi exporter ra sao?
Bạn xác định nguyên nhân log có trace ID nhưng thuộc trace khác do sai scope hoặc propagation như thế nào?
Bạn điều tra metric tăng đột biến cardinality sau khi thêm nhãn endpoint vào ứng dụng như thế nào?
Bạn kiểm tra vì sao trace giữa HTTP và Kafka bị chia thành hai trace không liên hệ bằng cách nào?
Bạn xác định lỗi dữ liệu telemetry bị gửi nhầm môi trường do cấu hình endpoint hoặc resource như thế nào?
Bạn xử lý trường hợp tất cả span hiển thị service.name giống nhau dù đến từ nhiều ứng dụng ra sao?
Bạn phân tích nguyên nhân trace latency bất thường khi đồng hồ máy chủ không đồng bộ bằng cách nào?
Bạn kiểm tra bộ đệm của SDK và Collector khi mất một phần telemetry lúc tắt dịch vụ như thế nào?
Bạn xây dựng runbook điều tra theo chuỗi ứng dụng, SDK, OTLP, Collector và backend khi telemetry biến mất ra sao?
Bạn lựa chọn các tiêu chí nghiệm thu cho việc tích hợp OpenTelemetry dựa trên độ đầy đủ của trace, tương quan log/metric, chi phí và khả năng chẩn đoán như thế nào?
