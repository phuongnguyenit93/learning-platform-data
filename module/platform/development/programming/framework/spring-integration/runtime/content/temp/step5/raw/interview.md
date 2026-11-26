Bạn giải thích Spring Integration Runtime điều phối một Message từ producer qua MessageChannel tới consumer endpoint như thế nào?
Bạn phân biệt vai trò của IntegrationFlow với các endpoint thực thi được tạo khi ApplicationContext khởi động như thế nào?
Bạn mô tả cách Message, MessageHeaders, MessageChannel và MessageHandler phối hợp tại runtime ra sao?
Bạn sẽ xác định chính xác thành phần nào chịu trách nhiệm tạo thread thực thi một MessageHandler trong một flow như thế nào?
Bạn phân biệt cấu hình IntegrationFlow lúc khởi động với trạng thái running của các endpoints khi ứng dụng đã chạy ra sao?
Bạn sẽ mô tả vòng đời của một message đi từ inbound endpoint tới outbound endpoint qua nhiều channels như thế nào?
Bạn phân biệt một bean MessageHandler với một consumer endpoint kết nối handler vào channel như thế nào?
Bạn giải thích EventDrivenConsumer đăng ký handler với SubscribableChannel tại runtime ra sao?
Bạn phân biệt EventDrivenConsumer với PollingConsumer về cơ chế kích hoạt handler như thế nào?
Bạn sẽ xác định khi nào SourcePollingChannelAdapter cần được dùng để lấy message từ MessageSource ra sao?
Bạn mô tả vai trò của MessageProducerSupport trong những inbound endpoints phát message dựa trên sự kiện như thế nào?
Bạn sẽ sử dụng IntegrationFlow DSL để nối nhiều endpoints mà vẫn nhìn thấy các ranh giới bất đồng bộ như thế nào?
Bạn phân tích vì sao một IntegrationFlow hợp lệ khi context refresh chưa bảo đảm mọi hệ thống nguồn và đích đều sẵn sàng ra sao?
Bạn sẽ đặt tên rõ ràng cho IntegrationFlow, MessageChannel và endpoint beans để quản lý runtime như thế nào?
Bạn phân biệt bean name của channel với component name được dùng trong management hoặc metrics như thế nào?
Bạn sẽ kiểm tra một endpoint không nhận message vì input channel chưa kết nối với đúng producer như thế nào?
Bạn phân tích nguy cơ vô tình có hai subscriber trên cùng channel rồi message được phân phối khác kỳ vọng như thế nào?
Bạn sẽ xác định khi nào nên tách một flow phức tạp thành các luồng con được nối qua channel ra sao?
Bạn phân biệt message-driven inbound endpoint với một @Scheduled method tự phát message theo chu kỳ như thế nào?
Bạn sẽ thiết kế một integration flow mà domain service không phụ thuộc trực tiếp vào Spring Integration headers như thế nào?
Bạn mô tả cách các endpoints được quản lý qua ApplicationContext và Spring SmartLifecycle ra sao?
Bạn sẽ xác định trạng thái started, stopped hoặc paused của endpoint dựa trên API lifecycle phù hợp như thế nào?
Bạn phân tích rủi ro giữ tham chiếu tới endpoint cũ khi IntegrationFlow được đăng ký lại như thế nào?
Bạn sẽ thiết kế cách xác nhận source đã phát message nhưng downstream consumer chưa hoàn thành xử lý như thế nào?
Bạn phân biệt correlation ID phục vụ truy vết với message ID do Spring Integration sinh theo mục tiêu nào?
Bạn sẽ xác định cách truyền custom headers qua transformer mà không làm mất metadata cần cho tracing ra sao?
Bạn đánh giá khi nào cần một adapter xử lý lỗi riêng thay vì đặt try/catch trong mọi MessageHandler ra sao?
Bạn sẽ chẩn đoán sự khác biệt giữa flow chưa được đăng ký và flow đã đăng ký nhưng endpoint chưa start như thế nào?
Bạn phân tích vì sao channel và handler là các abstraction trong JVM nhưng không tự cung cấp durable delivery ra sao?
Bạn sẽ chọn những loại channel nào khi cần đồng bộ, bất đồng bộ, buffering hoặc fan-out tại runtime?
Bạn giải thích DirectChannel thực thi subscriber trên thread của sender theo các điều kiện nào?
Bạn phân biệt DirectChannel với ExecutorChannel theo thời điểm send trả về và vị trí xử lý exception như thế nào?
Bạn sẽ lựa chọn ExecutorChannel khi cần tách producer thread khỏi handler nhưng vẫn kiểm soát queue capacity ra sao?
Bạn mô tả QueueChannel lưu message để consumer poll nhận sau như thế nào?
Bạn phân biệt QueueChannel với PublishSubscribeChannel về chiến lược dispatch khi có nhiều consumers như thế nào?
Bạn sẽ xác định khi nào RendezvousChannel phù hợp cho handoff giữa sender và receiver ra sao?
Bạn phân tích rủi ro cấu hình RendezvousChannel không có receiver khiến sender bị chặn như thế nào?
Bạn mô tả PriorityChannel chọn message theo độ ưu tiên và hệ quả với thứ tự gửi ban đầu như thế nào?
Bạn sẽ xác định khi nào một PollableChannel cần receive timeout để tránh giữ thread vô thời hạn ra sao?
Bạn phân biệt timeout của MessageChannel.send với timeout xử lý business handler sau khi nhận ra sao?
Bạn sẽ đánh giá tác động của giới hạn dung lượng QueueChannel khi nguồn phát nhanh hơn tốc độ consume như thế nào?
Bạn phân tích vì sao tăng kích thước QueueChannel không thay thế việc giải quyết chậm downstream ra sao?
Bạn sẽ thiết kế bounded channel hoặc backpressure policy để không làm tăng heap vô hạn ra sao?
Bạn phân biệt QueueChannel trong bộ nhớ với channel được backed bởi MessageGroupStore hoặc persistent MessageStore theo độ bền ra sao?
Bạn sẽ xác định khi nào channel persistence cần thiết vì JVM có thể crash sau khi message đã được gửi vào queue ra sao?
Bạn giải thích PublishSubscribeChannel xử lý một message với nhiều subscribers khác gì với DirectChannel như thế nào?
Bạn phân tích rủi ro PublishSubscribeChannel không có subscribers nhưng producer tưởng sự kiện đã được xử lý ra sao?
Bạn sẽ cấu hình error handling phù hợp cho PublishSubscribeChannel sử dụng TaskExecutor như thế nào?
Bạn phân biệt subscriber invocation đồng bộ qua SubscribableChannel với thực thi qua TaskExecutor trong PublishSubscribeChannel ra sao?
Bạn sẽ đánh giá độ ổn định thứ tự handlers khi cấu hình order cho nhiều subscribers như thế nào?
Bạn phân tích nguy cơ một subscriber chậm trong fan-out đồng bộ làm chậm toàn bộ producer ra sao?
Bạn sẽ lựa chọn round-robin hoặc load balancing tại UnicastingDispatcher cho nhiều handlers theo yêu cầu nào?
Bạn mô tả failover của dispatcher khi một handler từ chối message và các handler khác có thể xử lý như thế nào?
Bạn sẽ xác định nghĩa vụ idempotency khi cùng một message bị dispatch lại sau lỗi handler ra sao?
Bạn phân biệt FluxMessageChannel với các channel blocking trong môi trường Spring Integration reactive như thế nào?
Bạn sẽ kiểm tra cách chuyển message giữa FluxMessageChannel và handler blocking không làm nghẽn Reactor event loop ra sao?
Bạn phân tích rủi ro thay DirectChannel bằng ExecutorChannel làm mất context ThreadLocal của transaction hoặc security ra sao?
Bạn sẽ thiết kế trace propagation qua channel executor để giữ correlation mà không dựa vào tên thread ra sao?
Bạn đánh giá cách kiểm tra số message đang chờ trong QueueChannel và số task trong executor queue khi runtime backlog tăng ra sao?
Bạn giải thích MessageSource khác MessageProducerSupport như thế nào khi một endpoint được poll thay vì phát sự kiện trực tiếp?
Bạn mô tả PollingConsumer lấy Message từ PollableChannel theo chu kỳ rồi chuyển cho handler ra sao?
Bạn phân biệt SourcePollingChannelAdapter với PollingConsumer theo nguồn dữ liệu được polling như thế nào?
Bạn sẽ cấu hình PollerMetadata để điều khiển trigger, maxMessagesPerPoll và TaskExecutor cho endpoint nào?
Bạn phân biệt fixedDelay và fixedRate của một poller theo khả năng chạy chồng các lần poll ra sao?
Bạn sẽ chọn cron trigger khi nguồn chỉ cần được kiểm tra ở các khung giờ nhất định như thế nào?
Bạn phân tích tác động của maxMessagesPerPoll khi queue tồn đọng lớn nhưng các integration flows khác cũng cần CPU ra sao?
Bạn sẽ xác định khi nào maxMessagesPerPoll=-1 có thể làm một poller xử lý quá lâu như thế nào?
Bạn sẽ thiết kế polling policy để tránh tiêu thụ message nhanh hơn tốc độ downstream xử lý an toàn ra sao?
Bạn mô tả cách poller có thể thực thi trên TaskExecutor riêng và ảnh hưởng tới thread đang quản lý trigger như thế nào?
Bạn phân biệt concurrency của poller với concurrency của handler khi phía sau có ExecutorChannel như thế nào?
Bạn sẽ phân tích một lần poll lấy nhiều messages có luôn nằm trong một transaction duy nhất hay không theo cấu hình ra sao?
Bạn sẽ đặt một transaction advice vào poller để bao phủ các giai đoạn nhận và xử lý đồng bộ theo cách nào?
Bạn phân biệt lỗi xảy ra trong receive của MessageSource với lỗi handler sau khi gửi sang channel bất đồng bộ ra sao?
Bạn sẽ xác định khi nào RetryAdvice của poller có thể khiến cùng message được thử nhận lại nhiều lần như thế nào?
Bạn mô tả vai trò của ReceiveMessageAdvice khi muốn thực thi advice quanh thao tác nhận từ nguồn như thế nào?
Bạn sẽ đánh giá khi nào đặt backoff theo poller thay vì theo endpoint gửi outbound ra sao?
Bạn phân tích nguy cơ nhiều replicas cùng poll một bảng hoặc thư mục rồi nhận trùng message như thế nào?
Bạn sẽ áp dụng atomic claim hoặc distributed LockRegistry để giới hạn concurrency của poller theo cơ chế nào?
Bạn sẽ phân biệt logical source backlog với QueueChannel backlog khi xây dựng metric thực thi như thế nào?
Bạn mô tả cách receiveTimeout của PollingConsumer ảnh hưởng tần suất nhận message từ channel như thế nào?
Bạn sẽ giải thích tại sao poller chạy đúng lịch nhưng không tạo message nếu MessageSource trả null như thế nào?
Bạn phân tích tác động của TaskScheduler quá ít thread khi nhiều pollers phải chạy gần cùng thời điểm ra sao?
Bạn sẽ quyết định cách phân chia TaskScheduler và TaskExecutor cho các nhóm pollers khác nhau như thế nào?
Bạn mô tả tác động của cron trigger thay đổi trong cấu hình lên những endpoints đã chạy như thế nào?
Bạn sẽ xác định điểm nào cần restart endpoint khi thay đổi poller policy ở runtime như thế nào?
Bạn phân tích rủi ro tác vụ polling tiếp tục chạy trong lúc ứng dụng đang shutdown như thế nào?
Bạn sẽ thiết kế graceful pause poller khi database hoặc SFTP server đang bảo trì ra sao?
Bạn sẽ tính toán poll batch size, số lượng concurrency và connection pool theo throughput cần thiết như thế nào?
Bạn đánh giá trường hợp poller luôn báo running nhưng không có message do filter hoặc checkpoint không đúng như thế nào?
Bạn giải thích @EnableIntegration kích hoạt những thành phần hạ tầng runtime cần cho các IntegrationFlow như thế nào?
Bạn mô tả cách SmartLifecycle.start và SmartLifecycle.stop tác động tới integration endpoint tại runtime ra sao?
Bạn sẽ đặt autoStartup=false cho một endpoint phải được khởi chạy sau khi tải cấu hình bên ngoài theo cách nào?
Bạn phân biệt lifecycle của MessageChannel với lifecycle của consumer endpoint gắn trên channel như thế nào?
Bạn sẽ thiết kế phase ordering để inbound producers khởi động sau khi outbound resources và consumer endpoints sẵn sàng như thế nào?
Bạn phân tích nguy cơ stop outbound adapter trước inbound adapter trong lúc còn message in-flight ra sao?
Bạn sẽ sử dụng IntegrationFlowContext để đăng ký một IntegrationFlow mới khi ứng dụng đang chạy trong tình huống nào?
Bạn mô tả vai trò của IntegrationFlowRegistration khi cần quản lý flow đã đăng ký động ra sao?
Bạn sẽ xác định cách đặt ID duy nhất cho một dynamic flow để tránh đăng ký chồng lần nữa ra sao?
Bạn phân biệt remove integration flow khỏi context với stop tạm thời endpoint để bảo trì như thế nào?
Bạn sẽ kiểm tra resources được giải phóng khi một flow được unregister qua IntegrationFlowContext như thế nào?
Bạn phân tích rủi ro không hủy dynamic flow theo tenant khi tenant rời hệ thống khiến memory và threads tăng ra sao?
Bạn sẽ tạo luồng runtime có inbound poller mới nhưng tái sử dụng channel chung theo nguyên tắc nào?
Bạn đánh giá khi nào thay đổi consumer subscriptions động ảnh hưởng thứ tự và số lượt xử lý message như thế nào?
Bạn sẽ phân biệt refresh toàn ApplicationContext với start/stop một integration endpoint khi chỉ thay đổi nguồn message ra sao?
Bạn sẽ lấy trạng thái một endpoint qua bean name và Lifecycle API để làm health check như thế nào?
Bạn phân tích vì sao chỉ kiểm tra bean tồn tại trong ApplicationContext không chứng minh endpoint đang running ra sao?
Bạn sẽ thiết kế một quy trình pause, drain và resume cho flow đang có in-flight messages như thế nào?
Bạn mô tả tác động của graceful shutdown tới channel queue và handler futures đang chạy như thế nào?
Bạn sẽ xác định chính sách xử lý message tồn trong in-memory QueueChannel khi JVM phải dừng ra sao?
Bạn phân tích khi nào cần persistent MessageStore để khôi phục pending messages sau restart như thế nào?
Bạn sẽ sử dụng control bus để gửi lệnh quản lý trạng thái endpoint trong phạm vi quyền hạn nào?
Bạn phân biệt lệnh control bus với gọi API lifecycle trực tiếp từ code vận hành theo tính an toàn như thế nào?
Bạn sẽ giới hạn quyền gửi control bus command để client không đáng tin cậy không thể dừng production flow ra sao?
Bạn sẽ dùng actuator và Spring Integration management endpoints để quan sát thông tin component theo cách nào?
Bạn mô tả cách IntegrationGraphServer hỗ trợ khám phá cấu trúc các nodes và links của runtime integration graph ra sao?
Bạn sẽ kiểm tra runtime graph để xác định message đi vào channel không có consumer nào như thế nào?
Bạn phân tích vì sao dynamic flows cần được đặt tên để metrics và tracing không thay đổi thất thường qua lần deploy ra sao?
Bạn sẽ lập kế hoạch rolling restart đảm bảo hai replicas không cùng xử lý source message khi endpoint autoStartup bật ra sao?
Bạn sẽ xác định khi nào một IntegrationFlow không thể hoàn toàn drain vì có subscription sống lâu hoặc stream vô hạn như thế nào?
Bạn đánh giá rủi ro manual stop giữa lúc transaction đang thực thi và kết quả rollback hoặc redelivery như thế nào?
Bạn giải thích ranh giới Spring transaction được bảo toàn qua DirectChannel khi handler chạy trên cùng thread theo những điều kiện nào?
Bạn phân biệt giao dịch của poller với giao dịch bắt đầu riêng tại một outbound handler như thế nào?
Bạn sẽ xác định vì sao @Transactional tại một handler không tự bao trùm mọi upstream endpoints trong flow ra sao?
Bạn phân tích tác động của ExecutorChannel lên ThreadLocal transaction context của một DataSourceTransactionManager như thế nào?
Bạn sẽ thiết kế flow có QueueChannel sao cho dữ liệu được ghi trong transaction phù hợp sau khi message được lấy khỏi queue ra sao?
Bạn phân biệt transaction commit của JDBC với JMS acknowledgment khi message qua nhiều resource managers như thế nào?
Bạn sẽ quyết định khi nào sử dụng TransactionTemplate trong một service được gọi bởi Spring Integration endpoint ra sao?
Bạn mô tả cách advice chain của endpoint có thể bao quanh một lần poll hoặc một handler invocation như thế nào?
Bạn sẽ chọn TransactionInterceptor tại poller khi cần rollback checkpoint cùng với xử lý đồng bộ như thế nào?
Bạn phân tích vì sao một flow có outbound HTTP call trong transaction có thể kéo dài thời gian giữ database connection ra sao?
Bạn sẽ đánh giá tradeoff giữa transaction lớn bao trọn nhiều bước với nhiều transaction ngắn cộng idempotency ra sao?
Bạn sẽ thiết kế lưu trạng thái processed message trong database để an toàn khi source gửi trùng sau rollback như thế nào?
Bạn phân biệt commit thành công của database với thành công gửi outbound event sang message broker như thế nào?
Bạn sẽ dùng transactional outbox khi business update và publish event không có distributed transaction theo cách nào?
Bạn phân tích rủi ro poller đánh dấu record đã nhận trong database trước khi outbound publish thật sự thành công ra sao?
Bạn sẽ xác định chiến lược checkpoint sau xử lý khi nguồn là file, JMS, Kafka hoặc JDBC theo đặc thù nào?
Bạn đánh giá cách propagation REQUIRED và REQUIRES_NEW của một downstream service thay đổi kết quả khi outer poller rollback như thế nào?
Bạn sẽ phân biệt transactional MessageStore với persistent MessageStore chỉ lưu dữ liệu nhưng không tham gia cùng transaction ra sao?
Bạn phân tích vì sao một persistent QueueChannel không tự đảm bảo exactly-once business effect khi consumer có thể crash ra sao?
Bạn sẽ xác định lúc nào dùng JtaTransactionManager và khi nào tránh XA để dùng outbox/idempotency như thế nào?
Bạn sẽ thiết kế thử nghiệm crash sau khi database commit nhưng trước khi broker ack nhằm xác minh recovery ra sao?
Bạn đánh giá rủi ro một message bị đưa qua async channel rồi bị acknowledge quá sớm tại upstream như thế nào?
Bạn mô tả cách TransactionSynchronization callbacks có thể dùng để phát signal sau commit và giới hạn của cách làm này ra sao?
Bạn sẽ phân biệt afterCommit callback với outbox khi yêu cầu delivery có thể phục hồi sau process crash ra sao?
Bạn sẽ kiểm tra một Spring Integration handler chạy trong transaction thực tế của thread bằng cách nào?
Bạn phân tích ảnh hưởng của thread switch qua Reactor pipeline tới cách quản lý reactive transaction context như thế nào?
Bạn sẽ tổ chức rollback policy khi một handler phát lỗi checked exception mà transaction default không rollback ra sao?
Bạn đánh giá cách xử lý cancellation hoặc timeout của một reactive flow khi đồng bộ với resource transaction như thế nào?
Bạn giải thích errorChannel mặc định nhận ErrorMessage từ những lỗi bất đồng bộ được Spring Integration phát ra như thế nào?
Bạn phân biệt lỗi ném trực tiếp tới caller qua DirectChannel với lỗi được publish thành ErrorMessage sau khi qua ExecutorChannel ra sao?
Bạn sẽ cấu hình errorChannel riêng cho một endpoint để tránh làm lẫn lỗi của nhiều luồng tích hợp như thế nào?
Bạn mô tả một ErrorMessage giúp truy ra exception và failedMessage gốc theo những thông tin nào?
Bạn sẽ xác định vì sao một lỗi trong handler không được errorChannel nhận do caller đã xử lý exception trước đó ra sao?
Bạn phân tích rủi ro error handler nuốt exception khiến upstream nghĩ message đã xử lý thành công như thế nào?
Bạn sẽ thiết kế nhánh xử lý fatal error để chuyển message sang quarantine mà vẫn giữ correlation ID như thế nào?
Bạn phân biệt MessageHandlingException và MessageDeliveryException theo giai đoạn phát sinh như thế nào?
Bạn sẽ dùng RequestHandlerRetryAdvice với RetryTemplate để retry một outbound handler theo chính sách nào?
Bạn mô tả cách backoff và retry limit giúp giảm tải khi một remote service tạm gián đoạn như thế nào?
Bạn phân tích vì sao retry một handler có side effect không idempotent có thể gây tác dụng phụ trùng như thế nào?
Bạn sẽ lựa chọn recoveryCallback để trả message về error flow khi retry đã hết như thế nào?
Bạn phân biệt retry ở poller, retry advice tại handler và redelivery do broker nguồn theo số lần thực thi ra sao?
Bạn sẽ xác định cách tránh retry storm khi nhiều instances cùng retry một API outage ra sao?
Bạn phân tích vì sao bật retry cả ở broker và handler có thể nhân số attempt ngoài dự kiến như thế nào?
Bạn sẽ thiết kế phân loại lỗi validation, authentication, timeout và transient network failure để xử lý khác nhau ra sao?
Bạn đánh giá khi nào cần dead-letter queue của broker so với error channel trong bộ nhớ như thế nào?
Bạn sẽ cấu hình error message persistence nếu báo lỗi cần tồn tại sau khi ứng dụng restart như thế nào?
Bạn mô tả cách ErrorMessagePublisher hỗ trợ phát lỗi từ thành phần adapter có cơ chế xử lý lỗi riêng ra sao?
Bạn sẽ thiết kế một ErrorMessageStrategy để bổ sung metadata chẩn đoán mà không tiết lộ dữ liệu nhạy cảm như thế nào?
Bạn phân tích vì sao ErrorMessage có chứa failedMessage không đồng nghĩa với message có thể được redrive an toàn ra sao?
Bạn sẽ xác định khi nào sau retry thất bại cần giữ transaction rollback thay vì chỉ trả một status lỗi ra sao?
Bạn đánh giá ảnh hưởng của errorChannel subscriber chạy chậm tới nguồn phát message lỗi liên tục như thế nào?
Bạn sẽ giám sát tỷ lệ retry, số recoveries và số message bị quarantine để phát hiện sự cố kéo dài như thế nào?
Bạn phân tích rủi ro MessageHandler ném exception khác loại trong lần retry cuối khiến logic phân loại lỗi bị sai ra sao?
Bạn sẽ thiết kế correlation giữa một ErrorMessage và bản ghi audit của message ban đầu như thế nào?
Bạn phân biệt lỗi format headers trong transformer với lỗi resource connection trong adapter khi tổ chức runbook như thế nào?
Bạn sẽ đặt giới hạn payload log khi message quá lớn để tránh tốn tài nguyên trong error flow như thế nào?
Bạn đánh giá khi nào một circuit breaker hợp lý hơn retry liên tục tại outbound handler ra sao?
Bạn giải thích MessageStore và MessageGroupStore phục vụ các mục tiêu persistence và message grouping trong Spring Integration như thế nào?
Bạn phân biệt SimpleMessageStore trong bộ nhớ với JdbcMessageStore khi cần khôi phục thông điệp sau restart như thế nào?
Bạn sẽ lựa chọn JdbcChannelMessageStore cho một persistent QueueChannel theo yêu cầu nào?
Bạn mô tả vai trò của MessageGroupStore khi một Aggregator tích lũy messages chưa đủ điều kiện release ra sao?
Bạn phân biệt MessageStore giữ từng message với MessageGroupStore quản lý cả nhóm message liên quan như thế nào?
Bạn sẽ thiết kế correlation key cho Aggregator khi nhiều đơn hàng được xử lý xen kẽ như thế nào?
Bạn mô tả ý nghĩa của CORRELATION_ID, SEQUENCE_NUMBER và SEQUENCE_SIZE headers sau khi Splitter chia một message như thế nào?
Bạn sẽ xác định khi nào các sequence headers mặc định từ Splitter đủ dùng cho Aggregator ra sao?
Bạn phân tích nguy cơ dùng correlation ID không duy nhất khiến messages từ hai business workflows bị trộn một nhóm ra sao?
Bạn sẽ thiết kế CorrelationStrategy từ business key khi một nhóm message được tạo bởi nhiều nguồn khác nhau như thế nào?
Bạn phân biệt ReleaseStrategy dựa trên sequence size với điều kiện hoàn tất nghiệp vụ dựa trên nội dung ra sao?
Bạn sẽ kiểm tra một Aggregator không phát output do thiếu message hoặc release condition không bao giờ đạt như thế nào?
Bạn phân tích rủi ro group không hoàn tất và bị giữ vô thời hạn trong MessageGroupStore như thế nào?
Bạn sẽ cấu hình groupTimeout để xử lý các message groups không hoàn chỉnh theo policy nào?
Bạn phân biệt expireGroupsUponCompletion với expireGroupsUponTimeout trong quản lý trạng thái nhóm như thế nào?
Bạn sẽ quyết định khi nào sendPartialResultOnExpiry phù hợp và khi nào bắt buộc coi group chưa đủ là lỗi ra sao?
Bạn đánh giá rủi ro giải phóng partial group làm downstream hiểu nhầm rằng mọi message đã có mặt ra sao?
Bạn sẽ dùng group locking để tránh hai consumers cùng cập nhật một MessageGroupStore entry như thế nào?
Bạn phân tích yêu cầu shared persistent MessageGroupStore khi chạy nhiều replicas xử lý cùng correlation key ra sao?
Bạn sẽ cấu hình MessageGroupProcessor để tạo output từ các message cùng nhóm theo ngữ nghĩa nào?
Bạn phân biệt Aggregator với Resequencer khi cần gom nhóm để tính kết quả hoặc khôi phục thứ tự ra sao?
Bạn sẽ thiết kế Resequencer để khôi phục thứ tự theo sequence headers mà không giả định toàn bộ message sẽ đến như thế nào?
Bạn phân tích rủi ro mất một sequence number khiến nhóm chờ vô hạn dù nguồn đã gửi hết dữ liệu ra sao?
Bạn sẽ giữ correlation headers qua transformer hoặc router để Aggregator nhận diện đúng message group như thế nào?
Bạn đánh giá khi nào Splitter áp dụng applySequence để tạo sequence metadata phù hợp với Aggregator ra sao?
Bạn sẽ xác định tác động của duplicate message tới release condition của Aggregator như thế nào?
Bạn sẽ thiết kế IdempotentReceiverInterceptor để bỏ hoặc đánh dấu message đã xử lý theo MetadataStore như thế nào?
Bạn phân biệt IdempotentReceiverInterceptor với idempotency thực thi trong database business transaction như thế nào?
Bạn sẽ chọn persistent MetadataStore khi một app cần chống duplicate xuyên nhiều lần restart ra sao?
Bạn phân tích rủi ro hai replicas dùng local in-memory MetadataStore để quyết định cùng một message đã xử lý hay chưa như thế nào?
Bạn sẽ tổ chức cleanup cho metadata và message groups cũ mà không làm message còn in-flight mất khả năng correlation ra sao?
Bạn đánh giá cách giám sát số open groups, tuổi nhóm lâu nhất và message count trong MessageGroupStore như thế nào?
Bạn sẽ viết integration test cho Aggregator timeout và late arrivals để bảo đảm chính sách xử lý rõ ràng ra sao?
Bạn giải thích message history giúp truy vết các components mà một message đi qua trong Spring Integration như thế nào?
Bạn sẽ bật message history cho các luồng cần chẩn đoán bằng @EnableMessageHistory theo cân nhắc nào?
Bạn phân biệt message history trong MessageHeaders với distributed tracing qua nhiều services như thế nào?
Bạn sẽ kiểm tra message history khi một message đi qua sai channel do cấu hình router như thế nào?
Bạn phân tích chi phí giữ message history trong headers khi một flow có nhiều hops và throughput lớn như thế nào?
Bạn sẽ dùng Spring Integration management metrics hoặc Micrometer để theo dõi send counts và handler durations như thế nào?
Bạn phân biệt channel send rate với handler success rate và backlog khi đánh giá sức khỏe flow như thế nào?
Bạn sẽ thiết kế metric naming cho dynamic IntegrationFlow để không sinh series mới ở mỗi lần đăng ký như thế nào?
Bạn đánh giá rủi ro dùng message ID, correlation ID hoặc tenant ID làm metric tags gây cardinality quá lớn ra sao?
Bạn sẽ xây dựng dashboard theo endpoint running state, poll interval, retries và message store backlog như thế nào?
Bạn mô tả vai trò của MessageHandler metrics khi cần xác định bottleneck ở từng bước trong integration flow ra sao?
Bạn sẽ phân tích thread dump để phân biệt một poller blocked ở receive với một handler blocked ở HTTP call như thế nào?
Bạn sẽ xác định dấu hiệu TaskScheduler starvation khi hàng chục polls cùng đợi một số thread ít ỏi như thế nào?
Bạn phân tích cách TaskExecutor saturation khiến QueueChannel backlog và p99 latency tăng như thế nào?
Bạn sẽ sử dụng executor active count, queue size và rejected tasks để chẩn đoán tải lớn như thế nào?
Bạn phân biệt lỗi thread pool exhausted với deadlock do Java locks hoặc database locks ra sao?
Bạn sẽ kiểm tra impact khi một handler dùng blocking I/O trên Reactor event loop trong reactive integration flow như thế nào?
Bạn phân tích tác động của payload lớn qua nhiều transformer tới garbage collection và heap usage ra sao?
Bạn sẽ chọn streaming hoặc chunking để giảm peak memory cho một flow xử lý file lớn như thế nào?
Bạn đánh giá khi nào cần đặt timeouts tại outbound handler, gateway và poller thay vì một timeout tổng quát như thế nào?
Bạn sẽ thiết kế health indicator cho một endpoint quan trọng mà không làm liveness phụ thuộc vào hệ thống ngoài tạm lỗi ra sao?
Bạn phân biệt readiness của flow với sự tồn tại của ApplicationContext bean khi chuẩn bị nhận traffic như thế nào?
Bạn sẽ xác định cách phát hiện endpoint stopped nhưng nguồn vẫn gửi message làm backlog tăng như thế nào?
Bạn sẽ dùng IntegrationGraphServer để đối chiếu runtime graph với các channel metrics khi message không đi tới handler ra sao?
Bạn phân tích rủi ro bật logging toàn bộ payload trong production khi luồng chứa PII hoặc credentials như thế nào?
Bạn sẽ sử dụng trace propagation giữa inbound endpoint và outbound gateway khi flow chuyển thread như thế nào?
Bạn đánh giá khi nào phải tách CPU-bound transformer khỏi blocking outbound call để không làm nghẽn cùng executor ra sao?
Bạn sẽ kiểm thử throughput khi số subscribers của PublishSubscribeChannel tăng trên một flow như thế nào?
Bạn phân tích cách giảm batch size hoặc poll frequency khi downstream latency tăng đột ngột như thế nào?
Bạn sẽ xây dựng runbook kiểm tra endpoint status, channel subscribers, poller trigger và errorChannel theo thứ tự nào?
Bạn sẽ xác định cách replay messages an toàn từ persistent store sau khi khôi phục một ứng dụng bị crash ra sao?
Bạn phân biệt unit test MessageHandler với integration test cần chạy cả consumer endpoint, poller và channel như thế nào?
Bạn sẽ dùng @SpringIntegrationTest để kiểm tra một IntegrationFlow trong Spring TestContext khi phù hợp ra sao?
Bạn mô tả vai trò của MockIntegrationContext khi thay một outbound handler bằng mock trong integration test như thế nào?
Bạn sẽ dùng TestChannelInterceptor để quan sát messages đi qua channel và xác minh headers như thế nào?
Bạn phân tích vì sao một unit test gọi handler trực tiếp không kiểm chứng transaction hoặc threading của runtime flow như thế nào?
Bạn sẽ kiểm thử DirectChannel gọi handler trên thread hiện tại và ExecutorChannel gọi qua executor như thế nào?
Bạn sẽ thiết kế test cho QueueChannel bounded capacity để kiểm tra send timeout và backpressure ra sao?
Bạn đánh giá cách kiểm thử PollingConsumer chỉ xử lý message sau khi poller được start như thế nào?
Bạn sẽ dùng deterministic trigger hoặc điều khiển scheduler trong test thay vì Thread.sleep không ổn định như thế nào?
Bạn sẽ kiểm thử SourcePollingChannelAdapter dừng nhận dữ liệu khi SmartLifecycle.stop được gọi như thế nào?
Bạn phân tích cách test dynamic IntegrationFlowRegistration được stop và destroy mà không rò endpoint beans ra sao?
Bạn sẽ tạo test flow có inner @Transactional service và ExecutorChannel để chứng minh transaction không truyền qua thread như thế nào?
Bạn sẽ xác minh RetryAdvice gọi outbound handler đúng số lượt và recoverer nhận được failed message như thế nào?
Bạn đánh giá cách kiểm thử errorChannel nhận ErrorMessage khi asynchronous handler ném exception ra sao?
Bạn sẽ thiết kế test Aggregator nhận messages ngoài thứ tự nhưng release đúng khi đủ sequence như thế nào?
Bạn sẽ kiểm thử groupTimeout và sendPartialResultOnExpiry bằng đồng hồ được kiểm soát hoặc timeout ngắn ra sao?
Bạn phân tích vì sao cần test Aggregator với persistent MessageGroupStore sau restart thay vì chỉ test bằng memory ra sao?
Bạn sẽ kiểm thử IdempotentReceiverInterceptor với shared MetadataStore khi hai consumers cùng nhận event như thế nào?
Bạn sẽ xác nhận message history và correlation headers được giữ nguyên sau nhiều transformer bằng cách nào?
Bạn đánh giá cách benchmark poller throughput không làm quá tải hệ thống bên ngoài dùng trong test như thế nào?
Bạn sẽ mô phỏng thread pool saturation và xem metrics để kiểm tra chính sách từ chối công việc như thế nào?
Bạn phân tích khi nào cần Testcontainers với database hoặc broker để xác minh transaction và redelivery semantics như thế nào?
Bạn sẽ kiểm tra graceful shutdown khi handler đang xử lý message và poller còn scheduled tasks ra sao?
Bạn sẽ thiết kế test context restart với persistent QueueChannel để xác minh message tồn đọng được khôi phục như thế nào?
Bạn đánh giá tiêu chí nghiệm thu một IntegrationFlow production về throughput, retry, timeout, lifecycle và observability như thế nào?
Nếu một DirectChannel handler ném exception khiến sender thất bại nhưng thay bằng ExecutorChannel thì sender vẫn thành công, bạn sẽ xử lý error propagation ra sao?
Nếu một QueueChannel tăng backlog trong khi consumer endpoint báo running, bạn sẽ kiểm tra poller, thread pool và handler latency như thế nào?
Nếu message đến channel nhưng không có consumer nào xử lý, bạn sẽ kiểm tra subscriber registration và integration graph ra sao?
Nếu một SourcePollingChannelAdapter đang running nhưng MessageSource luôn trả null, bạn sẽ kiểm tra filter và checkpoint như thế nào?
Nếu nhiều pollers cùng dùng TaskScheduler quá ít thread và trễ lịch, bạn sẽ điều chỉnh cấu hình như thế nào?
Nếu một REQUIRES_NEW handler bị chạy qua ExecutorChannel mà context không giống upstream, bạn sẽ phân tích transaction boundary ra sao?
Nếu source message đã được ACK trước khi async handler ghi database, bạn sẽ thiết kế lại handoff và idempotency như thế nào?
Nếu errorChannel không thấy lỗi của một handler, bạn sẽ kiểm tra kiểu channel, exception handling và advice chain ra sao?
Nếu RequestHandlerRetryAdvice làm một lệnh ghi đơn hàng chạy nhiều lần, bạn sẽ thêm idempotency và phân loại retry thế nào?
Nếu một dynamic flow được đăng ký mỗi lần kết nối và không được destroy, bạn sẽ tìm memory leak và lifecycle resources ra sao?
Nếu Aggregator không release vì một SEQUENCE_NUMBER bị thiếu, bạn sẽ thiết kế timeout, partial result hoặc manual recovery như thế nào?
Nếu correlation key không đủ duy nhất khiến message của hai đơn hàng bị trộn, bạn sẽ sửa CorrelationStrategy và kiểm thử ra sao?
Nếu SimpleMessageStore mất pending messages khi JVM crash, bạn sẽ đánh giá chuyển sang persistent store và recovery như thế nào?
Nếu hai replicas cùng cập nhật shared MessageGroupStore gây race condition, bạn sẽ kiểm tra locking và transaction ra sao?
Nếu message history tăng overhead ở một flow lưu lượng cao, bạn sẽ điều chỉnh instrumentation và sampling như thế nào?
Nếu PublishSubscribeChannel có subscriber chậm làm upstream tăng latency, bạn sẽ tách executor và kiểm soát fan-out ra sao?
Nếu control bus cho phép user thiếu quyền dừng endpoint, bạn sẽ thiết kế giới hạn quyền và audit lệnh quản trị như thế nào?
Nếu application shutdown giữa transaction và message còn ở QueueChannel, bạn sẽ xác minh commit, checkpoint và khả năng replay ra sao?
Nếu một integration flow gặp p99 latency tăng nhưng send rate vẫn bình thường, bạn sẽ đối chiếu executor queue, handler duration và remote calls như thế nào?
Nếu cần thiết kế Spring Integration runtime nhiều replicas cho một hệ thống quan trọng, bạn sẽ quản lý channel, poller, transaction, retry, MessageStore, correlation, lifecycle và monitoring như thế nào?
