Bạn xác định những trách nhiệm nào nên và không nên đặt tại API Gateway trong kiến trúc microservices, và vì sao?
Bạn phân biệt API Gateway với reverse proxy và service mesh theo vị trí xử lý request và phạm vi chính sách ra sao?
Bạn mô tả đường đi của một HTTP request từ client qua Spring Cloud Gateway tới dịch vụ backend như thế nào?
Bạn so sánh Spring Cloud Gateway trên nền WebFlux với biến thể Server MVC theo mô hình xử lý I/O và khả năng tích hợp như thế nào?
Bạn quyết định khi nào nên triển khai gateway riêng thay vì để load balancer chuyển tiếp trực tiếp tới từng microservice ra sao?
Bạn thiết kế sơ đồ định tuyến cho nhiều dịch vụ dùng chung một domain nhưng có prefix URL khác nhau như thế nào?
Bạn phân biệt Route, Predicate và Filter trong Spring Cloud Gateway bằng các trách nhiệm cụ thể nào?
Bạn giải thích một route definition gồm ID, URI đích, predicates, filters và order phối hợp để xử lý request như thế nào?
Bạn lựa chọn cấu hình route tĩnh hay tạo route động từ nguồn cấu hình dựa trên yêu cầu vận hành nào?
Bạn tổ chức cấu hình các route trong application.yaml để tránh trùng ID và xung đột đường dẫn như thế nào?
Bạn phát hiện và xử lý cấu hình chồng lấn khi nhiều route cùng khớp một HTTP request trước khi triển khai như thế nào?
Bạn giải thích vai trò của order trong lựa chọn route khi một path cụ thể nằm trong một path tổng quát như thế nào?
Bạn thiết kế route dùng Path predicate để chuyển các request theo prefix tới đúng dịch vụ như thế nào?
Bạn kết hợp Method predicate với Path predicate để phân biệt những thao tác HTTP dùng chung đường dẫn ra sao?
Bạn sử dụng Header predicate để yêu cầu một header có giá trị hợp lệ mà không nhầm với kiểm tra quyền truy cập như thế nào?
Bạn lựa chọn Query predicate khi việc định tuyến phụ thuộc vào tham số truy vấn và kiểm tra các giá trị động ra sao?
Bạn sử dụng Host predicate để hỗ trợ nhiều tên miền trên cùng gateway mà vẫn giữ đúng virtual host như thế nào?
Bạn giải thích cách RemoteAddr predicate hoạt động khi client kết nối qua nhiều lớp reverse proxy và load balancer ra sao?
Bạn thiết kế điều kiện định tuyến dựa trên thời gian hoặc cửa sổ bảo trì bằng các predicate phù hợp như thế nào?
Bạn kiểm thử một route chỉ được kích hoạt khi đồng thời khớp path, method và header bằng cách nào?
Bạn phân tích lý do một request nhận HTTP 404 từ gateway dù dịch vụ đích vẫn hoạt động bình thường như thế nào?
Bạn phân biệt lỗi không khớp route với lỗi backend trả HTTP 404 sau khi request đã được chuyển tiếp ra sao?
Bạn xây dựng RoutePredicateFactory tùy biến khi điều kiện định tuyến vượt quá các predicate có sẵn như thế nào?
Bạn xác định các giới hạn nên đặt lên logic predicate để việc tìm route không thực hiện thao tác chặn hoặc tốn tài nguyên ra sao?
Bạn tổ chức kiểm thử một custom predicate với request headers và query parameters đa dạng như thế nào?
Bạn mô tả trình tự xử lý của GatewayFilterChain từ trước khi gửi request tới backend cho đến sau khi nhận response như thế nào?
Bạn phân biệt GatewayFilter gắn với một route và GlobalFilter áp dụng cho nhiều route theo phạm vi tác động ra sao?
Bạn giải thích tác động của Ordered hoặc @Order lên thứ tự chạy filter ở giai đoạn pre và post như thế nào?
Bạn thiết kế một GlobalFilter ghi nhận thời gian request mà vẫn bảo đảm thao tác sau chain chạy cả khi downstream lỗi ra sao?
Bạn đánh giá vì sao filter không nên chặn Netty event-loop bằng truy vấn cơ sở dữ liệu hoặc thao tác I/O đồng bộ như thế nào?
Bạn tổ chức filter tùy biến theo nguyên tắc bất biến của request và response trong ServerWebExchange như thế nào?
Bạn sử dụng các exchange attributes để trao đổi thông tin giữa các filter mà không làm rò rỉ dữ liệu giữa hai request ra sao?
Bạn thiết kế một GatewayFilterFactory có cấu hình riêng cho từng route và cách kiểm tra cấu hình không hợp lệ như thế nào?
Bạn phân tích nguyên nhân một filter tùy biến chạy hai lần hoặc không chạy trên route mong muốn bằng cách nào?
Bạn phân biệt AddRequestHeader, SetRequestHeader và RemoveRequestHeader khi cần điều chỉnh metadata gửi tới backend như thế nào?
Bạn xác định khi nào cần xóa các hop-by-hop headers hoặc header nhạy cảm trước khi chuyển tiếp request ra sao?
Bạn sử dụng StripPrefix và PrefixPath để ánh xạ path công khai sang path nội bộ mà không làm hỏng endpoint backend như thế nào?
Bạn so sánh RewritePath và SetPath khi thiết kế biến đổi URL có path variables hoặc biểu thức chính quy ra sao?
Bạn kiểm thử một route chuyển /api/orders/123 thành path nội bộ tương ứng và vẫn giữ query string bằng cách nào?
Bạn phân tích nguy cơ tạo đường dẫn kép hoặc mất dấu slash khi kết hợp nhiều filter biến đổi path như thế nào?
Bạn thiết kế cách biến đổi response headers mà không để lộ hostname hoặc địa chỉ nội bộ của backend như thế nào?
Bạn xác định tình huống cần dùng ModifyRequestBody hoặc ModifyResponseBody và các rủi ro về bộ đệm như thế nào?
Bạn kiểm soát dung lượng payload và bộ nhớ khi gateway phải đọc toàn bộ JSON body để biến đổi nội dung như thế nào?
Bạn đánh giá khi nào nên giữ dữ liệu request nguyên trạng để backend tự xử lý thay vì đặt logic chuyển đổi nghiệp vụ trong gateway ra sao?
Bạn xử lý Content-Type, Content-Length và mã hóa body sau một phép biến đổi request hoặc response như thế nào?
Bạn thiết kế kiểm thử cho filter xử lý payload Unicode hoặc JSON lỗi định dạng mà không làm sai HTTP status như thế nào?
Bạn mô tả cách Spring Cloud Gateway sử dụng lb:// service URI khi kết hợp với cơ chế cân bằng tải phía client như thế nào?
Bạn phân biệt một URI cố định với URI dùng service discovery khi số instance của backend thường xuyên thay đổi ra sao?
Bạn giải thích vai trò của DiscoveryClient trong quá trình tìm instance cho một logical service name như thế nào?
Bạn quyết định khi nào nên sử dụng DiscoveryClient Route Definition Locator để sinh route tự động từ dịch vụ đã đăng ký ra sao?
Bạn đánh giá các rủi ro bảo mật hoặc lộ endpoint khi tự động công bố route cho mọi dịch vụ từ service registry như thế nào?
Bạn kiểm tra một route dùng lb:// không tìm được instance dù dịch vụ có tên đúng trong cấu hình bằng những bước nào?
Bạn phân biệt lỗi tìm route, lỗi resolve service instance và lỗi kết nối đến instance đã được chọn như thế nào?
Bạn xác định cách bảo toàn Host header hoặc ghi đè Host khi backend yêu cầu virtual host cụ thể ra sao?
Bạn thiết kế chính sách cân bằng tải và xử lý instance unhealthy để giảm request lỗi khi registry cập nhật chậm như thế nào?
Bạn kiểm tra hành vi gateway khi service discovery tạm thời không truy cập được hoặc không có instance khả dụng ra sao?
Bạn đánh giá khi nào việc sticky session là cần thiết và khi nào nên chuyển sang session store dùng chung cho backend như thế nào?
Bạn thiết kế route tới một upstream hỗ trợ WebSocket và kiểm tra quá trình nâng cấp kết nối như thế nào?
Bạn phân biệt chuyển tiếp HTTP streaming, Server-Sent Events và WebSocket tại gateway theo đặc điểm kết nối như thế nào?
Bạn kiểm tra gateway có xử lý đúng việc client hủy subscription hoặc đóng kết nối trong một luồng streaming ra sao?
Bạn giải thích khác biệt giữa xác thực người dùng tại gateway và kiểm tra phân quyền nghiệp vụ ở từng microservice như thế nào?
Bạn tổ chức Spring Security filter chain với gateway filters để request chưa xác thực không thể vượt qua lớp bảo vệ như thế nào?
Bạn thiết kế xác thực JWT tại gateway và xác định những claim nào đáng tin để chuyển tới backend ra sao?
Bạn kiểm tra token hết hạn, chữ ký không hợp lệ và thiếu audience để trả HTTP status phù hợp bằng cách nào?
Bạn phân biệt xác thực OAuth2 Resource Server và OAuth2 Login tại gateway theo kiểu client và luồng truy cập như thế nào?
Bạn xác định khi nào dùng TokenRelay để chuyển access token đã được xác thực tới dịch vụ downstream ra sao?
Bạn giảm nguy cơ đưa token hoặc thông tin định danh nhạy cảm vào access log, tracing attributes và response headers bằng cách nào?
Bạn giải thích vì sao gateway không nên tin các header nhận dạng user do client tự gắn trước khi xác thực như thế nào?
Bạn thiết kế cơ chế xóa header nội bộ từ request bên ngoài rồi bổ sung lại thông tin định danh đáng tin cậy như thế nào?
Bạn phân biệt xác thực ở gateway với kiểm tra quyền truy cập theo tài nguyên hoặc tenant ở backend như thế nào?
Bạn kiểm thử một người dùng hợp lệ nhưng không có quyền gọi một route để tránh trả nhầm HTTP 401 thay vì 403 ra sao?
Bạn xử lý một preflight CORS request không mang token mà vẫn duy trì chính sách bảo vệ endpoint như thế nào?
Bạn cấu hình CORS ở gateway để tránh xung đột với CORS headers do backend cũng trả về ra sao?
Bạn xác định khi nào cần chính sách CSRF cho gateway sử dụng cookie-based authentication thay vì bearer token thuần túy như thế nào?
Bạn đánh giá nguy cơ giả mạo Forwarded hoặc X-Forwarded headers và lựa chọn phạm vi proxy đáng tin cậy ra sao?
Bạn kiểm tra cách gateway suy ra client IP chính xác khi có nhiều lớp reverse proxy và load balancer như thế nào?
Bạn thiết kế chính sách rate limiting theo user ID, API key hoặc IP và giải thích rủi ro của từng loại key ra sao?
Bạn phân biệt giới hạn lưu lượng tại gateway với quota nghiệp vụ và giới hạn đồng thời ở backend như thế nào?
Bạn giải thích cơ chế token bucket và cách nó điều tiết burst request so với tốc độ trung bình ra sao?
Bạn sử dụng RequestRateLimiter với một key resolver để phân phối hạn mức công bằng giữa nhiều client như thế nào?
Bạn xác định ý nghĩa của replenish rate, burst capacity và requested tokens khi cấu hình RedisRateLimiter ra sao?
Bạn thiết kế chính sách xử lý khi key resolver không tìm được danh tính client mà không vô tình cho phép vượt hạn mức như thế nào?
Bạn phân tích lý do một user bị trả HTTP 429 liên tục dù tổng số request toàn hệ thống chưa cao bằng cách nào?
Bạn kiểm thử rate limit trên nhiều gateway replicas để phát hiện sai lệch so với giới hạn toàn cụm ra sao?
Bạn quyết định gateway nên xử lý fail-open hay fail-closed khi Redis dùng cho rate limiting bị mất kết nối dựa trên rủi ro nào?
Bạn thiết kế response khi vượt giới hạn lưu lượng để client hiểu thời điểm retry phù hợp mà không làm lộ cấu hình nội bộ như thế nào?
Bạn phân biệt rate limiting, load shedding và circuit breaking khi upstream có dấu hiệu quá tải ra sao?
Bạn mô tả vai trò của CircuitBreaker gateway filter khi một upstream liên tục lỗi hoặc phản hồi quá chậm như thế nào?
Bạn phân biệt trạng thái closed, open và half-open của circuit breaker và tác động của chúng lên request ra sao?
Bạn lựa chọn ngưỡng lỗi, số lượng mẫu và khoảng thời gian mở circuit breaker theo đặc tính một upstream như thế nào?
Bạn thiết kế fallback khi circuit breaker mở mà không tạo ra response nhìn như thành công nhưng chứa dữ liệu không chính xác ra sao?
Bạn xử lý fallback URI và forwarding nội bộ để tránh vòng lặp route khi dịch vụ downstream lỗi như thế nào?
Bạn giải thích vì sao HTTP 5xx từ backend không tự động đồng nghĩa với lỗi kết nối cần kích hoạt circuit breaker trong mọi chính sách ra sao?
Bạn phân tích cách circuit breaker tương tác với Retry filter và thứ tự filter có thể ảnh hưởng số lần gọi backend như thế nào?
Bạn xác định khi nào retry request HTTP là hợp lý dựa trên method, trạng thái lỗi và tính idempotent của thao tác ra sao?
Bạn thiết kế chính sách retry cho một request POST có side effect để tránh tạo giao dịch trùng lặp như thế nào?
Bạn quyết định số lần retry, backoff và jitter sao cho không khuếch đại tải đúng lúc upstream đang gặp sự cố ra sao?
Bạn đánh giá các rủi ro khi retry một request có body lớn hoặc streaming body cần được phát lại như thế nào?
Bạn kiểm tra một request tới backend thất bại lần đầu nhưng thành công sau retry và xác minh số lần thực sự gọi upstream ra sao?
Bạn phân biệt timeout kết nối, timeout nhận response và thời hạn tổng thể của một request qua gateway như thế nào?
Bạn lựa chọn global connect timeout và response timeout so với cấu hình riêng cho một route dựa trên SLA nào?
Bạn phân tích một lỗi HTTP 504 từ gateway khi backend vẫn xử lý xong công việc để xác định rủi ro retry và trùng side effect ra sao?
Bạn thiết kế cancellation propagation để ngắt công việc không cần thiết khi client đã đóng kết nối giữa lúc chờ upstream như thế nào?
Bạn xác định khi nào cần giới hạn số kết nối hoặc pending acquire trong HTTP client connection pool của gateway ra sao?
Bạn giải thích tác động của pool cạn và event-loop bị blocking đối với p95/p99 latency của gateway như thế nào?
Bạn thiết kế biện pháp ngăn một route có upstream chậm chiếm hết tài nguyên cần cho các route khác ra sao?
Bạn đánh giá khả năng chuyển tiếp HTTP/2 giữa client, gateway và backend khi các hop có thể dùng phiên bản giao thức khác nhau như thế nào?
Bạn phân biệt TLS termination tại load balancer, TLS tới gateway và TLS từ gateway tới upstream theo mô hình tin cậy như thế nào?
Bạn thiết kế cấu hình HTTPS cho gateway với certificate và private key được cấp qua cơ chế quản lý secret như thế nào?
Bạn kiểm tra hostname verification và trust store khi gateway gọi một upstream qua HTTPS như thế nào?
Bạn phân biệt xác thực client bằng mTLS ở ingress với mTLS từ gateway đến backend và cách quản lý danh tính chứng chỉ ra sao?
Bạn lập kế hoạch certificate rotation trên gateway mà không làm gián đoạn các kết nối đang phục vụ như thế nào?
Bạn phân tích lỗi TLS handshake chỉ xảy ra với một số backend instances do trust chain hoặc SNI bằng cách nào?
Bạn xác định chính sách forwarded headers và redirect URL khi gateway nằm sau TLS-terminating reverse proxy ra sao?
Bạn thiết kế cách ẩn các HTTP headers hoặc error details có thể tiết lộ tên host và thông tin hạ tầng nội bộ như thế nào?
Bạn kiểm tra route, filter và response headers để hạn chế open redirect hoặc header injection qua dữ liệu người dùng ra sao?
Bạn giải thích vai trò của Actuator gateway endpoint trong việc quan sát routes và filters, đồng thời nêu rủi ro khi công khai endpoint này như thế nào?
Bạn kiểm tra các route đang hoạt động sau một lần cập nhật cấu hình và xác định khi nào cần làm mới route cache ra sao?
Bạn tổ chức quy trình thay đổi route động có kiểm soát, có audit và rollback khi cấu hình sai như thế nào?
Bạn thiết kế một cách kiểm thử regression cho route predicate và filter trước khi thay đổi cấu hình trên nhiều gateway replicas ra sao?
Bạn sử dụng Micrometer metrics để theo dõi số request, HTTP status, độ trễ và route ID tại gateway như thế nào?
Bạn tránh cardinality quá cao trong metrics khi URL chứa user ID hoặc tham số động bằng thiết kế tag nào?
Bạn phân biệt thời gian gateway xử lý filter với thời gian chờ upstream khi đọc distributed trace của một request ra sao?
Bạn thiết kế correlation ID và trace context để liên kết log gateway với log microservice đích như thế nào?
Bạn kiểm tra việc truyền W3C trace context qua gateway tới backend mà không làm lộ token người dùng như thế nào?
Bạn giải thích vì sao metric HTTP 200 của gateway không đủ để khẳng định backend nghiệp vụ đã xử lý thành công ra sao?
Bạn phân tích các lỗi HTTP 502, 503 và 504 quan sát ở gateway để phân biệt vấn đề service discovery, kết nối và timeout như thế nào?
Bạn xác định những log và metric nào giúp tìm ra một route đang tạo ra số lượng retry tăng mạnh sau rollout ra sao?
Bạn thiết kế dashboard theo từng route cho request rate, error rate, p95 latency, rejection và circuit breaker state như thế nào?
Bạn chuẩn bị load test để đo giới hạn throughput, connection reuse, CPU và bộ nhớ của gateway khi có nhiều upstream ra sao?
Bạn phân tích một gateway có CPU thấp nhưng latency tăng và active connections cao dựa trên thread, event-loop và pool metrics như thế nào?
Bạn kiểm tra xem gateway đang buffer quá nhiều payload trong quá trình response transformation bằng metric và tình huống thử nào?
Bạn lựa chọn cách triển khai nhiều gateway replicas với health/readiness probes và cân bằng tải phù hợp như thế nào?
Bạn đánh giá tác động của route discovery và cache đối với traffic khi một backend instance mới được thêm hoặc xóa như thế nào?
Bạn xây dựng chính sách graceful shutdown để gateway ngừng nhận request mới và xử lý các request đang thực hiện như thế nào?
Bạn thiết kế cách đóng hoặc chuyển hướng kết nối WebSocket và HTTP streaming khi một gateway replica sắp dừng ra sao?
Bạn phối hợp readiness, SIGTERM và termination grace period trong Kubernetes để hạn chế lỗi khi rolling deploy gateway như thế nào?
Bạn xác định chiến lược retry của client khi kết nối gateway bị cắt lúc deploy mà không phát sinh giao dịch trùng ra sao?
Bạn xây dựng integration test cho Gateway sử dụng upstream giả lập để xác minh routing, header/path rewrite và HTTP status như thế nào?
Bạn sử dụng WebTestClient với ứng dụng Gateway phản ứng để xác minh filter và response trong điều kiện bất đồng bộ như thế nào?
Bạn thiết kế kiểm thử bảo mật để phát hiện route mới được thêm nhưng chưa áp dụng chính sách authentication hoặc authorization ra sao?
Bạn mô phỏng Redis rate limiter không khả dụng và upstream chậm để kiểm thử chính sách từ chối hay fallback như thế nào?
Bạn kiểm thử circuit breaker và retry trong các tình huống upstream trả 5xx, timeout và phục hồi bằng cách nào?
Bạn phân tích sự cố một route chạy trên local nhưng trả 404 hoặc 503 ở production sau thay đổi service registry bằng các bước nào?
Bạn đề xuất cấu hình và quy trình vận hành Spring Cloud Gateway cho hệ thống nhiều microservice yêu cầu JWT, rate limit theo tenant, resilience và distributed tracing như thế nào?
