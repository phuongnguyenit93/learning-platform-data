Bạn giải thích vai trò của Spring Boot trong việc tích hợp nhiều hệ thống có giao thức và mô hình dữ liệu khác nhau như thế nào?
Bạn lựa chọn tích hợp đồng bộ hay bất đồng bộ dựa trên yêu cầu nghiệp vụ và ngân sách độ trễ nào?
Bạn phân biệt integration layer với domain layer khi thiết kế ứng dụng Spring Boot như thế nào?
Bạn xác định ranh giới giữa một adapter tích hợp và logic nghiệp vụ cốt lõi ra sao?
Bạn sử dụng kiến trúc ports and adapters để cô lập các client bên ngoài như thế nào?
Bạn thiết kế khả năng thay thế một nhà cung cấp dịch vụ mà không sửa luồng nghiệp vụ chính ra sao?
Bạn đánh giá mức độ coupling khi nhiều service dùng chung một database so với giao tiếp qua API như thế nào?
Bạn lựa chọn giao tiếp request-response thay cho sự kiện khi cần kết quả tức thời theo tiêu chí nào?
Bạn nhận diện các điểm lỗi độc lập trong một luồng tích hợp qua nhiều hệ thống như thế nào?
Bạn phân biệt tính sẵn sàng của ứng dụng với tính sẵn sàng của từng dependency tích hợp ra sao?
Bạn lập sơ đồ luồng dữ liệu giữa HTTP API, cơ sở dữ liệu, cache và message broker như thế nào?
Bạn phân loại dữ liệu nào là nguồn sự thật và dữ liệu nào chỉ là bản sao phục vụ truy xuất nhanh ra sao?
Bạn thiết kế hợp đồng rõ ràng cho dữ liệu chuyển giữa hai bounded context như thế nào?
Bạn phân biệt dữ liệu nội bộ và DTO trao đổi giữa các hệ thống nhằm tránh rò rỉ schema ra sao?
Bạn quản lý định danh yêu cầu xuyên nhiều bước tích hợp để đối soát lỗi như thế nào?
Bạn đánh giá tác động của việc thêm một hệ thống phụ thuộc tới p99 latency của API như thế nào?
Bạn thiết kế graceful degradation khi một dependency không thiết yếu không hoạt động ra sao?
Bạn xác định những bước tích hợp nào bắt buộc phải hoàn thành trước khi trả kết quả cho người dùng?
Bạn xử lý eventual consistency khi dữ liệu cập nhật ở nhiều dịch vụ theo thời điểm khác nhau như thế nào?
Bạn phân biệt orchestration và choreography cho quy trình tích hợp nhiều dịch vụ ra sao?
Bạn thiết kế giới hạn tài nguyên của từng adapter để sự cố ở một downstream không lan sang toàn ứng dụng như thế nào?
Bạn chọn cách đồng bộ hóa dữ liệu bằng batch, polling hay event-driven theo đặc điểm nào?
Bạn đánh giá khả năng vận hành của một tích hợp khi phụ thuộc vào nhiều API bên thứ ba như thế nào?
Bạn thiết kế tài liệu kiến trúc tích hợp để người vận hành biết các đường đi và điểm khôi phục dữ liệu ra sao?
Bạn xác định chỉ số thành công cho một luồng tích hợp ngoài số request HTTP trả về 2xx như thế nào?
Bạn tổ chức cấu hình URL, port và credentials cho nhiều external service bằng Spring Boot như thế nào?
Bạn dùng @ConfigurationProperties để quản lý cấu hình adapter có nhiều tham số liên quan ra sao?
Bạn áp dụng validation cho cấu hình bắt buộc để ứng dụng không khởi động với endpoint thiếu hoặc sai như thế nào?
Bạn phân biệt cấu hình bất biến khi khởi động với cấu hình có thể cập nhật động trong một hệ thống tích hợp ra sao?
Bạn kiểm soát default timeout để một cấu hình bị thiếu không gây chờ vô hạn như thế nào?
Bạn quản lý các cấu hình riêng cho dev, staging và production mà không hardcode secret ra sao?
Bạn lựa chọn cách lưu API key, database password và broker credentials theo nguyên tắc ít quyền nhất như thế nào?
Bạn thiết kế cơ chế xoay vòng credentials mà không gián đoạn toàn bộ luồng tích hợp ra sao?
Bạn kiểm tra ứng dụng đang dùng đúng phiên bản cấu hình khi deploy nhiều replica như thế nào?
Bạn phân biệt cấu hình timeout theo client với deadline tổng thể của một nghiệp vụ ra sao?
Bạn xử lý cấu hình proxy và DNS khi một API bên ngoài chỉ truy cập được qua mạng doanh nghiệp như thế nào?
Bạn quản lý certificate truststore cho HTTP client, database và message broker theo từng môi trường ra sao?
Bạn lựa chọn các giới hạn connection pool riêng cho database, HTTP client và broker dựa trên đặc điểm tải nào?
Bạn đánh giá rủi ro bật logging toàn bộ payload tích hợp trên production ra sao?
Bạn thiết kế feature flag để chuyển traffic giữa adapter cũ và adapter mới như thế nào?
Bạn sử dụng Spring Boot profiles mà không biến một profile thành bản build riêng như thế nào?
Bạn kiểm tra điều kiện auto-configuration nào quyết định client hoặc connection factory được tạo ra sao?
Bạn xử lý xung đột bean khi có nhiều client cùng kiểu nhưng kết nối tới upstream khác nhau như thế nào?
Bạn thiết kế health indicator cho dependency bắt buộc và dependency tùy chọn theo những nguyên tắc nào?
Bạn tổ chức startup checks để chưa nhận traffic khi các kết nối quan trọng chưa sẵn sàng như thế nào?
Bạn chọn RestClient, WebClient hay RestTemplate trong một Spring Boot service dựa trên kiểu thực thi nào?
Bạn phân biệt API đồng bộ của RestClient với pipeline reactive của WebClient về cách dùng tài nguyên ra sao?
Bạn cấu hình một RestClient dùng chung cho một upstream bằng base URL và request defaults như thế nào?
Bạn tạo nhiều WebClient cho các upstream khác nhau nhưng chia sẻ tài nguyên mạng hợp lý ra sao?
Bạn phân biệt request timeout, connect timeout và response timeout trong HTTP client như thế nào?
Bạn xây dựng một request HTTP có path variable, query parameter và body tránh lỗi encoding ra sao?
Bạn xác định rủi ro truyền raw URL từ dữ liệu người dùng vào HTTP client như thế nào?
Bạn ngăn SSRF khi URL hoặc hostname của upstream phụ thuộc vào input bên ngoài ra sao?
Bạn thiết kế DTO request và response để tách API contract khỏi entity JPA như thế nào?
Bạn xử lý trường hợp upstream trả HTTP 200 nhưng body không thỏa schema mong đợi như thế nào?
Bạn phân biệt response 400, 401, 403, 404, 409, 429 và 5xx theo cơ chế xử lý client ra sao?
Bạn quản lý các header Authorization, Accept và Content-Type trong HTTP client như thế nào?
Bạn truyền trace context và correlation ID sang upstream mà không làm lộ thông tin cá nhân ra sao?
Bạn thiết kế cơ chế gắn token động vào request HTTP khi access token có thể hết hạn như thế nào?
Bạn tránh việc nhiều request đồng thời cùng refresh token bằng chiến lược đồng bộ nào?
Bạn xử lý chuyển hướng HTTP khi redirect dẫn sang một host khác với host ban đầu ra sao?
Bạn quyết định có retry request POST hay không khi không biết upstream đã xử lý trước lúc mất kết nối?
Bạn dùng idempotency key trong hợp đồng HTTP để giảm nguy cơ tạo giao dịch trùng như thế nào?
Bạn áp dụng exponential backoff, jitter và Retry-After khi upstream báo quá tải ra sao?
Bạn phân biệt retry ngay trong client với retry bằng hàng đợi tác vụ bất đồng bộ như thế nào?
Bạn giới hạn tổng số lần thử và deadline khi một tác vụ gọi nhiều upstream ra sao?
Bạn thiết kế circuit breaker cho một upstream thường xuyên timeout để giảm lỗi dây chuyền như thế nào?
Bạn phối hợp circuit breaker, rate limiter và bulkhead để bảo vệ HTTP client ra sao?
Bạn đánh giá tác động của connection pooling khi hàng nghìn request đồng thời đến cùng một host như thế nào?
Bạn chẩn đoán hiện tượng pending connection tăng nhưng CPU ứng dụng vẫn thấp bằng cách nào?
Bạn xử lý body streaming từ upstream để không giữ một file lớn hoàn toàn trong heap ra sao?
Bạn truyền cancellation và timeout qua pipeline WebClient để giải phóng công việc mạng như thế nào?
Bạn tránh gọi block trên event loop khi WebClient được dùng trong ứng dụng WebFlux ra sao?
Bạn quyết định chuyển một thư viện HTTP blocking sang scheduler riêng theo dấu hiệu nào?
Bạn kiểm thử HTTP client với mock server để xác nhận headers, status handling và retry ra sao?
Bạn xác định trường hợp nên dùng contract test với upstream thực thay vì chỉ mock response như thế nào?
Bạn thiết kế fallback trả dữ liệu cache khi upstream không sẵn sàng mà vẫn thể hiện độ mới ra sao?
Bạn thu thập metrics HTTP outbound theo destination, status và latency mà không tạo cardinality cao như thế nào?
Bạn xử lý lỗi TLS hoặc hostname verification của HTTP client khác với lỗi HTTP status ra sao?
Bạn phân biệt cách xử lý timeout do chờ connection pool với timeout khi upstream gửi response chậm như thế nào?
Bạn xác định khi nào nên gọi song song nhiều HTTP upstream và cách giới hạn fan-out ra sao?
Bạn giữ thứ tự dữ liệu khi kết hợp kết quả từ nhiều HTTP service xử lý song song như thế nào?
Bạn thiết kế adapter chuẩn hóa response của nhiều provider có schema không giống nhau ra sao?
Bạn đánh giá cơ chế pagination khi phải đồng bộ toàn bộ dữ liệu từ API bên ngoài như thế nào?
Bạn xử lý API sử dụng cursor pagination khi tập dữ liệu thay đổi trong lúc đồng bộ ra sao?
Bạn thiết kế checkpoint để tiếp tục một HTTP batch import sau khi tiến trình bị dừng giữa chừng như thế nào?
Bạn phân biệt JDBC, Spring Data JPA và R2DBC theo cách truy cập dữ liệu và khả năng non-blocking ra sao?
Bạn lựa chọn connection pool và kích thước pool JDBC dựa trên số request đồng thời như thế nào?
Bạn phát hiện database connection leak khi một adapter xử lý nhiều luồng tích hợp ra sao?
Bạn đánh giá tác động của transaction dài bao gồm gọi API bên ngoài lên tài nguyên database như thế nào?
Bạn phân biệt transaction propagation REQUIRED và REQUIRES_NEW trong một luồng tích hợp ra sao?
Vì sao lời gọi phương thức nội bộ trong cùng bean có thể khiến Spring không áp dụng @Transactional như mong đợi?
Bạn tổ chức ranh giới transaction trong service để chỉ bao bọc thao tác dữ liệu cục bộ ra sao?
Bạn giải thích tại sao transaction database không tự rollback lời gọi HTTP đã thực hiện như thế nào?
Bạn thiết kế outbox để phát sự kiện sau khi commit dữ liệu nghiệp vụ mà không làm mất message ra sao?
Bạn quyết định dùng optimistic locking hoặc pessimistic locking khi hai consumer cập nhật cùng một bản ghi ra sao?
Bạn xử lý lỗi unique constraint khi hai request cùng tạo một tài nguyên từ cùng event ID như thế nào?
Bạn dùng isolation level nào để bảo vệ những bất biến dữ liệu cần thiết mà không giảm throughput quá nhiều?
Bạn phân biệt read committed với repeatable read khi xử lý tích hợp cần đọc nhiều bước ra sao?
Bạn xử lý deadlock transaction khi nhiều consumer ghi nhiều bảng theo thứ tự khác nhau như thế nào?
Bạn thiết kế retry transaction database sau deadlock để tránh lặp lại side effect bên ngoài như thế nào?
Bạn lựa chọn batch insert hoặc batch update khi ingest dữ liệu khối lượng lớn theo tiêu chí nào?
Bạn ngăn vấn đề N+1 query khi chuẩn bị dữ liệu xuất qua API hoặc message broker như thế nào?
Bạn phân biệt entity lifecycle và transaction boundary khi mapping dữ liệu sang integration DTO ra sao?
Bạn quản lý schema migration khi producer và consumer chạy các phiên bản ứng dụng khác nhau như thế nào?
Bạn áp dụng expand-contract migration để tránh lỗi khi rollout nhiều instance ra sao?
Bạn thiết kế metadata về version và source ID để đối soát dữ liệu giữa hai cơ sở dữ liệu như thế nào?
Bạn dùng transaction template trong trường hợp cần kiểm soát thủ công một đoạn ghi dữ liệu như thế nào?
Bạn quyết định lúc nào nên tách read model khỏi write model trong một hệ thống tích hợp ra sao?
Bạn đánh giá hiệu ứng của replication lag khi một bước ghi primary rồi đọc từ replica như thế nào?
Bạn thiết kế xử lý lỗi transient database theo giới hạn retry phù hợp như thế nào?
Bạn quản lý dữ liệu staging trước khi merge vào bảng chính để chống nhập dữ liệu không hợp lệ ra sao?
Bạn xử lý một batch nhập 10.000 dòng khi chỉ vài dòng lỗi schema bằng chính sách nào?
Bạn đối soát số bản ghi nguồn, đích và những bản ghi bị từ chối sau job tích hợp như thế nào?
Bạn phân biệt watermark theo thời gian và cursor theo ID trong đồng bộ tăng dần ra sao?
Bạn xử lý bản ghi đến muộn hoặc cập nhật trễ khi dùng updated_at làm checkpoint như thế nào?
Bạn xây dựng quy tắc giải quyết xung đột khi hai hệ thống cùng cập nhật một đối tượng ra sao?
Bạn lựa chọn mô hình cache-aside hay write-through cho dữ liệu được nhiều adapter dùng chung theo tiêu chí nào?
Bạn phân biệt cache là bản sao tăng tốc với kho dữ liệu chuẩn phải được cập nhật bền vững ra sao?
Bạn dùng Spring Cache abstraction để tách logic cache khỏi provider cụ thể như thế nào?
Bạn xác định khi nào cache local đủ dùng và khi nào cần cache phân tán như Redis ra sao?
Bạn lựa chọn key cache có tenant, version và tham số truy vấn để tránh trả nhầm dữ liệu như thế nào?
Bạn đánh giá thời hạn TTL phù hợp theo mức độ thay đổi của từng loại dữ liệu tích hợp ra sao?
Bạn thiết kế cache invalidation sau khi transaction database commit thành công như thế nào?
Bạn xử lý cache stale khi sự kiện invalidation đến chậm hoặc bị mất ra sao?
Bạn đánh giá rủi ro cache stampede khi một key phổ biến cùng hết hạn trên nhiều replica như thế nào?
Bạn sử dụng cache warming, TTL jitter hoặc single-flight để giảm tải backend ra sao?
Bạn thiết kế fallback khi Redis không sẵn sàng mà không làm sập API chính như thế nào?
Bạn phân biệt cache hit rate cao với dữ liệu cache thực sự đúng và còn mới như thế nào?
Bạn áp dụng negative caching cho kết quả không tìm thấy và chọn TTL theo yếu tố nào?
Bạn xác định nguy cơ lưu token hoặc thông tin nhạy cảm trong cache dùng chung như thế nào?
Bạn quyết định có cache một HTTP response đã được cá nhân hóa dựa trên chính sách nào?
Bạn quản lý thay đổi cấu trúc dữ liệu JSON trong Redis giữa hai bản phát hành Spring Boot ra sao?
Bạn xử lý lỗi deserialize cache entry được tạo bởi phiên bản ứng dụng cũ như thế nào?
Bạn tránh cache penetration khi client liên tục truy vấn key không tồn tại bằng biện pháp nào?
Bạn thiết kế consistency giữa database, cache và message event khi một giao dịch cập nhật tài khoản ra sao?
Bạn kiểm thử race condition giữa đọc cache miss và một giao dịch đồng thời cập nhật dữ liệu như thế nào?
Bạn lựa chọn RabbitMQ hoặc Kafka thay vì HTTP cho một luồng tích hợp dựa trên những tiêu chí nào?
Bạn phân biệt command message và domain event khi thiết kế consumer contract ra sao?
Bạn chọn RabbitTemplate, KafkaTemplate hoặc abstraction phù hợp dựa trên broker và mô hình delivery nào?
Bạn thiết kế sự kiện có event ID, schema version, timestamp và business key để hỗ trợ xử lý ra sao?
Bạn đánh giá rủi ro gửi nguyên entity JPA trong message thay vì DTO ổn định như thế nào?
Bạn lựa chọn JSON, Avro hoặc Protobuf dựa trên yêu cầu tương thích và hiệu năng trao đổi dữ liệu giữa các service như thế nào?
Bạn thiết kế tương thích xuôi và ngược khi producer bổ sung trường mới vào message như thế nào?
Bạn xử lý consumer không nhận biết enum value hoặc event type mới ra sao?
Bạn phân biệt producer acknowledgment với consumer acknowledgment trong broker như thế nào?
Bạn lựa chọn acknowledge sau commit nghiệp vụ để giảm nguy cơ mất hoặc xử lý lặp message ra sao?
Bạn đánh giá hành vi at-least-once delivery và redelivery khi worker chết giữa xử lý như thế nào?
Bạn thiết kế inbox table để chặn xử lý lặp cùng event ID như thế nào?
Bạn xác định cách đặt idempotency marker trong cùng transaction với tác dụng phụ database ra sao?
Bạn xử lý hai consumer nhận cùng sự kiện gần đồng thời mà cả hai cùng kiểm tra chưa xử lý ra sao?
Bạn phân biệt retry cục bộ trong listener với delayed retry qua queue hoặc topic riêng như thế nào?
Bạn lựa chọn backoff, jitter và số lần retry cho lỗi downstream tạm thời như thế nào?
Bạn chuyển message lỗi không khôi phục được sang dead-letter destination và lưu metadata điều tra ra sao?
Bạn ngăn poison message bị requeue vô hạn làm tắc queue như thế nào?
Bạn xây dựng quy trình replay DLQ để tránh xử lý lại các event đã hoàn tất ra sao?
Bạn phân biệt ordering ở broker với thứ tự commit của nhiều consumer song song như thế nào?
Bạn giữ thứ tự xử lý theo aggregate ID trong khi cần scale consumer theo tiêu chí nào?
Bạn thiết kế xử lý out-of-order event dùng sequence hoặc version thay vì giả định thứ tự giao hàng ra sao?
Bạn đánh giá broker backlog tăng vì downstream chậm bằng những metrics nào?
Bạn quyết định tăng consumer concurrency hay điều tiết producer theo tài nguyên downstream như thế nào?
Bạn phối hợp Kafka consumer offset commit với transaction database khi không có atomic transaction chung ra sao?
Bạn xác định nguy cơ retry publish sau timeout tạo bản sao message như thế nào?
Bạn áp dụng transactional outbox cho luồng ghi DB và gửi message theo các bước nào?
Bạn dùng CDC đọc outbox để phát sự kiện và kiểm soát việc phát trùng như thế nào?
Bạn đánh giá chi phí lưu trữ và cơ chế dọn dẹp inbox/outbox khi hệ thống hoạt động lâu dài ra sao?
Bạn thiết kế correlation ID trong message headers để theo dõi một quy trình nhiều bước ra sao?
Bạn giới hạn payload size, số pending message và concurrency để tránh làm cạn bộ nhớ broker như thế nào?
Bạn xử lý yêu cầu dừng service khi còn message đang unacked và transaction chưa hoàn tất ra sao?
Bạn thực hiện contract test giữa producer và consumer để phát hiện thay đổi schema không tương thích như thế nào?
Spring Integration bổ sung những cơ chế điều phối message nào so với cách gọi trực tiếp service hoặc broker client?
Bạn mô tả các vai trò Message, MessageHeaders, MessageChannel và MessageHandler trong Spring Integration ra sao?
Bạn phân biệt payload và headers khi đưa dữ liệu qua Spring Integration flow như thế nào?
Bạn thiết kế IntegrationFlow mô tả các bước nhận, chuyển đổi và gửi message theo cách nào?
Bạn lựa chọn Java DSL hoặc annotation-driven endpoints dựa trên độ phức tạp luồng ra sao?
Bạn phân biệt DirectChannel, ExecutorChannel và QueueChannel về cách dispatch và thread model như thế nào?
Bạn đánh giá hệ quả transaction khi message đi qua DirectChannel so với ExecutorChannel ra sao?
Bạn chọn PublishSubscribeChannel khi một sự kiện cần nhiều subscriber nhận độc lập như thế nào?
Bạn phân biệt round-robin giữa nhiều consumer với publish-subscribe trong routing message ra sao?
Bạn sử dụng FluxMessageChannel trong trường hợp cần tích hợp reactive stream theo điều kiện nào?
Bạn quyết định kênh nào cần buffer và kênh nào phải giới hạn năng lực nhận message như thế nào?
Bạn tránh queue nội bộ tăng vô hạn khi producer nhanh hơn handler xử lý ra sao?
Bạn sử dụng @MessagingGateway để expose một luồng messaging như API có kiểu dữ liệu như thế nào?
Bạn phân biệt gateway request-reply với one-way event channel về kỳ vọng hoàn tất ra sao?
Bạn thiết kế reply channel và error channel cho một gateway có timeout như thế nào?
Bạn xác định cách xây dựng transformer để chuyển đổi schema giữa hai service như thế nào?
Bạn phân biệt @Transformer và @ServiceActivator theo trách nhiệm của một thành phần xử lý ra sao?
Bạn dùng router theo header hoặc giá trị payload để chọn nhánh xử lý như thế nào?
Bạn quyết định khi nào dùng Filter thay cho Router để chặn hoặc chuyển message ra sao?
Bạn thiết kế splitter chia một payload thành nhiều message và lưu correlation metadata như thế nào?
Bạn xây dựng aggregator gom các message con và xác định điều kiện hoàn tất ra sao?
Bạn xử lý aggregator nhận thiếu một phần dữ liệu sau deadline bằng chiến lược nào?
Bạn kiểm soát memory và message store của aggregator khi luồng tích hợp có nhiều nhóm tồn đọng ra sao?
Bạn thiết kế resequencer để xử lý message đến sai thứ tự mà không chờ vô hạn như thế nào?
Bạn lựa chọn persistent MessageStore cho các bước cần chịu được restart dựa trên đặc điểm nào?
Bạn phân biệt poller và event-driven endpoint khi kết nối nguồn có hoặc không hỗ trợ push ra sao?
Bạn lựa chọn fixed delay, fixed rate và maxMessagesPerPoll của poller theo tốc độ dữ liệu và năng lực xử lý ra sao?
Bạn ngăn một poller chạy đè lần xử lý trước khi job tích hợp quá lâu như thế nào?
Bạn phân biệt inbound channel adapter, outbound channel adapter và outbound gateway trong Spring Integration ra sao?
Bạn dùng HTTP outbound gateway khi phải gọi dịch vụ và chờ kết quả như thế nào?
Bạn thiết kế HTTP inbound gateway để ánh xạ request bên ngoài sang Spring Integration message ra sao?
Bạn cân nhắc file inbound adapter khi phát hiện và xử lý file mới từ thư mục dùng chung như thế nào?
Bạn quản lý file rename, write-in-progress và polling để không đọc file chưa hoàn tất ra sao?
Bạn dùng SFTP inbound adapter đồng bộ file và lưu dấu các file đã xử lý ra sao?
Bạn xác định cơ chế local filter và remote filter để tránh tải lại file SFTP trùng như thế nào?
Bạn xử lý file lớn qua Spring Integration mà không giữ toàn bộ nội dung trong heap ra sao?
Bạn dùng JDBC inbound adapter hoặc polling query khi nguồn chỉ cho phép đọc từ database ra sao?
Bạn quản lý watermark khi JDBC polling lấy bản ghi mới nhưng các bản ghi cũ còn cập nhật ra sao?
Bạn thiết kế AMQP hoặc Kafka inbound endpoint trong IntegrationFlow để giao việc cho handler ra sao?
Bạn kết nối các adapter khác nhau bằng channel và transformer mà không làm rò schema giữa bước ra sao?
Bạn quyết định dùng Spring Integration flow hay Spring Batch cho một pipeline có state và checkpoint lớn theo tiêu chí nào?
Bạn phân biệt errorChannel với exception propagation qua synchronous DirectChannel như thế nào?
Bạn cấu hình ErrorMessage handler để phân loại và ghi nhận lỗi từng bước tích hợp ra sao?
Bạn ngăn một lỗi trong subscriber làm ảnh hưởng đến các subscriber khác của publish-subscribe như thế nào?
Bạn thiết kế retry advice cho một endpoint Spring Integration mà không tạo lặp side effect ra sao?
Bạn xây dựng idempotent receiver với metadata store để chặn message trùng như thế nào?
Bạn xác định tác động của persistent MetadataStore đối với nhiều instance chia nhau xử lý ra sao?
Bạn đánh giá transaction synchronization khi poller lấy dữ liệu và cập nhật dấu đã xử lý như thế nào?
Bạn sử dụng control bus để quản lý endpoint động và giới hạn quyền điều khiển ra sao?
Bạn theo dõi trạng thái channel, handler và IntegrationFlow qua những metrics nào?
Bạn kiểm thử IntegrationFlow tách adapter I/O thật khỏi transformer và router bằng cách nào?
Bạn lựa chọn kỹ thuật dùng test channel hoặc mock endpoint để kiểm tra routing không cần hệ thống ngoài ra sao?
Bạn thiết kế contract message rõ ràng gồm schema, version, id, timestamps và quy tắc tương thích như thế nào?
Bạn phân biệt hợp đồng đồng bộ REST với hợp đồng sự kiện bất đồng bộ về xử lý lỗi ra sao?
Bạn lựa chọn JSON schema hoặc OpenAPI cho HTTP payload và AsyncAPI cho message contract theo yêu cầu nào?
Bạn xử lý thêm field tùy chọn để consumer cũ vẫn hoạt động mà không đổi đồng thời nhiều service ra sao?
Bạn đánh giá hậu quả đổi tên field hoặc đổi kiểu dữ liệu khi hai phiên bản tích hợp cùng tồn tại như thế nào?
Bạn tổ chức schema registry hoặc repository hợp đồng để kiểm soát thay đổi theo nhóm như thế nào?
Bạn thiết kế mapping ở adapter để tránh truyền enum hoặc identifier nội bộ sang bên ngoài ra sao?
Bạn quản lý timezone và định dạng ngày giờ khi dữ liệu đi qua nhiều hệ thống như thế nào?
Bạn lựa chọn precision và rounding khi trao đổi số tiền qua JSON, database và message như thế nào?
Bạn phân biệt null, missing và giá trị mặc định khi merge dữ liệu từ nhiều provider ra sao?
Bạn chuẩn hóa lỗi từ upstream thành error model nhất quán cho consumer nội bộ như thế nào?
Bạn xử lý thông báo lỗi từ provider có chứa dữ liệu nhạy cảm trước khi lưu log ra sao?
Bạn lựa chọn cơ chế version API hoặc event phù hợp với vòng đời consumer ra sao?
Bạn thiết kế correlation và causation ID để truy ngược chuỗi sự kiện từ một thay đổi nghiệp vụ như thế nào?
Bạn xây dựng contract test để phát hiện producer thay đổi field bắt buộc trước khi rollout ra sao?
Bạn quản lý khả năng tương thích dữ liệu khi thực hiện blue-green deployment nhiều phiên bản adapter như thế nào?
Bạn quyết định giữ bản sao raw payload để debug trong bao lâu theo quy định dữ liệu nào?
Bạn xử lý biến đổi các định danh bên ngoài sang business ID nội bộ mà không tạo collision như thế nào?
Bạn xây dựng cách đối soát checksum hoặc record count sau khi chuyển đổi dữ liệu như thế nào?
Bạn xác định điều kiện một bước tích hợp cần transaction và các điểm transaction kết thúc ra sao?
Bạn phân biệt ACID transaction của một database với tính nhất quán xuyên HTTP và broker như thế nào?
Vì sao @Transactional không thể tự rollback tác dụng phụ của một request HTTP đã thực thi thành công?
Bạn thiết kế saga gồm các bước và thao tác bù trừ cho một đơn hàng đa dịch vụ như thế nào?
Bạn lựa chọn orchestration saga hay choreography dựa trên mức độ phức tạp luồng ra sao?
Bạn xử lý một bước đã thành công nhưng thao tác compensation thất bại như thế nào?
Bạn lưu trạng thái tiến trình tích hợp để có thể tiếp tục sau crash hoặc redeploy ra sao?
Bạn quyết định checkpoint theo record, batch hay message tùy độ lớn tác vụ như thế nào?
Bạn thiết kế inbox/outbox để ngăn mất event và giảm duplicate side effect như thế nào?
Bạn phân biệt idempotency của một endpoint với deduplication của một consumer ra sao?
Bạn đặt khóa idempotency theo request ID, event ID hay business key dựa trên yêu cầu nào?
Bạn lưu kết quả của lần xử lý đầu tiên để trả lại khi cùng idempotency key được gửi lần nữa ra sao?
Bạn xử lý hai request cùng idempotency key chạy đồng thời bằng transaction hoặc lock như thế nào?
Bạn thiết kế replay một công việc quá hạn mà không áp dụng lại side effect không thể đảo ngược ra sao?
Bạn xác định các side effect nào cần thao tác bù trừ thay vì retry mù quáng như thế nào?
Bạn quản lý version của trạng thái tích hợp để sự kiện đến muộn không ghi đè bản mới ra sao?
Bạn phân biệt duplicate delivery, retry và replay có chủ đích khi đo số lần xử lý ra sao?
Bạn thiết kế timeout tổng thể cho saga kéo dài nhiều phút mà vẫn theo dõi từng bước ra sao?
Bạn xử lý trạng thái không chắc chắn khi downstream đã xử lý request nhưng client gặp timeout ra sao?
Bạn lựa chọn lưu audit trail và trạng thái cuối cùng cho các tác vụ không thể khôi phục theo tiêu chí nào?
Bạn áp dụng retry có giới hạn và jitter để tránh khuếch đại tải từ một dependency đang gặp sự cố như thế nào?
Bạn phân biệt retryable với non-retryable errors qua HTTP, database và broker ra sao?
Bạn xây dựng circuit breaker riêng cho từng upstream để giảm nguy cơ lan truyền lỗi như thế nào?
Bạn lựa chọn bulkhead giới hạn thread, connection hoặc concurrency theo dạng tải nào?
Bạn phân biệt giới hạn số request đồng thời với rate limiting theo thời gian ra sao?
Bạn tổ chức deadline propagation khi một API gọi hai HTTP service rồi ghi database như thế nào?
Bạn xử lý fallback sang dữ liệu cũ khi cache hoặc external service lỗi nhưng nghiệp vụ vẫn cần phản hồi ra sao?
Bạn đánh giá tính an toàn của fallback khi dữ liệu liên quan tài chính hoặc phân quyền như thế nào?
Bạn kiểm soát độ dài hàng đợi nội bộ và policy reject khi lượng tác vụ đến vượt khả năng xử lý ra sao?
Bạn sử dụng backpressure trong luồng reactive khi consumer xử lý chậm hơn producer như thế nào?
Bạn xử lý overload khi một nguồn webhook gửi burst lớn hơn giới hạn downstream ra sao?
Bạn thiết kế dead-letter workflow có thể quan sát và replay thay vì mất tác vụ khó truy vết ra sao?
Bạn đánh giá khả năng chịu lỗi khi một upstream trả response chậm ngẫu nhiên và tỷ lệ 5xx tăng ra sao?
Bạn chọn chính sách fail-fast hay tiếp tục với dữ liệu từng phần theo rủi ro nghiệp vụ nào?
Bạn tách timeout của connection pool khỏi timeout nghiệp vụ để chẩn đoán đúng bottleneck ra sao?
Bạn thiết kế cơ chế giới hạn fan-out khi một user request dẫn đến hàng chục lời gọi downstream như thế nào?
Bạn áp dụng adaptive concurrency hoặc load shedding trong hệ thống nhiều dependency như thế nào?
Bạn xác định trạng thái readiness cần phản ánh dependency nào và không nên phụ thuộc vào dependency nào ra sao?
Bạn xây dựng metric theo từng adapter cho throughput, p95/p99 latency, error rate và retry counts ra sao?
Bạn dùng Micrometer Observation để quan sát toàn bộ luồng tích hợp nhiều bước như thế nào?
Bạn truyền trace context từ HTTP inbound qua WebClient đến message broker như thế nào?
Bạn phân biệt trace ID, correlation ID và business transaction ID trong báo cáo sự cố ra sao?
Bạn chuẩn hóa logging lỗi để vẫn theo dấu request nhưng không ghi credentials và payload nhạy cảm ra sao?
Bạn giới hạn metric tags để không tạo series cho từng order ID hoặc user ID như thế nào?
Bạn theo dõi HTTP outbound connection pool và database pool để phát hiện thiếu tài nguyên như thế nào?
Bạn giám sát broker ready/unacked messages hoặc consumer lag để dự báo backlog ra sao?
Bạn thiết kế dashboard đối chiếu thành công nghiệp vụ với tỷ lệ trả HTTP 2xx như thế nào?
Bạn xác định alert phù hợp cho tỷ lệ dead-letter, retry storm và sự cố đồng bộ dữ liệu như thế nào?
Bạn thu thập audit event cho quyền truy cập adapter và thao tác replay lỗi theo nguyên tắc nào?
Bạn cấu hình health indicator tùy chỉnh để phân biệt dependency thiết yếu và không thiết yếu ra sao?
Bạn kiểm tra một tác vụ đồng bộ bị chậm đang kẹt ở polling, transformation hay downstream bằng cách nào?
Bạn thiết kế log có record count và checkpoint để biết job đã xử lý đến đâu như thế nào?
Bạn hạn chế thông tin PII trong traces, error reports và dead-letter payload bằng biện pháp nào?
Bạn đo freshness của dữ liệu cache và dữ liệu đồng bộ bằng lag metric như thế nào?
Bạn đặt SLO cho một luồng sự kiện từ lúc phát sinh đến khi dữ liệu có mặt ở hệ thống đích ra sao?
Bạn xác định cách phân loại lỗi theo hệ thống nguồn, biến đổi hay hệ thống đích trong báo cáo vận hành như thế nào?
Bạn quản lý quyền truy cập HTTP API, database, cache và broker bằng service identity nào?
Bạn sử dụng OAuth2 client credentials để gọi upstream API an toàn như thế nào?
Bạn xác minh TLS certificate và hostname của downstream mà không tắt security checks ra sao?
Bạn ngăn SSRF khi một workflow xử lý URL do message hoặc webhook mang tới như thế nào?
Bạn kiểm tra webhook signature và chống replay attack trước khi đưa sự kiện vào pipeline ra sao?
Bạn phân biệt xác thực người gửi sự kiện với phân quyền thực hiện hành động nghiệp vụ như thế nào?
Bạn quản lý multi-tenancy trong cache keys, HTTP headers và message metadata để tránh trộn dữ liệu ra sao?
Bạn xác định lúc nào nên mã hóa trường dữ liệu nhạy cảm ở payload thay vì chỉ dựa vào TLS như thế nào?
Bạn thực hiện secret rotation cho nhiều adapter mà không phải dừng toàn bộ service ra sao?
Bạn thiết kế quyền read/write của broker và database theo nguyên tắc ít quyền nhất ra sao?
Bạn xây dựng unit test cho adapter HTTP bằng mock server để kiểm response 4xx, 5xx và timeout như thế nào?
Bạn sử dụng Testcontainers để kiểm thử kết nối database, Redis và broker trong Spring Boot như thế nào?
Bạn xác định phạm vi của @SpringBootTest so với slice tests khi kiểm thử luồng tích hợp ra sao?
Bạn kiểm thử transaction rollback khi một bước ghi database thất bại mà không cần thực hiện external side effect như thế nào?
Bạn xây dựng integration test cho outbox dispatcher và inbox deduplication qua nhiều lần retry ra sao?
Bạn kiểm thử contract HTTP và JSON giữa hai phiên bản service bằng cách nào?
Bạn tạo test cho IntegrationFlow để kiểm tra transformer, router và aggregator với message mẫu như thế nào?
Bạn mô phỏng message giao lại hai lần để xác minh kết quả nghiệp vụ chỉ được ghi một lần ra sao?
Bạn mô phỏng network partition khi provider phản hồi muộn để đánh giá deadline và retry ra sao?
Bạn kiểm thử TTL, cache invalidation và tình huống cache stale sau commit dữ liệu như thế nào?
Bạn giả lập broker mất kết nối sau khi database commit nhưng trước publisher confirm như thế nào?
Bạn kiểm thử DLQ replay có kiểm soát bằng event ID và trạng thái xử lý như thế nào?
Bạn đánh giá performance khi tăng đồng thời HTTP calls, DB transactions và broker publishes ra sao?
Bạn kiểm tra giao dịch đọc dữ liệu từ replica không phản ánh ngay bản ghi mới commit bằng test nào?
Bạn thiết kế fault injection cho timeout API, deadlock database và broker restart trong cùng kịch bản như thế nào?
Bạn so sánh kết quả contract tests và end-to-end tests để giảm các lỗi tích hợp lọt vào production ra sao?
Bạn xác định dữ liệu test nào phải được ẩn danh trước khi đưa vào môi trường kiểm thử tích hợp như thế nào?
Bạn đặt tiêu chí pass/fail cho một adapter mới dựa trên correctness, latency, security và khả năng replay ra sao?
Nếu một endpoint trả 200 nhưng event không được publish, bạn sẽ lần theo transaction, outbox và broker ở đâu?
Nếu upstream HTTP trả 429 kéo dài, bạn sẽ điều chỉnh rate limit, retry và queue như thế nào?
Nếu consumer cập nhật database hai lần cho cùng event ID, bạn sẽ kiểm tra inbox và transaction ra sao?
Nếu một service trả dữ liệu cũ dù database đã cập nhật, bạn sẽ kiểm tra cache key và invalidation như thế nào?
Nếu HTTP client thường xuyên timeout nhưng connection pool đã hết chỗ, bạn sẽ điều tra nguyên nhân nào trước?
Nếu một IntegrationFlow chặn nhiều luồng khác vì handler chạy lâu trên DirectChannel, bạn sẽ tái cấu trúc channel như thế nào?
Nếu aggregator liên tục thiếu một số message con, bạn sẽ kiểm tra correlation ID, release strategy và timeout ra sao?
Nếu poller đọc cùng file nhiều lần sau restart, bạn sẽ thiết kế persistent metadata store và idempotency như thế nào?
Nếu SFTP inbound adapter tải file đang được ghi dở, bạn sẽ bổ sung cơ chế sẵn sàng và lọc file ra sao?
Nếu một batch đồng bộ cập nhật 70 phần trăm rồi bị lỗi, bạn sẽ quyết định resume, rollback hay bù trừ thế nào?
Nếu API trả lỗi sau khi hệ thống đích đã tạo đơn hàng, bạn sẽ xử lý trạng thái không chắc chắn để tránh tạo trùng ra sao?
Nếu hai bản release dùng schema message khác nhau, bạn sẽ kiểm chứng tương thích và triển khai theo thứ tự nào?
Nếu broker backlog tăng dù số listener đã tăng, bạn sẽ tìm bottleneck database hay external API bằng cách nào?
Nếu một tenant nhận dữ liệu của tenant khác, bạn sẽ truy nguyên tenant context qua HTTP, cache và message như thế nào?
Nếu Redis outage làm lượng request database tăng đột biến, bạn sẽ giảm tải và phục hồi theo thứ tự nào?
Nếu transaction giữ lock quá lâu vì gọi API ngoài, bạn sẽ thay đổi boundary và cơ chế giao tiếp ra sao?
Nếu Saga đã hoàn thành hai bước nhưng bước thứ ba thất bại, bạn sẽ điều phối compensation và ghi trạng thái như thế nào?
Nếu hệ thống báo readiness DOWN vì cache tùy chọn bị lỗi, bạn sẽ điều chỉnh health group như thế nào?
Nếu trace chỉ xuất hiện ở HTTP inbound mà mất ở broker consumer, bạn sẽ kiểm tra propagation và instrumentation ra sao?
Nếu một adapter gửi payload có PII vào log và DLQ, bạn sẽ xử lý sự cố và thay đổi chính sách ghi nhận như thế nào?
Nếu service mất kết nối database, cache và broker cùng lúc, bạn sẽ lập runbook giảm ảnh hưởng và khôi phục như thế nào?
