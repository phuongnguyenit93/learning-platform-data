Bạn giải thích circuit breaker giải quyết vấn đề gì khi một dịch vụ phụ thuộc chậm hoặc không khả dụng như thế nào?
Bạn phân biệt circuit breaker với cơ chế xử lý exception thông thường trong một ứng dụng Spring Cloud ra sao?
Bạn mô tả một sự cố dây chuyền giữa các microservice có thể xảy ra khi thiếu circuit breaker như thế nào?
Bạn sẽ xác định khi nào một lời gọi phụ thuộc cần circuit breaker thay vì chỉ tăng timeout như thế nào?
Bạn phân biệt việc fail-fast với việc chờ dependency trả lời tới khi hết thời gian như thế nào?
Bạn giải thích mục tiêu bảo vệ tài nguyên của circuit breaker so với mục tiêu đảm bảo thành công của từng request ra sao?
Bạn đánh giá những đánh đổi khi từ chối lời gọi sớm dù dependency có thể đã phục hồi như thế nào?
Bạn sẽ xác định ranh giới circuit breaker cho từng API, từng service hay từng nhóm dependency ra sao?
Bạn phân biệt circuit breaker phía client với cơ chế health check của server như thế nào?
Bạn giải thích vì sao circuit breaker không thay thế việc sửa lỗi trong dịch vụ phụ thuộc ra sao?
Bạn mô tả ảnh hưởng của circuit breaker tới độ trễ và khả năng đáp ứng khi tỷ lệ lỗi tăng đột biến như thế nào?
Bạn phân biệt sự cố mạng, lỗi nghiệp vụ và lỗi quá tải khi quyết định mở circuit như thế nào?
Bạn xác định tín hiệu nào cho biết một dependency đang suy giảm trước khi nó hoàn toàn không khả dụng như thế nào?
Bạn sẽ chọn tiêu chí triển khai circuit breaker cho lời gọi đồng bộ và lời gọi bất đồng bộ ra sao?
Bạn giải thích cách circuit breaker có thể làm giảm áp lực retry và số kết nối đang chờ trên dependency như thế nào?
Bạn phân tích tác động nếu tất cả instance của cùng service đồng thời gọi lại một dependency vừa hồi phục ra sao?
Bạn sẽ mô tả giới hạn của circuit breaker khi bottleneck nằm trong chính ứng dụng gọi thay vì ở dependency như thế nào?
Bạn phân biệt circuit breaker với rate limiter, bulkhead và load shedding theo mục đích bảo vệ như thế nào?
Bạn đánh giá những trường hợp circuit breaker có thể làm tăng số phản hồi lỗi thay vì cải thiện tỷ lệ thành công ra sao?
Bạn xác định những quyết định nghiệp vụ nào phải được giữ ở ứng dụng thay vì giao phó cho cơ chế circuit breaker như thế nào?
Bạn mô tả ba trạng thái CLOSED, OPEN và HALF_OPEN của circuit breaker theo luồng xử lý request như thế nào?
Bạn giải thích hành vi của circuit breaker khi ở trạng thái CLOSED và tỷ lệ lỗi còn dưới ngưỡng ra sao?
Bạn phân tích điều kiện nào khiến circuit breaker chuyển từ CLOSED sang OPEN như thế nào?
Bạn giải thích vì sao OPEN thường từ chối lời gọi trước khi thực thi dependency như thế nào?
Bạn mô tả cách một circuit breaker ở OPEN xác định thời điểm thử phục hồi như thế nào?
Bạn phân biệt thời gian chờ ở OPEN với thời gian timeout của một lời gọi đang chạy như thế nào?
Bạn sẽ giải thích cách HALF_OPEN cho phép một số lời gọi kiểm tra khả năng phục hồi ra sao?
Bạn xác định kết quả nào khiến HALF_OPEN chuyển trở lại CLOSED hoặc OPEN như thế nào?
Bạn phân tích nguy cơ mở lại circuit vì số lượng probe quá ít trong HALF_OPEN ra sao?
Bạn sẽ thiết kế số lời gọi kiểm tra ở HALF_OPEN theo lưu lượng và độ ổn định của dependency như thế nào?
Bạn giải thích sự khác nhau giữa chuyển sang HALF_OPEN tự động và chuyển khi có lời gọi mới như thế nào?
Bạn phân biệt trạng thái DISABLED và FORCED_OPEN với các trạng thái vận hành thông thường của Resilience4j ra sao?
Bạn xác định trường hợp nào nên chủ động buộc circuit OPEN để giảm tác động của một sự cố diện rộng như thế nào?
Bạn sẽ mô tả rủi ro khi dùng chế độ METRICS_ONLY để theo dõi nhưng chưa chặn lời gọi như thế nào?
Bạn đánh giá hệ quả khi thao tác reset circuit breaker làm mất lịch sử đo lường như thế nào?
Bạn giải thích vai trò của sliding window trong việc tính toán chất lượng lời gọi tới dependency như thế nào?
Bạn phân biệt COUNT_BASED và TIME_BASED sliding window trong Resilience4j theo dữ liệu được giữ lại ra sao?
Bạn phân tích các trường hợp cửa sổ theo số lời gọi cho kết quả khác cửa sổ theo thời gian như thế nào?
Bạn sẽ lựa chọn kích thước sliding window dựa trên lưu lượng request và độ biến động của dependency ra sao?
Bạn giải thích tại sao minimumNumberOfCalls có thể làm circuit chưa mở khi mới xảy ra một vài lỗi như thế nào?
Bạn xác định cách failureRateThreshold và minimumNumberOfCalls phối hợp quyết định mở circuit như thế nào?
Bạn sẽ thiết kế ngưỡng lỗi cho một API có lưu lượng thấp khác API có lưu lượng cao ra sao?
Bạn phân biệt failure rate với slow call rate trong chính sách phát hiện dịch vụ suy giảm như thế nào?
Bạn giải thích vai trò của slowCallDurationThreshold khi phân loại một lời gọi chậm ra sao?
Bạn sẽ xác định slowCallRateThreshold phù hợp với SLA của dependency bằng dữ liệu latency như thế nào?
Bạn phân tích ảnh hưởng của trường hợp lời gọi chậm nhưng cuối cùng thành công đến cơ chế slow-call detection ra sao?
Bạn đánh giá hậu quả khi đặt ngưỡng failure rate quá thấp khiến circuit dễ bị mở bởi lỗi thoáng qua như thế nào?
Bạn sẽ chọn giá trị waitDurationInOpenState dựa trên đặc điểm phục hồi của dependency ra sao?
Bạn giải thích vai trò của permittedNumberOfCallsInHalfOpenState trong quá trình thử phục hồi như thế nào?
Bạn xác định khi nào maxWaitDurationInHalfOpenState hữu ích đối với các lời gọi probe bị treo như thế nào?
Bạn phân tích tác động của lưu lượng không đều tới độ tin cậy của sliding window theo thời gian như thế nào?
Bạn sẽ kiểm tra hành vi của circuit khi số lời gọi chưa đạt minimumNumberOfCalls ra sao?
Bạn phân biệt việc đếm lời gọi thành công, thất bại và lời gọi chậm khi đọc số liệu circuit breaker như thế nào?
Bạn phân tích cách đồng thời hóa nhiều request ảnh hưởng tới thời điểm kết quả được ghi nhận trong sliding window ra sao?
Bạn sẽ mô tả vì sao circuit breaker không nhất thiết giới hạn số request đang chạy đồng thời như thế nào?
Bạn xác định trường hợp nào một lỗi HTTP nên được coi là lỗi của dependency và trường hợp nào là phản hồi nghiệp vụ hợp lệ ra sao?
Bạn thiết kế quy tắc recordExceptions và ignoreExceptions theo các loại lỗi kỹ thuật như thế nào?
Bạn phân tích rủi ro khi tính cả lỗi validation của người dùng vào failure rate của một dịch vụ phụ thuộc như thế nào?
Bạn sẽ tùy chỉnh predicate phân loại lỗi mà vẫn tránh che giấu lỗi thực sự cần cảnh báo ra sao?
Bạn giải thích ảnh hưởng của một lỗi bị ignore tới thống kê và quyết định chuyển trạng thái như thế nào?
Bạn sẽ đánh giá chính sách phân loại HTTP 4xx, 5xx và timeout theo từng API phụ thuộc như thế nào?
Bạn xác định cách xử lý khi một response HTTP 200 vẫn chứa trạng thái lỗi nghiệp vụ mà ứng dụng cần nhận biết ra sao?
Bạn phân biệt lỗi được ném ra bởi thư viện client với lỗi do logic mapping response tạo ra như thế nào?
Bạn sẽ kiểm tra một loại exception mới có làm circuit hoạt động khác sau khi nâng cấp dependency ra sao?
Bạn giải thích Spring Cloud CircuitBreaker cung cấp lớp trừu tượng nào so với trực tiếp gọi Resilience4j API như thế nào?
Bạn phân biệt CircuitBreakerFactory và ReactiveCircuitBreakerFactory theo loại lời gọi cần bảo vệ ra sao?
Bạn sẽ xác định lúc nào dùng API Spring Cloud CircuitBreaker thay vì annotation trực tiếp của Resilience4j ra sao?
Bạn mô tả cách cấu hình dependency Spring Cloud CircuitBreaker với implementation Resilience4j trong Spring Boot như thế nào?
Bạn giải thích ảnh hưởng của phiên bản Spring Boot và Spring Cloud BOM tới khả năng tương thích của circuit breaker ra sao?
Bạn lựa chọn cách tạo breaker theo tên để các dependency khác nhau có thể dùng cấu hình riêng như thế nào?
Bạn mô tả cách gọi CircuitBreakerFactory tạo một circuit breaker và thực thi đoạn xử lý được bảo vệ ra sao?
Bạn sẽ quyết định phạm vi đối tượng circuit breaker được tái sử dụng giữa các request như thế nào?
Bạn phân biệt cấu hình mặc định và cấu hình riêng cho từng breaker instance trong Spring Cloud ra sao?
Bạn giải thích vai trò của Resilience4JCircuitBreakerFactory khi tích hợp với Spring Cloud như thế nào?
Bạn sẽ dùng Resilience4jConfigBuilder để cấu hình circuit breaker và time limiter theo mục tiêu gì?
Bạn phân tích nguy cơ cấu hình sai tên breaker khiến nhiều lời gọi dùng chung chính sách không mong muốn ra sao?
Bạn sẽ cấu hình các ngưỡng và thời gian thông qua Spring Boot properties theo từng dependency như thế nào?
Bạn phân biệt cách cấu hình trong mã Java với cách điều chỉnh bằng application.yml theo khả năng vận hành ra sao?
Bạn giải thích việc thay đổi một property runtime có nhất thiết cập nhật breaker đã tạo sẵn hay không như thế nào?
Bạn xác định chiến lược đặt tên breaker ổn định để giữ tính liên tục của metrics qua các lần deploy ra sao?
Bạn sẽ xây dựng lớp adapter cho outbound HTTP client để logic nghiệp vụ không lệ thuộc trực tiếp vào API breaker ra sao?
Bạn phân biệt cấu hình circuit breaker ở tầng service với cấu hình trong HTTP client hoặc gateway như thế nào?
Bạn sẽ kiểm tra circuit breaker có được áp dụng thật cho lời gọi thay vì chỉ được khai báo bean ra sao?
Bạn phân tích tác động nếu một lời gọi dependency được bảo vệ bởi nhiều breaker xếp chồng không chủ ý như thế nào?
Bạn lựa chọn cách kết hợp cấu hình ứng dụng và cấu hình thư viện để tránh trùng tên hoặc ghi đè ngoài ý muốn ra sao?
Bạn sẽ giải thích khi nào dùng annotation @CircuitBreaker của Resilience4j và cần chú ý điều kiện proxy nào?
Bạn phân tích vì sao self-invocation có thể khiến một cơ chế áp dụng qua Spring AOP không được kích hoạt như thế nào?
Bạn sẽ kiểm thử một phương thức được bọc bằng AOP có thực sự chạy qua circuit breaker như thế nào?
Bạn xác định những lời gọi nội bộ nào không nên đặt circuit breaker vì không phải ranh giới lỗi từ dependency ra sao?
Bạn sẽ xử lý trường hợp một service gọi hai dependency có SLA khác nhau bằng cấu hình breaker như thế nào?
Bạn phân biệt fallback của circuit breaker với việc bắt exception ở tầng controller ra sao?
Bạn thiết kế fallback trả về dữ liệu cache khi dependency không khả dụng theo những điều kiện nào?
Bạn phân tích rủi ro của việc trả dữ liệu cũ từ fallback đối với quyết định nghiệp vụ quan trọng như thế nào?
Bạn sẽ xác định khi nào fallback nên trả kết quả rỗng và khi nào phải báo lỗi rõ ràng cho caller ra sao?
Bạn giải thích vì sao fallback phải giữ hợp đồng dữ liệu và ngữ nghĩa của API gốc như thế nào?
Bạn đánh giá rủi ro biến lỗi thực sự thành response 200 OK bằng một fallback không phù hợp ra sao?
Bạn sẽ phân biệt fallback cho thao tác đọc với fallback cho thao tác ghi có tác dụng phụ như thế nào?
Bạn thiết kế phản hồi degradation có cờ chỉ rõ kết quả được lấy từ cache hoặc nguồn dự phòng ra sao?
Bạn sẽ bảo đảm fallback không gọi lại dependency đang hỏng gây vòng lặp lỗi như thế nào?
Bạn xác định cách giới hạn thời gian và tài nguyên tiêu thụ của fallback khi chính nguồn dự phòng cũng chậm ra sao?
Bạn phân tích hành vi khi fallback ném exception và cách phản hồi lỗi cuối cùng đến caller như thế nào?
Bạn sẽ thiết kế phương án giữ nguyên khả năng đặt hàng cơ bản khi hệ thống gợi ý sản phẩm bị lỗi ra sao?
Bạn đánh giá tính đúng đắn khi fallback trả danh sách trống cho lỗi truy vấn dữ liệu có ý nghĩa nghiệp vụ ra sao?
Bạn sẽ bảo đảm fallback không che giấu những lỗi về xác thực hoặc phân quyền như thế nào?
Bạn phân biệt chiến lược fail-open và fail-closed ở từng nghiệp vụ khi dependency lỗi ra sao?
Bạn xác định các metadata cần kèm theo một kết quả fallback để hỗ trợ đối soát và chẩn đoán như thế nào?
Bạn sẽ lựa chọn fallback theo loại exception và trạng thái circuit breaker bằng những quy tắc nào?
Bạn phân tích vì sao một hệ thống thanh toán có thể cần trả trạng thái chưa xác định thay vì tự động thành công khi fallback ra sao?
Bạn sẽ kiểm thử fallback vẫn hoạt động đúng khi circuit OPEN và khi lời gọi được phép nhưng thất bại ra sao?
Bạn mô tả vai trò của timeout trong việc giới hạn thời gian chờ dependency trước khi kết luận lời gọi thất bại như thế nào?
Bạn phân biệt timeout ở HTTP client với TimeLimiter của Resilience4j theo phạm vi kiểm soát ra sao?
Bạn sẽ xác định deadline đầu cuối từ một HTTP request qua nhiều lời gọi dependency như thế nào?
Bạn giải thích vì sao timeout quá dài có thể làm worker hoặc connection pool cạn tài nguyên như thế nào?
Bạn phân tích rủi ro đặt timeout quá ngắn khiến nhiều lời gọi khỏe mạnh bị phân loại thất bại như thế nào?
Bạn sẽ lựa chọn timeout dựa trên phân bố latency p95, p99 và ngân sách SLA như thế nào?
Bạn phân biệt timeout, cancellation và việc tác vụ hạ nguồn đã thực sự ngừng chạy như thế nào?
Bạn sẽ mô tả tác động nếu TimeLimiter hết hạn nhưng thao tác ghi phía dependency vẫn có thể hoàn tất ra sao?
Bạn xác định cách truyền deadline tới những client hoặc thư viện không hỗ trợ hủy công việc như thế nào?
Bạn phân tích vì sao việc kết hợp timeout và retry có thể vượt quá ngân sách thời gian của caller ra sao?
Bạn giải thích bulkhead hạn chế lỗi dây chuyền bằng cách cô lập tài nguyên như thế nào?
Bạn phân biệt SemaphoreBulkhead và ThreadPoolBulkhead của Resilience4j theo mô hình thực thi như thế nào?
Bạn sẽ chọn bulkhead semaphore cho lời gọi không blocking trong trường hợp nào?
Bạn phân tích khi nào thread-pool bulkhead phù hợp với một thư viện blocking không thể thay thế ra sao?
Bạn sẽ xác định số lượng lời gọi đồng thời tối đa cho một dependency theo connection pool và throughput như thế nào?
Bạn phân biệt số task chờ trong bulkhead với số lời gọi đang thực thi như thế nào?
Bạn đánh giá hậu quả của queue bulkhead không giới hạn đối với bộ nhớ và độ trễ khi dependency chậm ra sao?
Bạn mô tả sự khác biệt giữa breaker từ chối lời gọi do OPEN và bulkhead từ chối do hết suất như thế nào?
Bạn sẽ chọn fallback khi bulkhead đầy khác fallback khi circuit OPEN trong trường hợp nào?
Bạn xác định làm thế nào để bảo vệ một dependency yếu mà không làm nghẽn toàn bộ thread pool chung ra sao?
Bạn phân tích ảnh hưởng của BulkheadFullException tới chính sách đếm lỗi của circuit breaker như thế nào?
Bạn sẽ quyết định thứ tự bọc bulkhead, circuit breaker và time limiter dựa trên loại lỗi cần ghi nhận ra sao?
Bạn giải thích vì sao circuit breaker không thay thế giới hạn concurrency của bulkhead như thế nào?
Bạn sẽ kiểm thử bulkhead giữ được giới hạn số lời gọi đồng thời trong tình huống nhiều request đến cùng lúc ra sao?
Bạn phân biệt retry với circuit breaker theo thời điểm và điều kiện tái thực hiện lời gọi như thế nào?
Bạn sẽ chọn chính sách retry chỉ cho những lỗi có khả năng phục hồi ra sao?
Bạn phân tích vì sao retry dồn dập có thể làm dịch vụ đã yếu càng quá tải như thế nào?
Bạn thiết kế exponential backoff và jitter để tránh các instance đồng thời retry như thế nào?
Bạn sẽ xác định số lần retry tối đa mà vẫn tuân thủ deadline của yêu cầu gốc ra sao?
Bạn đánh giá thứ tự áp dụng retry và circuit breaker ảnh hưởng tới cách thống kê lỗi như thế nào?
Bạn phân biệt việc circuit ghi nhận mỗi attempt với ghi nhận kết quả cuối sau toàn bộ retry như thế nào?
Bạn sẽ kiểm tra lời gọi retry có bị circuit OPEN chặn đúng lúc dependency suy giảm như thế nào?
Bạn giải thích vì sao retry thao tác ghi có thể tạo side effect trùng dù circuit breaker hoạt động đúng như thế nào?
Bạn thiết kế idempotency key cho các lời gọi thay đổi dữ liệu có thể bị retry như thế nào?
Bạn sẽ phân biệt lỗi timeout khi thao tác có thể đã commit với lỗi được xác nhận chưa thực thi ra sao?
Bạn phân tích cách retry và fallback kết hợp sai thứ tự có thể làm caller thấy kết quả thành công giả như thế nào?
Bạn phân biệt rate limiter với bulkhead khi muốn giới hạn lượt gọi trong một khoảng thời gian như thế nào?
Bạn lựa chọn cách kết hợp rate limiting với circuit breaker khi dependency có quota rõ ràng ra sao?
Bạn sẽ xác định cần trả lỗi ngay hay xếp hàng khi rate limit hoặc bulkhead đã đạt ngưỡng như thế nào?
Bạn giải thích vì sao circuit breaker và retry không tự bảo đảm exactly-once cho nghiệp vụ ra sao?
Bạn thiết kế ngân sách retry chia sẻ giữa nhiều tầng client và service để tránh retry amplification như thế nào?
Bạn sẽ bảo đảm chính sách retry không thực thi lại fallback nhiều lần ngoài mong đợi ra sao?
Bạn xác định cách tránh circuit mở do lỗi do bulkhead hoặc rate limiter tự từ chối thay vì dependency thất bại ra sao?
Bạn mô tả sự khác biệt giữa blocking và reactive circuit breaker khi một lời gọi trả Mono hoặc Flux như thế nào?
Bạn giải thích vai trò của ReactiveCircuitBreakerFactory trong việc bảo vệ pipeline reactive ra sao?
Bạn sẽ bọc một Mono gọi dịch vụ ngoài bằng reactive circuit breaker mà không gọi block như thế nào?
Bạn phân tích vì sao subscription quyết định thời điểm bắt đầu một lời gọi reactive được bảo vệ ra sao?
Bạn phân biệt lỗi terminal trong Mono với một giá trị nghiệp vụ báo thất bại khi circuit breaker đo kết quả như thế nào?
Bạn sẽ thiết kế fallback Mono khi pipeline bị từ chối do circuit đang OPEN ra sao?
Bạn phân tích cách fallback cho Flux phát nhiều phần tử cần được thiết kế khác fallback cho Mono như thế nào?
Bạn sẽ xử lý Flux đã phát một phần dữ liệu rồi gặp lỗi mà không làm người dùng hiểu nhầm kết quả đầy đủ ra sao?
Bạn giải thích cancellation của subscriber có thể ảnh hưởng vòng đời lời gọi và số liệu circuit breaker như thế nào?
Bạn xác định cách xử lý timeout trong một chuỗi WebClient reactive mà không giữ connection vô hạn ra sao?
Bạn phân biệt subscribeOn và publishOn với cơ chế circuit breaker trong quản lý thread như thế nào?
Bạn đánh giá tác động của việc dùng block trong một WebFlux request tới khả năng chịu tải dù circuit breaker đã được áp dụng ra sao?
Bạn sẽ giới hạn concurrency của các inner publisher khi dùng flatMap gọi dependency như thế nào?
Bạn phân tích quan hệ giữa backpressure của Flux và bulkhead khi downstream tiêu thụ chậm như thế nào?
Bạn sẽ tránh phát lại toàn bộ một Flux có tác dụng phụ khi kết hợp retryWhen với circuit breaker ra sao?
Bạn mô tả thời điểm circuit breaker ghi nhận lỗi khi một Mono chỉ được subscribe sau một khoảng trì hoãn như thế nào?
Bạn sẽ thiết kế kiểm thử với StepVerifier cho phản hồi reactive khi circuit OPEN ra sao?
Bạn phân biệt fallback ở mức onErrorResume với fallback do ReactiveCircuitBreakerFactory cung cấp như thế nào?
Bạn phân tích rủi ro khi dùng onErrorContinue khiến một số lỗi không đến được circuit breaker như thế nào?
Bạn sẽ truyền trace context qua Reactor Context và các tác vụ circuit breaker như thế nào?
Bạn xác định chính sách hủy hoặc dọn dẹp tài nguyên khi reactive circuit breaker chuyển trạng thái giữa lúc nhiều subscription hoạt động ra sao?
Bạn sẽ kiểm thử một reactive fallback vẫn tuân thủ quy tắc phát tín hiệu của Mono và Flux ra sao?
Bạn xác định khi nào nên dùng StepVerifier.withVirtualTime để kiểm tra retry, timeout hoặc chu kỳ chuyển trạng thái như thế nào?
Bạn giải thích khả năng quan sát trạng thái CLOSED, OPEN và HALF_OPEN giúp người vận hành đánh giá bảo vệ hệ thống ra sao?
Bạn sẽ theo dõi tỷ lệ call thành công, failed, slow và not permitted của một circuit breaker như thế nào?
Bạn phân biệt lỗi dependency thực sự với CallNotPermittedException do breaker OPEN khi thiết kế metric ra sao?
Bạn sẽ tích hợp Resilience4j metrics với Micrometer và Spring Boot Actuator như thế nào?
Bạn lựa chọn metric nào cho phép phát hiện một circuit đang dao động OPEN và CLOSED liên tục ra sao?
Bạn phân tích ý nghĩa của số lượng not-permitted calls tăng dù failure rate trong cửa sổ hiện tại giảm như thế nào?
Bạn sẽ lập dashboard theo breaker name và dependency để tránh trộn số liệu của nhiều service như thế nào?
Bạn xác định cách đặt tag metrics ổn định và tránh cardinality cao khi gắn tên breaker như thế nào?
Bạn phân biệt state transition event với sự kiện mỗi lời gọi thất bại khi ghi log ra sao?
Bạn sẽ sử dụng event publisher của Resilience4j để theo dõi chuyển trạng thái và lỗi bị từ chối như thế nào?
Bạn lựa chọn khi nào cần log chi tiết sự kiện breaker và khi nào chỉ cần aggregate metric như thế nào?
Bạn sẽ gắn correlation ID và trace ID vào log khi breaker chặn một request như thế nào?
Bạn phân tích vì sao một trace của lời gọi bị chặn sớm có thể không có span outbound tới dependency ra sao?
Bạn xác định alert theo tỷ lệ OPEN, số not-permitted calls và độ trễ fallback như thế nào?
Bạn sẽ phát hiện một circuit breaker OPEN dài bất thường dù dependency đã phục hồi ra sao?
Bạn phân biệt circuit mở đúng để bảo vệ dịch vụ với cấu hình quá nhạy dẫn tới chặn nhầm như thế nào?
Bạn đánh giá tác động của tỷ lệ sampling trace tới khả năng chẩn đoán các lời gọi probe hiếm ở HALF_OPEN ra sao?
Bạn sẽ dùng metrics và traces để đối chiếu độ trễ dependency trước và sau khi bật circuit breaker ra sao?
Bạn mô tả cách đo tỷ lệ request thành công cuối cùng ở API thay vì chỉ xem tỷ lệ thành công của breaker như thế nào?
Bạn phân tích rủi ro dashboard chỉ đếm HTTP 200 từ fallback và che khuất mức độ suy giảm của dependency ra sao?
Bạn lựa chọn cách đo latency của fallback để bảo đảm chính cơ chế dự phòng không gây thêm nghẽn như thế nào?
Bạn sẽ kiểm tra độ chính xác của số liệu khi một breaker được dùng bởi nhiều instance ứng dụng ra sao?
Bạn giải thích vì sao trạng thái circuit breaker thường là trạng thái cục bộ theo instance thay vì tự động thống nhất trên toàn cluster ra sao?
Bạn đánh giá tác động khi các instance có trạng thái breaker khác nhau trước cùng một dependency như thế nào?
Bạn sẽ xác định cách điều phối traffic hoặc giới hạn probe khi nhiều instance cùng chuyển sang HALF_OPEN ra sao?
Bạn thiết kế phép đo chứng minh circuit breaker làm giảm lỗi dây chuyền chứ không chỉ tăng phản hồi fallback như thế nào?
Bạn sẽ xác định chi phí observability cần trả khi bật nhiều metric và event cho từng breaker ra sao?
Bạn phân biệt cấu hình resilience phù hợp ở development, staging và production theo dữ liệu thực tế như thế nào?
Bạn sẽ thiết kế cấu hình mặc định và cấu hình riêng cho dependency quan trọng trong nhiều môi trường ra sao?
Bạn đánh giá rủi ro thay đổi threshold bằng hot reload khi breaker đang giữ dữ liệu cửa sổ như thế nào?
Bạn sẽ thử nghiệm ngưỡng mới trên một nhóm instance trước khi rollout toàn hệ thống ra sao?
Bạn xác định chiến lược rollback khi cấu hình breaker mới làm tăng lỗi bị từ chối ngoài mong đợi như thế nào?
Bạn xây dựng runbook vận hành khi một breaker mở liên tục trong thời gian dài như thế nào?
Bạn sẽ quyết định khi nào cần chủ động tắt tính năng phụ thuộc thay vì để fallback hoạt động mãi ra sao?
Bạn phân tích tác động của deploy hoặc restart instance tới thống kê cửa sổ và trạng thái breaker như thế nào?
Bạn sẽ bảo vệ thông tin nhạy cảm trong exception và logs liên quan đến fallback và request lỗi ra sao?
Bạn thiết kế việc phân quyền cho endpoint quản trị trạng thái breaker hoặc thay đổi cấu hình như thế nào?
Bạn phân biệt hành vi circuit breaker khi downstream trả HTTP 401 hoặc 403 do lỗi quyền với lỗi 503 do không khả dụng ra sao?
Bạn sẽ tránh fallback bỏ qua kiểm tra quyền hoặc trả dữ liệu của tenant khác khi dependency lỗi như thế nào?
Bạn xác định cách kiểm tra fallback không làm phát sinh side effect mà người dùng chưa chấp thuận ra sao?
Bạn đánh giá hậu quả nếu fallback cho một lời gọi đọc số dư trả giá trị mặc định thay vì báo không chắc chắn như thế nào?
Bạn thiết kế cách kiểm thử một CircuitBreaker chuyển CLOSED sang OPEN khi đạt đủ số lỗi trong sliding window ra sao?
Bạn sẽ kiểm thử trường hợp chưa đủ minimumNumberOfCalls nhưng toàn bộ các cuộc gọi đều thất bại như thế nào?
Bạn giải thích cách mô phỏng thời gian để kiểm tra OPEN sang HALF_OPEN mà không dùng sleep kéo dài ra sao?
Bạn xác định cách kiểm tra số permitted calls ở HALF_OPEN và hành vi khi probe chưa hoàn tất ra sao?
Bạn sẽ kiểm thử HALF_OPEN phục hồi sang CLOSED và tái mở khi các probe thất bại như thế nào?
Bạn thiết kế kiểm thử COUNT_BASED và TIME_BASED sliding window với các chuỗi sự kiện khác nhau ra sao?
Bạn sẽ kiểm thử slow-call threshold khi lời gọi chậm nhưng không ném exception như thế nào?
Bạn xác định cách kiểm tra recordExceptions và ignoreExceptions bằng các lớp lỗi nghiệp vụ khác nhau ra sao?
Bạn sẽ giả lập dependency timeout để kiểm thử TimeLimiter và chính sách ghi nhận lỗi của breaker ra sao?
Bạn phân tích cách dùng fake clock hoặc nguồn thời gian điều khiển được giúp kiểm thử circuit breaker ổn định như thế nào?
Bạn xây dựng integration test cho Spring Cloud CircuitBreaker với client HTTP stub như thế nào?
Bạn xác định cách chứng minh breaker thực sự chặn lời gọi outbound khi OPEN mà không chỉ trả về lỗi mô phỏng ra sao?
Bạn sẽ kiểm thử fallback riêng cho trường hợp circuit OPEN, lỗi 5xx và lỗi timeout như thế nào?
Bạn thiết kế kiểm thử để bảo đảm fallback không gọi lại dependency lỗi và không rò rỉ dữ liệu nhạy cảm ra sao?
Bạn kiểm thử SemaphoreBulkhead giới hạn số yêu cầu đồng thời dưới tải lớn bằng phương pháp nào?
Bạn sẽ kiểm tra ThreadPoolBulkhead khi queue đầy hoặc worker bị blocking kéo dài ra sao?
Bạn mô phỏng retry storm để kiểm tra backoff và circuit breaker phối hợp bảo vệ dependency như thế nào?
Bạn xác định cách kiểm thử idempotency khi request ghi bị timeout và được retry sau đó ra sao?
Bạn viết kiểm thử StepVerifier cho Mono bị lỗi và Mono fallback thành công như thế nào?
Bạn sẽ kiểm thử ReactiveCircuitBreakerFactory không tự gây blocking trên event loop ra sao?
Bạn thiết kế kiểm thử cancellation khi subscriber dừng trước khi dependency phản hồi như thế nào?
Bạn đánh giá bằng load test tác động của circuit breaker tới throughput, p99 và tỷ lệ fallback trước một dependency lỗi ra sao?
Bạn sẽ mô phỏng lỗi mạng chập chờn và dependency phục hồi theo từng giai đoạn trong chaos test như thế nào?
Bạn xác định tiêu chí nghiệm thu chứng minh breaker ngăn cạn connection pool và thread pool trong kịch bản suy giảm như thế nào?
Bạn xây dựng kiểm thử bảo đảm metrics và sự kiện chuyển trạng thái phản ánh hành vi breaker sau khi deploy như thế nào?
Nếu một API phụ thuộc chậm dần nhưng hiếm khi ném exception, bạn sẽ cấu hình slow-call detection như thế nào?
Nếu breaker mở sau vài lỗi đơn lẻ dù dịch vụ nhìn chung khỏe, bạn sẽ điều chỉnh sliding window và minimumNumberOfCalls ra sao?
Nếu một dependency đã hồi phục nhưng circuit vẫn OPEN và không có traffic, bạn sẽ điều tra cơ chế chuyển trạng thái như thế nào?
Nếu nhiều request vào HALF_OPEN đồng thời nhưng chỉ một số được phép chạy, bạn sẽ giải thích và cấu hình lại thế nào?
Nếu fallback trả dữ liệu cache hết hạn khiến người dùng đưa ra quyết định sai, bạn sẽ sửa hợp đồng phản hồi ra sao?
Nếu retry và circuit breaker cùng bật khiến số request outbound tăng gấp nhiều lần, bạn sẽ xem lại thứ tự bọc và ngân sách retry như thế nào?
Nếu TimeLimiter báo timeout nhưng service thanh toán vẫn commit giao dịch, bạn sẽ thiết kế phản hồi và idempotency như thế nào?
Nếu bulkhead từ chối request nhưng breaker lại ghi nhận tỷ lệ lỗi cao, bạn sẽ kiểm tra thứ tự bọc và phân loại exception ra sao?
Nếu một lời gọi WebClient bị chặn bởi breaker nhưng trace không có outbound span, bạn sẽ điều tra telemetry như thế nào?
Nếu các instance có trạng thái breaker khác nhau sau deploy, bạn sẽ giải thích nguyên nhân và điều chỉnh vận hành ra sao?
Nếu cơ chế @CircuitBreaker không có hiệu lực khi một method trong cùng bean gọi method khác, bạn sẽ chẩn đoán proxy như thế nào?
Nếu circuit breaker chạy tốt trong unit test nhưng tải production vẫn làm cạn connection pool, bạn sẽ đánh giá giới hạn bulkhead và timeout ra sao?
Nếu người dùng cần trả về trạng thái chính xác khi dependency bị lỗi, bạn sẽ thiết kế fallback cho thao tác đọc và ghi khác nhau thế nào?
Nếu phải xây dựng circuit breaker cho Spring Cloud service từ đầu, bạn sẽ chọn ngưỡng, timeout, bulkhead, fallback, monitoring và kiểm thử ra sao?
