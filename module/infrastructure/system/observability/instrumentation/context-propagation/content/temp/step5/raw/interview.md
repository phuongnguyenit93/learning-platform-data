Context propagation giải quyết vấn đề gì khi một request đi qua nhiều thread, tác vụ bất đồng bộ và dịch vụ?
Bạn sẽ phân biệt trace context, baggage và MDC theo mục đích, phạm vi sử dụng và dữ liệu chứa bên trong như thế nào?
Bạn sẽ mô tả quan hệ giữa trace, span, trace ID và span ID trong một yêu cầu phân tán ra sao?
Bạn sẽ giải thích vì sao các log từ nhiều dịch vụ cần cùng một trace ID nhưng có thể mang span ID khác nhau?
Bạn sẽ mô tả đường đi của context từ HTTP gateway qua hai microservice và một message consumer như thế nào?
Bạn sẽ phân biệt việc ghi nhận một span với việc truyền context đến nơi tiếp tục xử lý ra sao?
Bạn sẽ xác định trường hợp nào cần tạo span con và trường hợp nào nên dùng span link trong hệ thống bất đồng bộ?
Bạn sẽ giải thích vì sao việc dùng cùng trace ID không đồng nghĩa với việc mọi span đều có quan hệ cha con đúng?
Bạn sẽ thiết kế quy tắc đặt tên và gắn thuộc tính span để hỗ trợ điều tra mà không nhầm với thông tin propagation như thế nào?
Bạn sẽ xác định điểm nào của luồng xử lý có thể làm mất context khi request rời khỏi thread ban đầu?
Bạn sẽ phân biệt propagation trong cùng tiến trình với propagation qua ranh giới mạng theo cách truyền dữ liệu ra sao?
Bạn sẽ quyết định lúc nào không nên kế thừa context cũ mà cần bắt đầu trace mới như thế nào?
Bạn sẽ giải thích các thành phần chính của W3C Trace Context và lý do cần chuẩn chung giữa các hệ thống?
Bạn sẽ mô tả cấu trúc cơ bản của HTTP header traceparent và ý nghĩa từng trường ra sao?
Bạn sẽ phân biệt trace-id và parent-id trong header traceparent khi một dịch vụ nhận request như thế nào?
Bạn sẽ giải thích trường trace-flags cho phép downstream biết quyết định sampling đã được truyền đi như thế nào?
Bạn sẽ phân tích vì sao nhận được trace-flags sampled không đồng nghĩa với bảo đảm mọi span đều được xuất ra backend?
Bạn sẽ mô tả vai trò của tracestate khi các hệ thống tracing cần truyền thêm trạng thái theo nhà cung cấp như thế nào?
Bạn sẽ phân biệt tracestate với W3C Baggage về tính chất thông tin và khả năng truyền qua dịch vụ ra sao?
Bạn sẽ kiểm tra tính hợp lệ của traceparent khi nhận phiên bản, độ dài ID hoặc giá trị header sai định dạng như thế nào?
Bạn sẽ xử lý header traceparent vắng mặt khi request đến một service chưa có thông tin tracing ra sao?
Bạn sẽ xác định hành vi an toàn khi client gửi traceparent không hợp lệ hoặc bị chỉnh sửa thủ công như thế nào?
Bạn sẽ mô tả một dịch vụ nhận traceparent rồi tạo span xử lý mới và truyền parent context tiếp theo như thế nào?
Bạn sẽ giải thích vì sao dịch vụ outbound không nên sao chép nguyên parent-id của inbound span nếu đã tạo span client mới?
Bạn sẽ đánh giá cách truyền traceparent qua nhiều proxy để không làm mất thông tin liên kết request ra sao?
Bạn sẽ phân biệt header propagation theo W3C Trace Context với định dạng B3 trong môi trường có nhiều thư viện tracing như thế nào?
Bạn sẽ lập kế hoạch chuyển đổi từ định dạng propagation cũ sang W3C khi nhiều dịch vụ chưa nâng cấp đồng thời ra sao?
Bạn sẽ kiểm tra trường hợp có nhiều bộ propagator cùng đọc hoặc ghi header và tạo kết quả không nhất quán như thế nào?
Bạn sẽ xác định quy tắc xử lý khi một request chứa đồng thời header tracing thuộc nhiều chuẩn mà chúng mâu thuẫn ra sao?
Bạn sẽ giải thích vì sao header HTTP không phải là kho lưu trữ đáng tin cậy cho mọi thuộc tính nội bộ của ứng dụng?
Bạn sẽ mô tả W3C Baggage dùng để mang thông tin nào xuyên ranh giới dịch vụ và thông tin nào không nên đưa vào đó?
Bạn sẽ phân biệt baggage được truyền sang downstream với span attributes chỉ dùng để mô tả một span như thế nào?
Bạn sẽ thiết kế bộ khóa baggage có tên ổn định để tránh xung đột giữa các nhóm phát triển ra sao?
Bạn sẽ đánh giá tác động của baggage có kích thước lớn đến băng thông, latency và giới hạn header như thế nào?
Bạn sẽ xử lý baggage thiếu, không đúng định dạng hoặc có giá trị không mong đợi theo quy tắc nào?
Bạn sẽ xác định ranh giới nào cần lọc hoặc bỏ baggage trước khi gửi request đến đối tác bên ngoài?
Bạn sẽ giải thích vì sao không nên đưa mật khẩu, token, dữ liệu cá nhân hoặc thông tin tenant nhạy cảm vào baggage?
Bạn sẽ phân biệt dùng baggage để phân loại yêu cầu với việc tin vào baggage để cấp quyền truy cập như thế nào?
Bạn sẽ thiết kế việc truyền metadata phục vụ quan sát nhưng không tạo ra phụ thuộc nghiệp vụ vào trace context ra sao?
Bạn sẽ thử nghiệm bằng cách nào để biết một giá trị baggage đã được truyền qua ba service nhưng không bị rò rỉ sang request khác?
Bạn sẽ mô tả vai trò của OpenTelemetry API, SDK và instrumentation trong quá trình tạo và lan truyền context trên Java như thế nào?
Bạn sẽ phân biệt đối tượng Context của OpenTelemetry với đối tượng Span hiện tại trong một luồng thực thi ra sao?
Bạn sẽ giải thích cách xác định current context trong một đoạn xử lý Java mà không giả định nó là biến toàn cục như thế nào?
Bạn sẽ sử dụng phạm vi Scope khi một span cần trở thành span hiện hành để các thao tác bên trong kế thừa context ra sao?
Bạn sẽ thiết kế vòng đời mở và đóng Scope bằng cấu trúc quản lý tài nguyên để tránh sót bước dọn dẹp như thế nào?
Bạn sẽ phân tích hậu quả khi một Scope bị đóng sai thứ tự trong chuỗi xử lý lồng nhau như thế nào?
Bạn sẽ mô tả quan hệ giữa việc kết thúc Span và việc kết thúc Scope, cùng lý do chúng không hoàn toàn thay thế nhau ra sao?
Bạn sẽ phân biệt context được capture tại thời điểm tạo task với current context tại thời điểm task thực thi như thế nào?
Bạn sẽ thiết kế một wrapper cho Runnable hoặc Callable để context được kích hoạt và khôi phục đúng trong lúc chạy như thế nào?
Bạn sẽ xác định điều gì xảy ra với parent-child span nếu một background task được tạo khi context chưa được kích hoạt?
Bạn sẽ phân biệt Context Propagators và Context Storage trong OpenTelemetry Java về trách nhiệm truyền và quản lý context như thế nào?
Bạn sẽ mô tả cách TextMapPropagator trích xuất context từ HTTP headers và inject vào carrier outbound ra sao?
Bạn sẽ thiết kế getter và setter cho carrier tùy chỉnh mà vẫn bảo đảm header được đọc, ghi và chuẩn hóa đúng như thế nào?
Bạn sẽ xác định khi nào nên tận dụng instrumentation tự động thay vì tự tạo span và truyền context bằng tay ra sao?
Bạn sẽ kiểm tra cấu hình propagator của OpenTelemetry Java khi trace bị đứt dù các span nội bộ vẫn được tạo như thế nào?
Bạn sẽ phân tích tình huống ứng dụng có Java agent và instrumentation thủ công khiến span hoặc header bị ghi lặp như thế nào?
Bạn sẽ đánh giá hậu quả của việc dùng đồng thời nhiều phiên bản thư viện hoặc instrumentation tracing trong cùng ứng dụng ra sao?
Bạn sẽ phân biệt tài nguyên Resource của OpenTelemetry với dữ liệu context đi theo từng request như thế nào?
Bạn sẽ đặt những thông tin nào vào resource attributes và những thông tin nào vào span attributes hoặc baggage?
Khi scheduler khởi phát tác vụ không có request cha, bạn sẽ xác định root context và điểm bắt đầu trace ra sao?
Bạn sẽ giải thích MDC hỗ trợ gắn trace ID và span ID vào dòng log Java như thế nào?
Bạn sẽ phân biệt MDC của logging framework với context của OpenTelemetry khi ứng dụng cần liên kết log và trace ra sao?
Bạn sẽ chọn những MDC keys nào để giúp tìm log theo trace mà không làm tăng rủi ro lộ dữ liệu?
Bạn sẽ mô tả cách cập nhật MDC khi current span thay đổi trong cùng một request như thế nào?
Bạn sẽ phân tích vì sao MDC dựa trên thread-local có thể giữ giá trị cũ khi thread được tái sử dụng trong pool?
Bạn sẽ thiết kế cơ chế lưu và khôi phục MDC của thread trước và sau khi xử lý một task như thế nào?
Bạn sẽ xử lý tình huống exception xảy ra giữa lúc thiết lập MDC và lúc cleanup để tránh rò rỉ ngữ cảnh ra sao?
Bạn sẽ phân biệt thao tác xóa toàn bộ MDC với khôi phục tập MDC trước đó khi hai lời gọi được lồng nhau như thế nào?
Bạn sẽ kiểm chứng log của hai request đồng thời không vô tình dùng trace ID hoặc tenant ID của nhau như thế nào?
Bạn sẽ điều tra trường hợp trace backend hiển thị đúng quan hệ span nhưng log của service thiếu trace ID ra sao?
Bạn sẽ xác định giới hạn của việc chỉ truyền MDC mà không truyền OpenTelemetry Context qua thread khác như thế nào?
Bạn sẽ thiết kế định dạng structured logging để liên kết trace ID với log mà không ghi toàn bộ baggage như thế nào?
Vì sao ThreadLocal không tự động chuyển context sang thread trong pool, và bạn sẽ khắc phục hạn chế đó ra sao?
Bạn sẽ chỉ ra bước nào cần capture context khi một request submit Runnable vào ExecutorService ra sao?
Bạn sẽ thiết kế wrapper Executor để bảo đảm mọi task được submit đều mang context của bên gọi như thế nào?
Bạn sẽ xác định rủi ro khi một Executor wrapper capture context tại thời điểm tạo Executor thay vì khi submit task ra sao?
Bạn sẽ khôi phục context của thread trong pool sau task có lỗi hoặc bị hủy bằng cách nào?
Bạn sẽ phân biệt context của task cha với context của task con khi task tạo thêm công việc bất đồng bộ ra sao?
Bạn sẽ kiểm tra việc truyền context qua scheduled task có thời gian chờ dài mà không giữ tham chiếu không cần thiết như thế nào?
Bạn sẽ cân nhắc liệu tác vụ chạy định kỳ nên kế thừa context của request tạo nó hay tạo trace độc lập ra sao?
Bạn sẽ phân tích tại sao CompletableFuture.supplyAsync có thể làm mất context khi dùng executor mặc định như thế nào?
Bạn sẽ bảo toàn context khi chuỗi CompletableFuture sử dụng thenApplyAsync hoặc thenComposeAsync chạy trên thread khác ra sao?
Bạn sẽ phân biệt callback chạy cùng thread với callback thực thi trên executor khác về nguy cơ mất context như thế nào?
Bạn sẽ thiết kế cách capture context phù hợp khi callback được đăng ký ở một thread nhưng hoàn tất ở thread khác như thế nào?
Bạn sẽ xử lý propagation trong nhánh exceptionally, handle hoặc whenComplete của CompletableFuture để log lỗi đúng trace ra sao?
Bạn sẽ xác định context nào cần dùng khi hai CompletableFuture khác nguồn được kết hợp thành một kết quả chung?
Bạn sẽ phân biệt việc chờ CompletableFuture hoàn tất với việc giữ Scope mở xuyên qua khoảng thời gian chờ như thế nào?
Bạn sẽ lựa chọn điểm mở span và thời điểm end span cho một thao tác bất đồng bộ có thể hoàn tất sau khi hàm trả về ra sao?
Bạn sẽ xử lý task timeout hoặc cancellation sao cho span có trạng thái phù hợp và context được dọn dẹp như thế nào?
Bạn sẽ so sánh việc truyền context qua ExecutorService với việc dùng virtual thread trong Java theo những giả định nào?
Bạn sẽ thiết kế test nhiều task chạy xen kẽ trên cùng thread pool để phát hiện trace context leakage như thế nào?
Bạn sẽ giải thích vì sao reactive pipeline có thể chuyển thread giữa các operator và làm ThreadLocal không đủ tin cậy ra sao?
Bạn sẽ phân biệt Reactor Context với ThreadLocal của Java trong việc lưu metadata cho một chuỗi reactive như thế nào?
Bạn sẽ mô tả cách gắn giá trị vào Reactor Context để các operator downstream đọc được theo ngữ cảnh subscriber ra sao?
Bạn sẽ phân biệt thời điểm lắp ráp pipeline với thời điểm subscription khi lựa chọn context cần capture như thế nào?
Bạn sẽ đánh giá điều gì thay đổi về propagation khi pipeline dùng publishOn hoặc subscribeOn với nhiều Scheduler ra sao?
Bạn sẽ mô tả cách OpenTelemetry Context và Reactor Context có thể được kết nối qua cơ chế tích hợp phù hợp như thế nào?
Bạn sẽ kiểm tra cấu hình context propagation trong Reactor khi trace ID chỉ đúng trước một operator bất đồng bộ như thế nào?
Bạn sẽ xử lý propagation khi một Mono phát sinh thêm Flux hoặc gọi service khác trong flatMap như thế nào?
Bạn sẽ phân tích rủi ro của việc thiết lập Scope trong lambda reactive rồi giữ nó mở ngoài phạm vi thực thi đồng bộ ra sao?
Bạn sẽ thiết kế truyền context giữa một endpoint Spring WebFlux và reactive HTTP client như thế nào?
Bạn sẽ xử lý context khi một reactive stream có nhiều subscriber để tránh dùng nhầm thông tin của lần subscribe trước ra sao?
Bạn sẽ phân biệt ngữ cảnh của mỗi nhánh khi dùng merge, zip hoặc parallel trong Reactor như thế nào?
Bạn sẽ xác định span parent hợp lý khi nhiều nhánh reactive đồng thời cùng tạo sự kiện và cùng kết thúc một bước xử lý ra sao?
Bạn sẽ kiểm tra trace và MDC khi reactive pipeline bị retry, timeout hoặc cancellation như thế nào?
Bạn sẽ mô tả các hậu quả khi vừa dùng automatic context propagation vừa bổ sung các hook thủ công không tương thích ra sao?
Bạn sẽ thiết kế kiểm thử với Scheduler khác nhau để xác nhận log correlation không phụ thuộc một thread cụ thể như thế nào?
Bạn sẽ mô tả quá trình extract trace context từ HTTP request đến và tạo server span trong Java ra sao?
Bạn sẽ xác định vị trí inject traceparent, tracestate và baggage khi ứng dụng gửi HTTP request sang downstream như thế nào?
Bạn sẽ phân biệt context cha từ HTTP request đến với span client mới tạo cho một HTTP call ra sao?
Bạn sẽ bảo toàn context khi sử dụng interceptor, filter hoặc middleware cho HTTP client mà không phải sửa mọi service method như thế nào?
Bạn sẽ kiểm tra propagation khi HTTP client sử dụng connection pool và kết nối được tái sử dụng giữa nhiều request ra sao?
Bạn sẽ chẩn đoán trường hợp downstream tạo trace ID mới dù outbound request vẫn mang traceparent như thế nào?
Bạn sẽ phân biệt request không mang trace context với request bị middleware xóa header tại proxy hoặc API gateway ra sao?
Bạn sẽ thiết kế chính sách xử lý trace context từ Internet tại ingress khi client có thể gửi header giả mạo như thế nào?
Bạn sẽ quyết định khi nào tiếp tục trace đến từ đối tác bên ngoài và khi nào tạo trace mới có span link như thế nào?
Bạn sẽ xác định cách truyền context qua gRPC metadata khi giao tiếp giữa các dịch vụ Java như thế nào?
Bạn sẽ kiểm tra việc truyền context cho request fan-out gọi nhiều downstream song song như thế nào?
Bạn sẽ xử lý retry HTTP sao cho các span mô tả đúng từng lần thử và vẫn liên kết với logical operation như thế nào?
Bạn sẽ đánh giá tác động của timeout ở HTTP client đến thời điểm kết thúc span và thông tin lỗi như thế nào?
Bạn sẽ phân biệt trace bị đứt do sampling với trace bị đứt do không inject hoặc extract đúng context như thế nào?
Bạn sẽ bảo đảm trace context được truyền xuyên qua load balancer hoặc service mesh mà không phụ thuộc địa chỉ Pod ra sao?
Bạn sẽ kiểm thử traceparent qua HTTP header có biến đổi chữ hoa chữ thường và proxy có thể chuẩn hóa tên header như thế nào?
Bạn sẽ phân biệt ngữ nghĩa propagation ở HTTP đồng bộ với việc truyền context khi gửi sự kiện vào message broker ra sao?
Bạn sẽ thiết kế cách mang traceparent và baggage trong message headers mà không sửa payload nghiệp vụ như thế nào?
Bạn sẽ xác định điểm inject context khi producer gửi một bản tin từ Java đến Kafka hoặc hệ thống hàng đợi ra sao?
Bạn sẽ trích xuất context từ headers phía consumer trước khi xử lý bản tin và tạo span nhận như thế nào?
Bạn sẽ lựa chọn parent-child relation hay span link khi một message được xử lý trễ hoặc tách khỏi request gốc ra sao?
Bạn sẽ mô tả trace context khi một consumer nhận batch gồm nhiều bản tin có trace ID khác nhau như thế nào?
Bạn sẽ giải thích vì sao một consumer không nên tự chọn ngẫu nhiên một trace ID làm parent cho toàn bộ batch?
Bạn sẽ thiết kế context propagation khi một message bị retry qua hàng đợi khác hoặc chuyển sang dead-letter queue như thế nào?
Bạn sẽ xác định thông tin trace nào cần giữ lại khi message được phát lại sau nhiều ngày để không làm sai ngữ nghĩa quan hệ span?
Bạn sẽ xử lý trường hợp producer cũ không gắn trace headers còn consumer mới đã hỗ trợ OpenTelemetry như thế nào?
Bạn sẽ phân biệt correlation ID nghiệp vụ với trace ID khi một order trải qua nhiều message và nhiều phiên xử lý như thế nào?
Bạn sẽ lựa chọn thuộc tính quan sát nào cho message ID, topic và consumer group mà không tạo cardinality quá lớn ra sao?
Bạn sẽ phân tích hành vi propagation khi broker hoặc middleware không bảo toàn đầy đủ message headers như thế nào?
Bạn sẽ xác định cách tạo các span riêng cho publish, receive và process phù hợp ngữ nghĩa messaging ra sao?
Bạn sẽ thiết kế hành vi khi một event sinh ra nhiều event downstream để giữ được khả năng truy dấu và tránh phụ thuộc vòng như thế nào?
Bạn sẽ kiểm chứng propagation qua producer, broker và consumer bằng bài kiểm thử tích hợp gồm những bước nào?
Bạn sẽ giải thích mối quan hệ giữa parent-based sampling và cờ sampled trong context được truyền xuống các dịch vụ ra sao?
Bạn sẽ lựa chọn điểm quyết định sampling để tránh việc các dịch vụ tùy tiện bỏ qua context của cùng một trace như thế nào?
Bạn sẽ nhận biết trường hợp trace có cùng trace ID nhưng chỉ thấy một phần span do sampling hoặc exporter gặp lỗi ra sao?
Bạn sẽ phân biệt head-based sampling với tail-based sampling trong hệ thống thu thập trace phân tán như thế nào?
Bạn sẽ xác định những thuộc tính span hoặc baggage nào không nên trở thành điều kiện sampling vì độ tin cậy hoặc quyền riêng tư?
Bạn sẽ thiết kế cách ghi nhận trace context trong log khi span không được xuất đi do quyết định sampling như thế nào?
Bạn sẽ phân tích tác động của việc tái sử dụng trace ID từ request cũ đối với tính đúng đắn và khả năng tìm kiếm trace ra sao?
Bạn sẽ lựa chọn cách kiểm tra độ hợp lệ của trace ID và span ID trong log, header và kết quả backend như thế nào?
Bạn sẽ mô tả việc tạo span mới độc lập rồi thêm span link trong một quy trình fan-in có nhiều parent logic ra sao?
Bạn sẽ phân biệt việc truyền context để duy trì định danh với việc truyền thông tin phục vụ định tuyến hoặc xác thực như thế nào?
Bạn sẽ đánh giá rủi ro lộ dữ liệu trong baggage, MDC và span attributes khi log hoặc telemetry được gửi ra hệ thống bên ngoài ra sao?
Bạn sẽ thiết kế allowlist các baggage keys được phép truyền qua ranh giới trust domain như thế nào?
Bạn sẽ xử lý header tracing quá dài hoặc chứa dữ liệu không hợp lệ mà vẫn tránh ảnh hưởng availability của request ra sao?
Việc một client bên ngoài cố tình sử dụng cùng trace ID cho nhiều request có thể tạo ra những rủi ro gì?
Bạn sẽ thiết kế việc giới hạn kích thước, số lượng và độ dài giá trị baggage để tránh lạm dụng tài nguyên ra sao?
Bạn sẽ phân biệt giá trị baggage do bên ngoài cung cấp với thông tin nhận dạng đã được ứng dụng xác thực như thế nào?
Bạn sẽ bảo vệ log khỏi việc chèn ký tự điều khiển hoặc dữ liệu nhạy cảm khi giá trị MDC đến từ nguồn không tin cậy ra sao?
Bạn sẽ đánh giá nguy cơ giữ tham chiếu tới Context quá lâu khiến metadata của request bị giữ trong bộ nhớ như thế nào?
Bạn sẽ phân tích cách một Scope bị quên đóng có thể làm lộ trace hoặc tenant giữa hai request chạy trên cùng thread ra sao?
Bạn sẽ thiết kế cleanup cho context trong các đường xử lý thành công, lỗi, timeout và cancellation như thế nào?
Bạn sẽ dùng những tiêu chí nào để giới hạn propagation qua ranh giới giữa các tenant hoặc hệ thống có chính sách dữ liệu riêng?
Bạn sẽ lập kế hoạch thử nghiệm khi một service chuyển từ xử lý đồng bộ sang CompletableFuture để bảo đảm trace không đứt như thế nào?
Bạn sẽ viết bài kiểm thử xác minh span của callback bất đồng bộ có parent ID đúng dù callback chạy trên thread khác như thế nào?
Bạn sẽ tổ chức kiểm thử đồng thời nhiều request có baggage khác nhau để phát hiện giá trị bị lẫn qua thread pool ra sao?
Bạn sẽ xác minh MDC của thread được trả lại trạng thái ban đầu sau một tác vụ thất bại bằng những kiểm tra nào?
Bạn sẽ thiết kế kiểm thử Reactor với nhiều lần subscription để phát hiện context của subscriber này bị dùng cho subscriber khác như thế nào?
Bạn sẽ kiểm tra việc truyền traceparent qua HTTP client, proxy và HTTP server bằng cách đối chiếu những dữ liệu nào?
Bạn sẽ kiểm thử propagation với message không có headers, headers sai định dạng và message được retry như thế nào?
Bạn sẽ sử dụng kết hợp trace UI, log query và packet capture có kiểm soát để xác định vị trí làm mất context ra sao?
Bạn sẽ điều tra tình huống log có trace ID hợp lệ nhưng tracing backend không tìm thấy trace tương ứng theo những giả thuyết nào?
Bạn sẽ phân biệt lỗi thiếu context tại nguồn phát, lỗi không gắn nó vào task và lỗi không kích hoạt ở thread nhận ra sao?
Bạn sẽ chẩn đoán việc log của một CompletableFuture hiện trace ID của request khác trong điều kiện tải cao như thế nào?
Bạn sẽ xác định nguyên nhân cùng một HTTP request tạo hai server span hoặc hai client span do instrumentation trùng như thế nào?
Bạn sẽ thiết kế metric hoặc log chẩn đoán tỷ lệ request thiếu trace context mà không làm tăng cardinality quá mức ra sao?
Bạn sẽ quan sát sự thay đổi tỷ lệ orphan span sau khi thêm instrumentation cho Executor hoặc Reactor như thế nào?
Bạn sẽ xây dựng quy trình rollout an toàn khi thay đổi cấu hình propagator giữa nhiều dịch vụ không thể nâng cấp đồng thời như thế nào?
Bạn sẽ đánh giá tác động hiệu năng của propagation, tạo span và cập nhật MDC dưới tải cao bằng những phép đo nào?
Bạn sẽ xác định tiêu chí nghiệm thu nào về trace continuity, log correlation, bảo vệ dữ liệu và không rò rỉ context trước khi triển khai production?
