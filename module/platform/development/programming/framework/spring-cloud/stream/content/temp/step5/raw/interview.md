Bạn giải thích Spring Cloud Stream giúp tách mã xử lý sự kiện khỏi chi tiết của message broker như thế nào?
Bạn phân biệt Spring Cloud Stream với Spring for Apache Kafka và Spring AMQP theo mức độ trừu tượng và khả năng cấu hình ra sao?
Bạn mô tả đường đi của một message từ broker qua input binding đến hàm xử lý rồi tới output binding như thế nào?
Bạn xác định những trường hợp nào nên dùng xử lý sự kiện thay vì gọi API đồng bộ trong kiến trúc microservices ra sao?
Bạn giải thích mối quan hệ giữa Spring Cloud Function và mô hình lập trình hàm của Spring Cloud Stream như thế nào?
Bạn phân biệt vai trò của Supplier, Function và Consumer khi thiết kế nguồn phát, biến đổi và xử lý kết thúc một luồng sự kiện ra sao?
Bạn thiết kế một ứng dụng nhận sự kiện đơn hàng, chuẩn hóa dữ liệu và phát sự kiện đã xử lý bằng Function như thế nào?
Bạn lựa chọn Consumer khi chỉ cần ghi dữ liệu hoặc tạo side effect mà không xuất thêm một message như thế nào?
Bạn mô tả cách Spring Cloud Stream kích hoạt Supplier để phát message và cấu hình chu kỳ phát phù hợp như thế nào?
Bạn phân biệt Supplier tạo message theo cơ chế polling với Supplier cung cấp một nguồn reactive liên tục như thế nào?
Bạn quyết định khi nào nên sử dụng Function trả về Publisher thay vì xử lý từng payload một cách đồng bộ như thế nào?
Bạn giải thích vì sao các side effect trong hàm xử lý cần được thiết kế phù hợp với khả năng message bị giao lại như thế nào?
Bạn tổ chức các hàm xử lý nghiệp vụ thành bean độc lập để có thể kiểm thử không cần broker ra sao?
Bạn phân biệt xử lý dữ liệu bằng payload đơn thuần với nhận đối tượng Message để sử dụng headers như thế nào?
Bạn xác định khi nào cần trả về Message có headers tùy biến thay vì chỉ trả payload từ Function ra sao?
Bạn thiết kế luồng xử lý sự kiện với nhiều chức năng nhỏ mà không để logic nghiệp vụ phụ thuộc tên destination của broker như thế nào?
Bạn giải thích spring.cloud.function.definition được dùng để chọn hàm nào trong số nhiều bean ứng dụng ra sao?
Bạn mô tả quy ước tên binding đầu vào và đầu ra của một Function có một input và một output như thế nào?
Bạn xác định tên binding cho Supplier và Consumer để cấu hình destination mà không cần đổi tên bean như thế nào?
Bạn phân biệt binding name với destination name và consumer group trong cấu hình Spring Cloud Stream ra sao?
Bạn thiết kế cấu hình để một Function đọc từ topic orders-in và ghi sang topic orders-validated theo nguyên tắc nào?
Bạn giải thích tác động khi ứng dụng định nghĩa nhiều Function nhưng không chọn rõ hàm cần bind như thế nào?
Bạn phân biệt việc kết hợp các function bằng composition với việc nối nhiều dịch vụ độc lập qua broker theo trade-off nào?
Bạn kiểm thử thứ tự biến đổi dữ liệu khi cấu hình một chuỗi function composition bằng cách nào?
Bạn xác định hạn chế cần kiểm tra khi một function có nhiều input hoặc nhiều output và binder hỗ trợ khác nhau như thế nào?
Bạn thiết kế quy ước tên binding có ý nghĩa nghiệp vụ để tránh nhầm lẫn khi refactor tên function như thế nào?
Bạn tổ chức file cấu hình cho nhiều input binding mà mỗi binding cần destination, group và chính sách xử lý lỗi khác nhau ra sao?
Bạn giải thích vai trò của binder trong việc nối các binding logic của ứng dụng tới Kafka, RabbitMQ hoặc Pulsar như thế nào?
Bạn phân biệt cấu hình chung của Spring Cloud Stream với cấu hình đặc thù của từng binder để giảm phụ thuộc broker ra sao?
Bạn xác định tiêu chí chọn Kafka, RabbitMQ hoặc Pulsar theo nhu cầu lưu trữ sự kiện, phân phối và xử lý lại như thế nào?
Bạn cấu hình binder mặc định khi ứng dụng chỉ có một hệ thống messaging và cách xử lý khi có nhiều binder như thế nào?
Bạn thiết kế ánh xạ từng binding tới binder tương ứng khi cùng một ứng dụng kết nối hai nền tảng messaging ra sao?
Bạn phân tích rủi ro khi cùng một Function đọc từ Kafka nhưng gửi sang RabbitMQ và chỉ một phía hoàn thành như thế nào?
Bạn xác định khả năng nào thuộc giao thức hoặc broker nên được kiểm tra trước khi chuyển một ứng dụng sang binder khác ra sao?
Bạn kiểm tra lỗi cấu hình destination hoặc binder name khiến ứng dụng khởi động được nhưng không nhận được message bằng cách nào?
Bạn giải thích cách StreamBridge hỗ trợ gửi message động từ một thành phần không phải Supplier hoặc Function như thế nào?
Bạn quyết định khi nào sử dụng StreamBridge thay vì khai báo Supplier để phát message trong ứng dụng như thế nào?
Bạn xử lý rủi ro số lượng dynamic bindings tăng không kiểm soát khi tên destination được tạo từ dữ liệu người dùng ra sao?
Bạn thiết kế quy tắc gửi message bằng StreamBridge và kiểm tra kết quả gửi hoặc lỗi bất đồng bộ theo khả năng binder như thế nào?
Bạn phân biệt việc ứng dụng tự tạo destination với việc hạ tầng yêu cầu topic hoặc exchange phải được cấp trước như thế nào?
Bạn mô tả vai trò của contentType trong chuyển đổi payload giữa byte array, JSON và object Java như thế nào?
Bạn xác định khi nào framework chuyển đổi payload theo kiểu tham số của Function và khi nào cần cấu hình converter rõ ràng ra sao?
Bạn thiết kế một message schema có version để các consumer khác ngôn ngữ vẫn có thể giải mã như thế nào?
Bạn phân biệt envelope chứa event ID, event type và timestamp với nội dung nghiệp vụ của payload ra sao?
Bạn lựa chọn header nào nên truyền qua broker và thông tin nào cần đưa vào payload để duy trì khả năng tương thích ra sao?
Bạn kiểm tra sự khác biệt giữa tên header trong Spring Message và metadata native của broker khi chuyển binder như thế nào?
Bạn thiết kế message conversion cho JSON có trường tùy chọn, số lớn và thời gian có timezone như thế nào?
Bạn xử lý payload không giải mã được trước khi vào Function và xác định vị trí ghi nhận lỗi ra sao?
Bạn quyết định khi nào dùng Avro hoặc Protobuf cùng schema registry thay vì chỉ JSON tự mô tả theo tiêu chí nào?
Bạn phân tích trường hợp producer thêm một trường mới và consumer cũ vẫn chạy được hay thất bại tùy chiến lược schema evolution như thế nào?
Bạn xác định quy tắc backward, forward và full compatibility khi nhiều phiên bản producer và consumer cùng hoạt động như thế nào?
Bạn kiểm thử một thay đổi schema làm trường đang tùy chọn thành bắt buộc bằng những phiên bản message nào?
Bạn xử lý message cũ thiếu trường sau khi nâng cấp DTO nhưng vẫn cần phát lại dữ liệu lịch sử ra sao?
Bạn thiết kế contract test cho event để xác minh kiểu dữ liệu, header bắt buộc và ngữ nghĩa trường giữa hai dịch vụ như thế nào?
Bạn giải thích tại sao contentType hoặc serializer không khớp có thể tạo lỗi trước khi logic nghiệp vụ được gọi ra sao?
Bạn đánh giá những dữ liệu nhạy cảm nào không nên đưa vào message headers, payload hoặc log chẩn đoán ra sao?
Bạn phân biệt broadcast đến mọi nhóm consumer với chia tải giữa các instance thuộc cùng một consumer group như thế nào?
Bạn giải thích consumer group ảnh hưởng đến khả năng mở rộng số instance và khả năng nhận mỗi sự kiện ra sao?
Bạn xác định hệ quả khi một consumer binding không cấu hình group ổn định và ứng dụng được khởi động lại như thế nào?
Bạn thiết kế tên consumer group cho các ứng dụng billing, notification và analytics cùng đọc sự kiện đơn hàng như thế nào?
Bạn kiểm tra trường hợp hai ứng dụng vô tình dùng chung consumer group nên một bên không nhận đủ sự kiện như thế nào?
Bạn phân biệt việc thêm replica trong cùng group với thêm một group mới khi cần xử lý lại toàn bộ luồng sự kiện ra sao?
Bạn đánh giá mức độ song song tối đa của một Kafka consumer group khi topic có số partition giới hạn như thế nào?
Bạn giải thích việc tăng concurrency của consumer có tạo thêm khả năng xử lý hay chỉ làm dư consumer không có partition ra sao?
Bạn thiết kế partition key để các sự kiện cùng order ID được gửi vào cùng partition khi cần giữ thứ tự xử lý như thế nào?
Bạn phân biệt thứ tự được bảo đảm trong một partition với thứ tự toàn topic hoặc giữa các consumer groups ra sao?
Bạn chọn partition key theo tenant ID hay entity ID để cân bằng yêu cầu thứ tự và phân bố tải như thế nào?
Bạn phát hiện hot partition khi một vài key chiếm phần lớn lưu lượng bằng những metric nào?
Bạn xử lý khi số lượng partition thay đổi làm ánh xạ key tới partition và thứ tự tương đối của một entity có thể bị ảnh hưởng ra sao?
Bạn thiết kế chiến lược phân vùng đầu ra của producer để consumer luôn nhận được routing key nghiệp vụ cần thiết như thế nào?
Bạn phân biệt partitioning ở mức Spring Cloud Stream với đặc tính partition hoặc routing của Kafka và RabbitMQ ra sao?
Bạn xác định giới hạn về ordering khi xử lý bất đồng bộ nhiều message cùng partition và cách bảo vệ tính nhất quán như thế nào?
Bạn xử lý duplicate event bằng event ID và bảng idempotency sao cho một giao dịch không bị ghi hai lần ra sao?
Bạn mô tả các tình huống gây giao nhận ít nhất một lần khiến consumer thấy message lặp dù producer chỉ gửi một lần như thế nào?
Bạn phân biệt at-most-once, at-least-once và exactly-once theo việc mất, lặp và xử lý side effect như thế nào?
Bạn lý giải vì sao một ứng dụng dùng Kafka transaction vẫn không tự bảo đảm exactly-once cho thao tác ghi database ngoài Kafka ra sao?
Bạn thiết kế outbox pattern để phát event đồng bộ với thay đổi dữ liệu nghiệp vụ mà không phụ thuộc giao dịch phân tán như thế nào?
Bạn xử lý consumer update database thành công nhưng chết trước khi xác nhận message bằng cơ chế idempotency nào?
Bạn xác định mốc commit offset hoặc acknowledge phù hợp để giảm nguy cơ mất message khi xử lý lỗi như thế nào?
Bạn phân biệt consumer offset của Kafka với cơ chế xác nhận message của RabbitMQ khi một bản ghi xử lý thất bại như thế nào?
Bạn giải thích Kafka binder ánh xạ destination và group tới topic và consumer group của Kafka ra sao?
Bạn thiết kế chính sách offset khởi tạo cho consumer group mới khi cần đọc từ đầu hoặc chỉ đọc sự kiện mới như thế nào?
Bạn so sánh thời điểm Kafka binder quản lý commit offset với chế độ manual acknowledgement khi xác định một record đã được xử lý an toàn như thế nào?
Bạn nhận biết các giới hạn của manual acknowledgement khi dùng functional consumer và binder-specific configuration ra sao?
Bạn xử lý tình huống Kafka consumer rebalance trong lúc Function đang xử lý một tác vụ dài như thế nào?
Bạn xác định vì sao max.poll.interval.ms và thời gian xử lý message liên quan đến khả năng bị thu hồi partition ra sao?
Bạn thiết kế batch consumption cho Kafka khi cần tăng throughput mà vẫn xác định item lỗi cụ thể ra sao?
Bạn phân biệt số lần poll, số record nhận mỗi poll và concurrency khi tinh chỉnh consumer Kafka theo throughput như thế nào?
Bạn giải thích tác động của Kafka producer acks, retries và idempotent producer tới độ bền và khả năng gửi trùng ra sao?
Bạn kiểm tra một event được gửi thành công tại phía producer nhưng consumer không thấy vì cấu hình topic hoặc offset như thế nào?
Bạn lựa chọn retention và compaction phù hợp khi cần phát lại lịch sử sự kiện hoặc giữ trạng thái mới nhất theo key ra sao?
Bạn kiểm soát việc consumer xử lý lại dữ liệu từ offset cũ mà không tạo side effect trùng ở các hệ thống ngoài Kafka như thế nào?
Bạn phân tích sự khác nhau giữa lỗi serialize ở producer và lỗi deserialize ở consumer Kafka khi chọn chiến lược xử lý ra sao?
Bạn giải thích RabbitMQ binder sử dụng exchange, queue và binding key để phân phối message đến consumer group như thế nào?
Bạn phân biệt publish-subscribe với work queue semantics trong RabbitMQ khi nhiều consumer group cùng nhận một message ra sao?
Bạn xác định cách cấu hình durable queue và persistent message để tăng khả năng chịu restart mà vẫn hiểu giới hạn bảo đảm ra sao?
Bạn so sánh cơ chế routing của RabbitMQ với partition của Kafka khi cần giữ thứ tự sự kiện trên một entity như thế nào?
Bạn đánh giá tác động của RabbitMQ prefetch và số consumer đồng thời đến throughput và số message chưa được xác nhận ra sao?
Bạn giải thích vì sao requeue liên tục một message lỗi có thể dẫn tới vòng lặp xử lý không tiến triển như thế nào?
Bạn thiết kế dead-letter exchange và queue cho RabbitMQ để tách message không xử lý được khỏi luồng chính ra sao?
Bạn xác định điều kiện một message bị nack, reject hoặc hết TTL dẫn đến dead-letter theo cấu hình broker như thế nào?
Bạn phân tích nguy cơ mất message khi dùng cơ chế không yêu cầu ack và ứng dụng lỗi giữa chừng như thế nào?
Bạn kiểm thử nhiều instance Rabbit consumer trong cùng group để xác minh tải được phân phối mà không nhân đôi side effect như thế nào?
Bạn xử lý tình huống RabbitMQ connection bị mất và broker giao lại những message đang chưa ack theo chiến lược nào?
Bạn lựa chọn khi nào dùng binder RabbitMQ thay vì Kafka cho workflow công việc ngắn, cần routing hoặc cần lưu lịch sử như thế nào?
Bạn đánh giá khả năng tích hợp Pulsar binder với mô hình Function và những giới hạn phiên bản hoặc tính năng cần xác minh như thế nào?
Bạn phân biệt khái niệm topic và subscription của Pulsar với destination và consumer group của Spring Cloud Stream ra sao?
Bạn thiết kế một thử nghiệm để kiểm tra partitioned topic, subscription type và message ordering của Pulsar binder như thế nào?
Bạn xử lý trường hợp môi trường triển khai không hỗ trợ một cấu hình retry hoặc DLQ giống Kafka hay RabbitMQ khi dùng Pulsar như thế nào?
Bạn xác định những rủi ro khi chuyển binder giữa Kafka, RabbitMQ và Pulsar dù tên binding và kiểu payload không đổi ra sao?
Bạn xây dựng ma trận tương thích cho producer, consumer và binder theo version trước khi chuyển một dịch vụ sang broker mới như thế nào?
Bạn phân biệt lỗi transient có thể retry với lỗi dữ liệu nghiệp vụ không thể sửa bằng retry trong một Function như thế nào?
Bạn giải thích tác động của retry ngay trong consumer so với chuyển message sang retry topic hoặc retry queue như thế nào?
Bạn xác định retry max attempts và backoff phù hợp khi dịch vụ downstream có thể tạm thời quá tải ra sao?
Bạn thiết kế chính sách jitter và giới hạn retry để tránh nhiều consumer cùng gọi lại downstream khi sự cố vừa kết thúc như thế nào?
Bạn mô tả luồng xử lý khi retry đã hết và message được chuyển tới dead-letter destination theo hỗ trợ của binder như thế nào?
Bạn phân biệt DLQ, parking-lot queue và luồng replay để tránh đưa dữ liệu độc hại trở lại luồng chính vô hạn ra sao?
Bạn quyết định DLQ nên chứa nguyên payload, headers và thông tin lỗi nào mà vẫn đáp ứng yêu cầu bảo mật như thế nào?
Bạn kiểm tra một message không đến DLQ vì lỗi xảy ra trước bước convert hoặc do cấu hình binder bằng cách nào?
Bạn thiết kế cơ chế cảnh báo khi số lượng message vào DLQ tăng và phân loại nguyên nhân do schema, quota hoặc dịch vụ ngoài ra sao?
Bạn xây dựng quy trình sửa và replay DLQ với audit trail, idempotency và giới hạn tốc độ theo các bước nào?
Bạn phân biệt error channel hoặc error handler ở tầng Spring Cloud Stream với dead-letter mechanism do broker hỗ trợ ra sao?
Bạn xác định lỗi phát sinh ở producer send có thể quan sát và xử lý khác với lỗi trong consumer Function như thế nào?
Bạn quyết định khi nào một lỗi phải làm cả instance tạm dừng nhận message thay vì tiếp tục skip hoặc gửi DLQ như thế nào?
Bạn thiết kế một consumer phát sinh lỗi ở item thứ ba trong batch và xác định dữ liệu nào có thể được ghi lại hoặc bỏ qua như thế nào?
Bạn mô tả việc retry toàn batch có thể gây xử lý lặp các item đã thành công và cách khắc phục bằng idempotency ra sao?
Bạn cân nhắc việc đặt timeout cho lời gọi HTTP bên trong consumer sao cho không kéo dài thời gian xử lý vượt khả năng broker như thế nào?
Bạn giải thích Kafka Streams binder khác Kafka message channel binder khi xử lý topology có trạng thái như thế nào?
Bạn mô tả vai trò của KStream, KTable và GlobalKTable trong một ứng dụng Kafka Streams được tích hợp qua Spring Cloud Stream ra sao?
Bạn quyết định khi nào dùng KStream để xử lý event liên tục và khi nào dùng KTable để biểu diễn trạng thái mới nhất theo key như thế nào?
Bạn thiết kế một hàm xử lý Kafka Streams để lọc event lỗi, map giá trị và phát output topic như thế nào?
Bạn phân biệt stateless transformation với stateful aggregation theo tài nguyên và khả năng khôi phục như thế nào?
Bạn mô tả cách grouping theo key và aggregation tạo ra state store trong Kafka Streams như thế nào?
Bạn lựa chọn windowing theo tumbling, hopping hoặc session khi cần tổng hợp sự kiện theo thời gian như thế nào?
Bạn xử lý sự kiện đến muộn hoặc lệch thứ tự trong cửa sổ Kafka Streams và quyết định grace period ra sao?
Bạn xác định khi nào nên dùng event time lấy từ record timestamp thay vì thời gian xử lý tại ứng dụng như thế nào?
Bạn phân biệt stream-stream join với stream-table join và loại dữ liệu cần chuẩn bị cho mỗi bên như thế nào?
Bạn kiểm tra kết quả aggregation hoặc join khi bản ghi đến trễ và cửa sổ đã đóng bằng phương pháp nào?
Bạn giải thích vai trò của Serde cho key và value trong Kafka Streams khi tạo source, state store và output ra sao?
Bạn xử lý sự cố state store không khôi phục được do thay đổi định dạng serialization giữa hai lần deploy như thế nào?
Bạn mô tả cách changelog topic hỗ trợ khôi phục local state store sau khi instance Kafka Streams bị restart như thế nào?
Bạn thiết kế naming và versioning cho application ID và state store để tránh xung đột giữa các ứng dụng hoặc môi trường ra sao?
Bạn phân biệt standby replicas, active task và rebalance khi triển khai Kafka Streams trên nhiều instance như thế nào?
Bạn đánh giá tác động của việc tăng số instance Kafka Streams tới state restoration và độ trễ sau rollout như thế nào?
Bạn giải thích tại sao stateful topology cần chú ý memory, disk và RocksDB trong môi trường container như thế nào?
Bạn thiết kế kiểm thử Kafka Streams topology với các record đầu vào có timestamp và thứ tự xác định như thế nào?
Bạn xác định khi nào cần kiểm thử exactly-once processing của Kafka Streams và những side effect ngoài Kafka vẫn cần xử lý riêng ra sao?
Bạn tổ chức unit test trực tiếp Function để kiểm tra biến đổi payload không phụ thuộc binder như thế nào?
Bạn sử dụng test binder của Spring Cloud Stream để gửi input và đọc output trong bài kiểm thử ứng dụng như thế nào?
Bạn mô tả cách InputDestination và OutputDestination hỗ trợ kiểm tra routing và message headers mà không khởi động Kafka hoặc RabbitMQ thật ra sao?
Bạn thiết kế test với nhiều binding name để xác minh message không bị chuyển nhầm sang destination khác như thế nào?
Bạn kiểm thử một Consumer xử lý dữ liệu và ghi database với transaction thật nhưng dùng binder thử nghiệm theo phạm vi nào?
Bạn phân biệt test binder với integration test sử dụng Kafka hoặc RabbitMQ thật khi cần xác minh partition, ack và DLQ ra sao?
Bạn dùng Testcontainers cho broker để kiểm tra consumer group rebalance và delivery sau restart trong bài test như thế nào?
Bạn thiết kế kiểm thử một sự kiện bị gửi hai lần và xác minh business side effect chỉ xuất hiện một lần ra sao?
Bạn kiểm tra message schema evolution giữa hai phiên bản producer và consumer bằng các bộ dữ liệu nào?
Bạn xử lý flakiness khi kiểm thử luồng bất đồng bộ mà không phụ thuộc Thread.sleep hoặc thời gian cố định như thế nào?
Bạn thiết kế bài kiểm thử retry và dead-letter để xác minh giới hạn số lần thử và payload được bảo toàn ra sao?
Bạn phân biệt readiness của ứng dụng với kết nối broker đã sẵn sàng tiêu thụ sự kiện bằng những kiểm tra nào?
Bạn lựa chọn các metric theo dõi consumer lag, throughput, processing latency và error rate cho Kafka như thế nào?
Bạn phân tích những chỉ số tương ứng trên RabbitMQ như queue depth, unacked messages và consumer count ra sao?
Bạn thiết kế distributed tracing để liên kết trace context từ producer qua broker đến consumer mà không làm lộ thông tin nhạy cảm như thế nào?
Bạn phân biệt lỗi backlog tăng do producer gửi quá nhanh với lỗi consumer bị retry hoặc không còn đủ instance ra sao?
Bạn dựa vào những tín hiệu nào để phát hiện hot partition hoặc consumer lag tăng sau khi thay đổi partition key như thế nào?
Bạn thiết kế chính sách graceful shutdown cho consumer để hạn chế bỏ dở tác vụ đang xử lý và hỗ trợ message được giao lại an toàn ra sao?
Bạn kiểm tra tác động của autoscaling đến Kafka rebalance, RabbitMQ queue consumers và Pulsar subscriptions như thế nào?
Bạn xác định cách tạm dừng hoặc khôi phục consumption khi cần bảo trì downstream mà không làm mất message ra sao?
Bạn phân tích sự cố producer gửi thành công nhưng consumer không thấy event bằng cách đối chiếu binding, destination, group và offset như thế nào?
Bạn điều tra trường hợp một event bị xử lý hai lần sau rolling deployment để tìm nguyên nhân từ ack, rebalance hoặc retry như thế nào?
Bạn thiết kế một ứng dụng Spring Cloud Stream xử lý đơn hàng qua Kafka, gửi thông báo qua RabbitMQ và bảo toàn dữ liệu khi một broker tạm thời không khả dụng như thế nào?
