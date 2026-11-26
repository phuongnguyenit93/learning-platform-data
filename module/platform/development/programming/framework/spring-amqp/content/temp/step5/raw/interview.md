Trong những bài toán nào bạn sẽ chọn Spring AMQP và RabbitMQ thay vì gọi HTTP đồng bộ giữa các dịch vụ?
Bạn giải thích vai trò của Spring AMQP khi ứng dụng Java giao tiếp với RabbitMQ như thế nào?
Bạn phân biệt giao thức AMQP 0-9-1 với thư viện Spring AMQP ở lớp ứng dụng ra sao?
Bạn xác định những giới hạn của mô hình hàng đợi bất đồng bộ đối với nghiệp vụ cần phản hồi ngay như thế nào?
Bạn mô tả đường đi của một message từ RabbitTemplate qua exchange đến queue và consumer ra sao?
Bạn phân biệt producer, exchange, binding, queue và consumer theo trách nhiệm nào?
Bạn đánh giá lợi ích của tách producer khỏi consumer khi hai dịch vụ triển khai độc lập như thế nào?
Bạn thiết kế hợp đồng message để hai hệ thống có thể thay đổi phiên bản mà vẫn tương thích ra sao?
Bạn phân biệt event thông báo sự kiện đã xảy ra với command yêu cầu xử lý nghiệp vụ như thế nào?
Bạn xác định trường hợp nào nên truyền message nhỏ thay vì đưa payload lớn vào RabbitMQ?
Bạn phân tích sự khác nhau giữa message được broker tiếp nhận và nghiệp vụ được consumer xử lý thành công như thế nào?
Bạn chọn tiêu chí nào khi đánh giá độ tin cậy, thông lượng và độ trễ của luồng xử lý bất đồng bộ?
Bạn giải thích mô hình at-most-once và at-least-once delivery khi dùng RabbitMQ như thế nào?
Bạn đánh giá tính khả thi của exactly-once business processing khi consumer cập nhật cơ sở dữ liệu ra sao?
Bạn xác định cách quản lý định danh sự kiện để xử lý message trùng lặp giữa các lần giao như thế nào?
Bạn cân nhắc những rủi ro nào khi một queue được nhiều dịch vụ không cùng mục đích tiêu thụ?
Bạn thiết kế quy ước đặt tên exchange, queue và routing key theo miền nghiệp vụ như thế nào?
Bạn phân biệt trường hợp cần một queue cho một nhóm consumer với trường hợp mỗi dịch vụ cần queue riêng như thế nào?
Bạn quyết định lưu vết message ở broker hay hệ thống nghiệp vụ theo các yêu cầu kiểm toán nào?
Bạn đánh giá RabbitMQ với một log broker khi cần đọc lại toàn bộ sự kiện quá khứ như thế nào?
Bạn tổ chức dependency và cấu hình Spring Boot để sử dụng Spring AMQP trong một dịch vụ như thế nào?
Bạn phân biệt vai trò của ConnectionFactory và RabbitTemplate trong kiến trúc Spring AMQP như thế nào?
Bạn cấu hình địa chỉ broker, virtual host, username và password giữa các môi trường ra sao?
Bạn xử lý cấu hình nhiều RabbitMQ broker endpoint để tăng khả năng kết nối như thế nào?
Bạn lựa chọn CachingConnectionFactory và cấu hình cache theo đặc điểm tải nào?
Bạn đánh giá chi phí của việc tạo connection mới so với tái sử dụng channel trong một ứng dụng như thế nào?
Bạn phân biệt AMQP channel với TCP connection và đánh giá những giới hạn khi chia sẻ channel giữa nhiều thread như thế nào?
Bạn quản lý số channel và connection để tránh vượt giới hạn broker như thế nào?
Bạn chọn cấu hình heartbeat để phát hiện mất kết nối nhưng không tạo báo động giả ra sao?
Bạn xử lý broker restart khi một Spring application vẫn đang phục vụ request như thế nào?
Bạn tổ chức lifecycle của connection factory để ứng dụng giải phóng tài nguyên khi shutdown ra sao?
Bạn phân biệt publisher connection với listener connection trong một hệ thống có tải lớn như thế nào?
Bạn đánh giá lợi ích của việc cô lập connection cho tác vụ publish và consume như thế nào?
Bạn xác định những timeout quan trọng khi kết nối, publish và chờ confirm như thế nào?
Bạn quản lý secret của RabbitMQ trong Spring Boot mà không đưa vào repository mã nguồn ra sao?
Bạn thiết kế cấu hình topology theo từng profile mà không vô tình tạo queue production trong môi trường test như thế nào?
Bạn sử dụng bean Exchange, Queue và Binding để khai báo tài nguyên AMQP trong Spring như thế nào?
Bạn giải thích vai trò của RabbitAdmin trong việc khai báo topology khi ứng dụng khởi động ra sao?
Bạn lựa chọn để ứng dụng tự declare queue hay quản lý topology qua hạ tầng theo những tiêu chí nào?
Bạn xử lý tình huống topology đã tồn tại với thuộc tính không tương thích với khai báo mới như thế nào?
Bạn đánh giá nguy cơ một ứng dụng dùng sai virtual host dẫn đến publish mà consumer không thấy message ra sao?
Bạn giải thích routing của direct exchange dựa trên routing key và binding key như thế nào?
Bạn dùng fanout exchange để gửi sự kiện cho nhiều consumer group độc lập ra sao?
Bạn thiết kế topic exchange với routing pattern có ký tự đại diện theo quy tắc nào?
Bạn phân biệt ý nghĩa của ký tự sao và dấu thăng trong binding key của topic exchange như thế nào?
Bạn dùng headers exchange trong trường hợp nào thay vì dùng routing key?
Bạn phân tích vai trò của default exchange khi gửi trực tiếp tới một queue như thế nào?
Bạn thiết kế nhiều binding cho một queue mà không tạo logic định tuyến khó kiểm soát ra sao?
Bạn đánh giá tình huống nhiều queue cùng được bind vào một exchange bằng routing key giống nhau như thế nào?
Bạn xử lý message không khớp bất kỳ binding nào để tránh mất dữ liệu âm thầm ra sao?
Bạn phân biệt alternate exchange với dead-letter exchange về thời điểm và nguyên nhân routing như thế nào?
Bạn thiết kế route versioning cho sự kiện khi consumer cũ và mới tồn tại đồng thời ra sao?
Bạn tổ chức namespace routing key cho event type, phiên bản và miền nghiệp vụ như thế nào?
Bạn đánh giá rủi ro tạo quá nhiều queue động theo user hoặc tenant như thế nào?
Bạn quyết định khi nào một queue cần durable, exclusive hoặc auto-delete dựa trên vòng đời sử dụng nào?
Bạn phân biệt transient message với durable queue về bảo đảm dữ liệu sau broker restart như thế nào?
Bạn sử dụng queue arguments để cấu hình TTL, dead-letter routing và giới hạn độ dài ra sao?
Bạn lựa chọn quản lý queue arguments qua policy của broker hay khai báo từ ứng dụng theo tiêu chí nào?
Bạn xử lý thay đổi chính sách queue khi tham số không thể cập nhật trực tiếp trên queue đang tồn tại như thế nào?
Bạn thiết kế các queue nhận sự kiện từ topic exchange để mỗi dịch vụ có bản sao message riêng như thế nào?
Bạn kiểm tra routing của một message qua exchange và queue bằng những bước nào?
Bạn phát hiện tình trạng publish vào exchange đúng nhưng routing key sai bằng cách nào?
Bạn xây dựng cơ chế phân vùng sự kiện theo tenant để bảo vệ dữ liệu và giảm nhiễu routing như thế nào?
Bạn so sánh classic queue và quorum queue khi ứng dụng cần độ bền cao như thế nào?
Bạn lựa chọn quorum queue theo nhu cầu chịu lỗi và khả năng nhân bản dữ liệu ra sao?
Bạn cân nhắc trade-off về hiệu năng, thứ tự và dung lượng khi chọn loại queue như thế nào?
Bạn giải thích điều kiện message có thể bị giao lại sau khi broker failover như thế nào?
Bạn đánh giá tác động của single active consumer lên thứ tự xử lý và khả năng mở rộng ra sao?
Bạn thiết kế consumer có khả năng chấp nhận thay đổi node leader của quorum queue như thế nào?
Bạn kiểm tra sự khác biệt giữa TTL theo message và TTL theo queue khi thiết kế chính sách hết hạn ra sao?
Bạn thiết kế dead-letter routing cho message hết hạn và message bị consumer từ chối khác nhau ở những điểm nào?
Bạn sử dụng RabbitTemplate để gửi message đến exchange với routing key theo cách nào?
Bạn chọn convertAndSend hay send tùy theo nhu cầu chuyển đổi payload như thế nào?
Bạn cấu hình MessageConverter để trao đổi JSON giữa các dịch vụ Java khác nhau như thế nào?
Bạn so sánh SimpleMessageConverter và Jackson JSON converter về tương thích và an toàn như thế nào?
Bạn quản lý contentType, encoding và type metadata để consumer giải mã đúng dữ liệu ra sao?
Bạn thiết kế DTO bất biến và quy ước schema để producer và consumer nâng cấp độc lập như thế nào?
Bạn xử lý trường hợp một message JSON thiếu field mới nhưng consumer vẫn cần tương thích như thế nào?
Bạn bảo vệ ứng dụng khỏi deserialization không an toàn khi nhận message từ nguồn không tin cậy ra sao?
Bạn chọn field nào cho message headers và field nào phải nằm trong payload nghiệp vụ?
Bạn đặt correlation ID, event ID và trace context vào message properties theo hợp đồng nào?
Bạn phân biệt message ID do ứng dụng đặt với delivery tag do channel quản lý như thế nào?
Bạn lựa chọn có bật publisher confirms cho RabbitTemplate theo yêu cầu độ tin cậy nào?
Bạn giải thích publisher confirm xác nhận điều gì và không xác nhận điều gì trong một luồng nghiệp vụ như thế nào?
Bạn cấu hình ConfirmCallback để nhận biết broker ack hoặc nack của message đã publish ra sao?
Bạn sử dụng CorrelationData để ghép publisher confirm với yêu cầu gửi ban đầu như thế nào?
Bạn xử lý tình huống mất kết nối trước khi nhận publisher confirm mà không tạo tác dụng phụ trùng lặp ra sao?
Bạn phân biệt publisher confirm với consumer acknowledgment qua ví dụ nào?
Bạn cấu hình mandatory publishing và ReturnsCallback để phát hiện message không route được như thế nào?
Vì sao publisher confirm ack vẫn có thể xảy ra với một message bị return do không route được?
Bạn xử lý thứ tự giữa returned message và publisher confirmation trong quy trình theo dõi kết quả gửi ra sao?
Bạn thiết kế trạng thái publish pending, confirmed, returned và failed trong hệ thống nghiệp vụ như thế nào?
Bạn lựa chọn xử lý lỗi publisher bằng retry ngay hay đưa vào outbox theo tiêu chí nào?
Bạn phân biệt lỗi không tồn tại exchange với trường hợp exchange tồn tại nhưng không có binding phù hợp như thế nào?
Bạn thiết kế timeout chờ confirm để tránh coi message chưa có phản hồi là chắc chắn đã thất bại ra sao?
Bạn xây dựng cơ chế đối soát message chưa được confirm sau khi tiến trình producer khởi động lại như thế nào?
Bạn phân tích tác động của việc chờ từng confirm tuần tự tới throughput producer ra sao?
Bạn thiết kế giới hạn số message đang chờ confirm để bảo vệ bộ nhớ producer như thế nào?
Bạn kiểm tra publisher confirms trong điều kiện broker chậm ghi xuống ổ đĩa như thế nào?
Bạn lựa chọn độ ưu tiên message có thể kiểm soát được trong ứng dụng theo những điều kiện nào?
Bạn đánh giá hậu quả của việc gửi message quá lớn qua RabbitTemplate đối với broker và consumer như thế nào?
Bạn triển khai idempotent publish khi API client gửi lại cùng một yêu cầu ra sao?
Bạn dùng RabbitTemplate để thực hiện request-reply trong trường hợp nghiệp vụ nào?
Bạn quản lý correlation ID và reply destination trong mô hình RPC qua RabbitMQ như thế nào?
Bạn lựa chọn timeout khi chờ phản hồi RPC và xử lý late reply ra sao?
Bạn phân tích giới hạn của request-reply trên RabbitMQ so với HTTP trong hệ thống yêu cầu độ trễ thấp như thế nào?
Bạn thiết kế cách bảo vệ reply consumer khỏi phản hồi trùng hoặc không còn request đang chờ như thế nào?
Bạn sử dụng @RabbitListener để đăng ký consumer nhận message từ queue như thế nào?
Bạn phân biệt @RabbitListener với lập trình trực tiếp RabbitMQ Java Client về mức độ trừu tượng ra sao?
Bạn xử lý payload được chuyển thành DTO trong phương thức listener theo cơ chế nào?
Bạn xác định cách nhận header và message properties cần thiết trong một @RabbitListener như thế nào?
Bạn tổ chức listener method tách việc nhận message khỏi service xử lý nghiệp vụ ra sao?
Bạn xử lý ngoại lệ từ @RabbitListener để message không bị xác nhận thành công nhầm như thế nào?
Bạn cấu hình container factory cho @RabbitListener theo yêu cầu concurrency và ack nào?
Bạn phân biệt SimpleRabbitListenerContainerFactory và DirectRabbitListenerContainerFactory về mô hình chạy consumer ra sao?
Bạn đánh giá hành vi scaling consumer khi thay đổi concurrentConsumers và maxConcurrentConsumers như thế nào?
Bạn chọn số lượng consumer phù hợp dựa trên tốc độ đến message và thời gian xử lý trung bình ra sao?
Bạn phân tích tác động của prefetch lên throughput, công bằng chia tải và số message đang unacked như thế nào?
Bạn giảm nguy cơ một consumer chậm giữ nhiều message đã prefetch mà chưa xử lý như thế nào?
Bạn quản lý QoS prefetch khác nhau cho queue có tác vụ ngắn và tác vụ dài ra sao?
Bạn xác định cơ chế dừng hoặc khởi động một listener container bằng cấu hình và lifecycle như thế nào?
Bạn thiết kế graceful shutdown để tránh hủy ngang tác vụ nghiệp vụ đang xử lý như thế nào?
Bạn giải thích vai trò của container acknowledgment mode AUTO, MANUAL và NONE trong Spring AMQP ra sao?
Bạn phân biệt Spring AMQP AUTO acknowledgment với AMQP broker autoAck ở mức protocol như thế nào?
Bạn chọn chế độ MANUAL khi ứng dụng cần quyết định ack dựa trên kết quả xử lý theo tiêu chí nào?
Bạn quản lý Channel và delivery tag khi tự gọi basicAck từ listener như thế nào?
Bạn xác định lý do không được dùng delivery tag của channel khác để acknowledgment như thế nào?
Bạn so sánh basicAck, basicNack và basicReject theo khả năng xử lý một hoặc nhiều delivery ra sao?
Bạn lựa chọn requeue hay reject không requeue khi gặp lỗi nghiệp vụ theo nguyên tắc nào?
Bạn xử lý message có lỗi dữ liệu vĩnh viễn để không bị đưa vào vòng lặp requeue vô hạn như thế nào?
Bạn giải thích giá trị redelivered cho biết những gì và không thể chứng minh điều gì về lần xử lý trước?
Bạn phân biệt message đang ready với message đang unacked khi xem RabbitMQ management metrics ra sao?
Bạn thiết kế cơ chế xử lý consumer chết sau khi ghi database thành công nhưng trước khi ack như thế nào?
Bạn bảo vệ ứng dụng trước việc broker giao lại message đã được xử lý một phần bằng cách nào?
Bạn xác định khóa idempotency theo event ID hay business key tùy trường hợp nào?
Bạn xử lý hai consumer cố gắng thực thi cùng một message trùng gần như đồng thời ra sao?
Bạn thiết kế bảng inbox để theo dõi message đã xử lý và kết quả xử lý như thế nào?
Bạn lựa chọn thời điểm ghi idempotency marker để không xác nhận thành công trước side effect thực tế ra sao?
Bạn phân tích tính an toàn khi consumer ack trước lúc cập nhật dữ liệu nghiệp vụ như thế nào?
Bạn xử lý message được ack thành công nhưng một lệnh gọi ra hệ thống ngoài thất bại sau đó ra sao?
Bạn đánh giá trường hợp listener ném AmqpRejectAndDontRequeueException và ảnh hưởng tới routing như thế nào?
Bạn dùng ConditionalRejectingErrorHandler để phân biệt lỗi chuyển đổi dữ liệu với lỗi tạm thời ra sao?
Bạn lựa chọn hành vi khi message không thể deserialize được trước khi vào listener method ra sao?
Bạn thiết kế cách lưu nguyên payload lỗi để điều tra mà không làm lộ thông tin nhạy cảm như thế nào?
Bạn phân biệt retry ở listener advice với redelivery của broker sau khi không ack ra sao?
Bạn thiết lập retry interceptor cho listener với các giới hạn số lần thử và backoff như thế nào?
Bạn lựa chọn retry đồng bộ trong consumer hay đẩy message vào retry queue dựa trên đặc điểm tải nào?
Bạn phân tích rủi ro giữ consumer thread khi một message retry với backoff quá dài như thế nào?
Bạn phân biệt lỗi transient như timeout với lỗi permanent như schema không tương thích như thế nào?
Bạn thiết kế retry policy riêng cho lỗi network, 429 và dữ liệu không hợp lệ ra sao?
Bạn áp dụng exponential backoff và jitter để tránh nhiều consumer retry đồng loạt như thế nào?
Bạn xác định số lần xử lý tối đa trước khi chuyển message sang dead-letter queue bằng những tiêu chí nào?
Bạn cấu hình dead-letter exchange và dead-letter routing key cho queue nguồn như thế nào?
Bạn thiết kế một DLQ riêng cho từng queue nguồn hoặc một DLQ chung theo tiêu chí nào?
Bạn đánh giá trường hợp DLX không có binding phù hợp khiến message không đến được DLQ như thế nào?
Bạn phân biệt DLQ với retry queue có TTL và routing quay về queue chính như thế nào?
Bạn thiết kế kiến trúc nhiều tầng retry queue để giãn thời gian giữa các lần xử lý ra sao?
Bạn giải thích vai trò của x-death header khi điều tra một message đi qua dead-letter routing như thế nào?
Bạn xác định những hạn chế khi dùng x-death để tính số lần retry trong một topology phức tạp ra sao?
Bạn ngăn message lặp vòng giữa queue chính, retry queue và DLQ như thế nào?
Bạn lựa chọn recoverer của Spring AMQP để đưa message không thể xử lý sang destination khác ra sao?
Bạn phân biệt RepublishMessageRecoverer với việc broker tự dead-letter sau reject như thế nào?
Bạn bảo đảm việc republish message lỗi có đủ metadata để tìm nguyên nhân và truy xuất nguồn ra sao?
Bạn xử lý message lỗi chứa exception stack trace quá dài khiến vượt giới hạn header như thế nào?
Bạn thiết kế quy trình replay DLQ có kiểm soát để không gây xử lý trùng hoặc bùng nổ lưu lượng ra sao?
Bạn phân biệt replay một message với purge cả DLQ về mức độ rủi ro vận hành như thế nào?
Bạn kiểm tra nguyên nhân lỗi trước khi replay hàng loạt message như thế nào?
Bạn giới hạn quyền move, replay và delete message từ DLQ theo vai trò vận hành ra sao?
Bạn đặt cảnh báo cho tỷ lệ message bị dead-letter và tồn đọng DLQ theo mục tiêu dịch vụ nào?
Bạn giải quyết mâu thuẫn giữa yêu cầu giữ thứ tự message và retry bằng queue khác như thế nào?
Bạn đánh giá việc dùng message TTL và queue TTL đối với chiến lược retry như thế nào?
Bạn xử lý tác động của head-of-line blocking khi message hết hạn không được chuyển ngay theo kỳ vọng ra sao?
Bạn phân biệt delayed exchange plugin với giải pháp TTL kết hợp DLX trong thiết kế trì hoãn xử lý như thế nào?
Bạn thiết kế chính sách backpressure khi producer nhanh hơn khả năng xử lý của consumer ra sao?
Bạn cân nhắc những tiêu chí nào trước khi tăng số consumer thay vì giảm tốc độ publish?
Bạn giải thích hành vi của queue khi một consumer xử lý chậm nhưng consumer khác vẫn rảnh như thế nào?
Bạn lựa chọn batch consumption khi thời gian xử lý mỗi message ngắn theo yêu cầu nào?
Bạn đánh giá sự đánh đổi giữa batch acknowledgment và khả năng giao lại message khi lỗi như thế nào?
Bạn thiết kế xử lý ordering theo order ID trong khi vẫn cần nhiều consumer như thế nào?
Vì sao thứ tự message trong queue chưa bảo đảm thứ tự hoàn tất khi có nhiều consumer xử lý song song?
Bạn xử lý các sự kiện out-of-order bằng sequence number và trạng thái nghiệp vụ như thế nào?
Bạn so sánh cạnh tranh consumer trên một queue với mô hình fanout sang nhiều queue về độ tin cậy ra sao?
Bạn lựa chọn publisher transaction hoặc publisher confirm theo yêu cầu hiệu năng và bảo đảm gửi như thế nào?
Trong một local AMQP channel transaction, những thao tác nào có thể được commit hoặc rollback?
Bạn xác định các giới hạn của channel transaction khi ứng dụng đồng thời ghi database như thế nào?
Bạn phối hợp Spring transaction với listener và database để giảm mất dữ liệu như thế nào?
Vì sao transaction của database và transaction của RabbitMQ không tự bảo đảm atomicity xuyên hai hệ thống?
Bạn thiết kế transactional outbox để tránh mất message giữa commit database và publish RabbitMQ ra sao?
Bạn xác định cơ chế outbox dispatcher và đánh dấu trạng thái gửi dựa trên publisher confirm như thế nào?
Bạn xử lý trạng thái outbox đã gửi nhưng dispatcher chết trước khi cập nhật bảng outbox như thế nào?
Bạn kết hợp outbox với idempotent consumer để đạt kết quả nghiệp vụ không bị lặp như thế nào?
Bạn đánh giá chi phí lưu trữ và dọn dẹp outbox khi lưu lượng sự kiện tăng cao ra sao?
Bạn lựa chọn xử lý bù trừ khi một chuỗi tác vụ bất đồng bộ hoàn thành một phần như thế nào?
Bạn thiết kế saga dựa trên RabbitMQ cho quy trình nhiều dịch vụ theo các bước nào?
Bạn xác định ranh giới nhất quán dữ liệu khi consumer gọi hai hệ thống downstream độc lập ra sao?
Bạn kiểm soát việc ack một message chỉ sau khi transaction nghiệp vụ được commit như thế nào?
Bạn xử lý lỗi không chắc chắn kết quả commit xảy ra trước khi broker gửi lại message ra sao?
Bạn đánh giá tác động của consumer transaction rollback tới redelivery và throughput như thế nào?
Bạn thiết kế chính sách xử lý lặp side effects không hỗ trợ rollback bằng cơ chế gì?
Bạn phân biệt publisher confirms với giao dịch AMQP và điều kiện lựa chọn từng cách như thế nào?
Bạn quản lý dữ liệu nghiệp vụ và trạng thái message khi chuyển từ đồng bộ sang eventual consistency ra sao?
Bạn xác định cách đối soát số bản ghi outbox với số tác vụ nghiệp vụ đã hoàn thành như thế nào?
Bạn tổ chức versioning cho schema message JSON mà không làm gián đoạn consumer cũ ra sao?
Bạn xử lý hai phiên bản producer và consumer chạy song song trong giai đoạn rolling deployment như thế nào?
Bạn đánh giá chiến lược thêm field tùy chọn so với đổi tên field bắt buộc trong hợp đồng message như thế nào?
Bạn thiết kế tương thích xuôi và ngược đối với enum hoặc loại sự kiện chưa biết như thế nào?
Bạn xử lý một consumer nhận message có contentType hoặc charset khác dự kiến ra sao?
Bạn lựa chọn thời hạn lưu message ở queue khi consumer offline lâu ngày theo yêu cầu nào?
Bạn cân nhắc chiến lược quota và max-length policy để tránh đầy disk broker như thế nào?
Bạn xử lý backlog cũ đã hết giá trị nghiệp vụ trước khi tăng tài nguyên consumer như thế nào?
Bạn thiết kế flow control khi RabbitMQ báo memory alarm hoặc disk alarm như thế nào?
Bạn xác định vì sao producer bị chặn publish dù connection vẫn đang mở bằng những chỉ số nào?
Bạn tính dung lượng broker cần dự phòng dựa trên tốc độ publish, kích thước message và thời gian gián đoạn consumer như thế nào?
Bạn lựa chọn cluster RabbitMQ hoặc topology federation/shovel theo những yêu cầu phân phối nào?
Bạn đánh giá nguy cơ đưa cluster RabbitMQ qua đường truyền mạng có độ trễ cao như thế nào?
Bạn xây dựng kế hoạch failover cho broker và kiểm thử khả năng consumer phục hồi như thế nào?
Bạn thiết kế quy trình rolling upgrade broker và Spring AMQP client để giảm gián đoạn ra sao?
Bạn xử lý consumer không tự phục hồi sau khi broker đổi leader hoặc node ngắt kết nối như thế nào?
Bạn cân nhắc giới hạn độ bền và replication của loại queue trước khi triển khai production như thế nào?
Bạn thiết kế cách khai báo và quản lý virtual host theo môi trường hoặc nhóm sản phẩm như thế nào?
Bạn áp dụng quyền configure, write và read trên exchange hoặc queue cho từng service account ra sao?
Bạn tách credential publisher và consumer để tuân thủ nguyên tắc ít quyền nhất như thế nào?
Bạn cấu hình TLS cho RabbitMQ connection và xác minh chứng chỉ phía server như thế nào?
Bạn xác định khi nào nên dùng mutual TLS cho giao tiếp từ ứng dụng Spring AMQP tới broker ra sao?
Bạn quản lý việc xoay vòng credential và chứng chỉ mà không ngắt toàn bộ consumer như thế nào?
Bạn kiểm soát quyền truy cập RabbitMQ Management API và giao diện quản trị như thế nào?
Bạn bảo vệ payload chứa thông tin cá nhân cả khi truyền và khi lưu trên broker như thế nào?
Bạn hạn chế log raw payload ở RabbitTemplate hoặc @RabbitListener khi xử lý dữ liệu nhạy cảm ra sao?
Bạn kiểm tra message headers do producer bên ngoài cung cấp để tránh giả mạo tenant hoặc quyền truy cập như thế nào?
Bạn thiết kế validation cho payload trước khi ghi database và phân loại lỗi phù hợp ra sao?
Bạn bảo vệ ứng dụng khỏi message quá lớn hoặc message có cấu trúc sâu bất thường như thế nào?
Bạn xử lý việc thu hồi quyền truy cập của một service account đang có nhiều connection mở như thế nào?
Bạn tổ chức audit trail cho thay đổi exchange, binding và queue policy trong môi trường production như thế nào?
Bạn thiết kế môi trường test và staging để không gửi nhầm sự kiện sang queue production ra sao?
Bạn xác định metrics quan trọng cho publish rate, deliver rate, acknowledge rate và ready messages như thế nào?
Bạn dùng unacked message count để nhận diện lỗi consumer, prefetch quá cao hoặc downstream chậm ra sao?
Bạn phân biệt queue depth tăng vì producer tăng tải với consumer giảm năng lực xử lý như thế nào?
Bạn đo end-to-end message latency từ lúc producer publish tới khi commit nghiệp vụ như thế nào?
Bạn theo dõi số publisher nacks, returns và confirm latency bằng metric nào?
Bạn phân biệt cảnh báo message bị return do không route được với lỗi publish vào exchange không tồn tại như thế nào?
Bạn phân biệt message redelivery rate cao với message DLQ tăng để xác định loại lỗi ra sao?
Bạn xác định ngưỡng cảnh báo cho queue backlog theo tốc độ tiêu thụ và thời gian xử lý còn lại như thế nào?
Bạn thiết kế dashboard Spring AMQP và RabbitMQ với connection, channel, consumer và queue metrics ra sao?
Bạn sử dụng Micrometer Observation hoặc tracing để theo dõi luồng gửi nhận message như thế nào?
Bạn truyền trace ID và correlation ID qua message headers giữa các dịch vụ như thế nào?
Bạn ngăn metric cardinality tăng vô hạn khi routing key chứa user ID hoặc order ID ra sao?
Bạn phân tích độ trễ publish tăng trong khi broker CPU thấp dựa trên metrics nào?
Bạn phát hiện consumer bị kẹt do gọi API ngoài quá lâu mà queue vẫn báo nhiều unacked message ra sao?
Bạn đo mức sử dụng thread listener và connection pool khi tăng concurrency như thế nào?
Bạn phát hiện memory alarm, disk alarm và channel limit trong RabbitMQ trước khi broker ngừng nhận message ra sao?
Bạn xây dựng runbook khi queue tăng nhanh, confirm latency tăng và consumer bắt đầu timeout như thế nào?
Bạn phân biệt logging thông tin kỹ thuật với ghi nguyên payload message khi điều tra sự cố ra sao?
Bạn xác định cách thu thập mẫu message lỗi mà vẫn tuân thủ chính sách dữ liệu như thế nào?
Bạn đánh giá sức khỏe hệ thống sau khi xử lý một đợt backlog lớn bằng các chỉ số nào?
Bạn viết unit test cho service dùng RabbitTemplate mà không phụ thuộc broker thật như thế nào?
Bạn kiểm thử JSON MessageConverter với payload hợp lệ, field thiếu và trường không hỗ trợ như thế nào?
Bạn kiểm thử routing direct, topic và fanout exchange bằng RabbitMQ thực ra sao?
Bạn dùng Testcontainers để khởi tạo RabbitMQ trong integration test Spring Boot như thế nào?
Bạn xây dựng test cho @RabbitListener để chờ xử lý bất đồng bộ mà không dựa vào sleep cố định ra sao?
Bạn kiểm thử publisher confirms và returned messages khi route không phù hợp như thế nào?
Bạn mô phỏng kết nối mất ngay trước publisher confirm để xác minh cơ chế retry an toàn ra sao?
Bạn kiểm thử consumer manual ack khi thao tác database thất bại giữa chừng như thế nào?
Bạn mô phỏng listener crash sau khi commit database nhưng trước ack để xác minh idempotency như thế nào?
Bạn kiểm thử message poison được chuyển DLQ sau khi vượt retry limit như thế nào?
Bạn kiểm thử x-death headers và đường đi của message qua nhiều retry queue ra sao?
Bạn tạo integration test cho cả tình huống requeue và reject không requeue như thế nào?
Bạn kiểm thử hợp đồng message giữa producer và consumer ở hai phiên bản khác nhau như thế nào?
Bạn kiểm tra việc thay đổi prefetch hoặc concurrency ảnh hưởng throughput và ordering ra sao?
Bạn xây dựng load test tăng publish rate để đo độ trễ, queue depth và broker resource usage như thế nào?
Bạn đánh giá tác động của message size và persistence đến throughput publisher ra sao?
Bạn mô phỏng broker restart khi vẫn còn persistent messages chưa xử lý để xác minh khả năng phục hồi ra sao?
Bạn kiểm thử một node của quorum queue gặp sự cố và đo ảnh hưởng tới producer, consumer như thế nào?
Bạn tạo test authorization khi một tài khoản chỉ có quyền đọc queue nhưng không có quyền publish như thế nào?
Bạn kiểm thử TLS handshake lỗi khi chứng chỉ hết hạn hoặc hostname không khớp như thế nào?
Bạn xác định tiêu chí pass/fail cho một thay đổi Spring AMQP dựa trên tỷ lệ mất, trùng, độ trễ và khả năng khôi phục như thế nào?
Nếu RabbitTemplate gửi thành công nhưng không queue nào nhận được, bạn sẽ lần theo exchange, routing key và binding ra sao?
Nếu publisher confirm ack nhưng message bị return, bạn sẽ chẩn đoán lý do và sửa cấu hình như thế nào?
Nếu listener xử lý cùng một order hai lần sau khi restart, bạn sẽ kiểm tra ack và idempotency như thế nào?
Nếu một message lỗi định dạng khiến queue quay vòng vô hạn, bạn sẽ cấu hình error handler và DLQ ra sao?
Nếu prefetch quá cao làm một consumer giữ nhiều message chưa ack, bạn sẽ điều chỉnh chia tải như thế nào?
Nếu queue backlog tăng mạnh sau khi deploy consumer mới, bạn sẽ kiểm tra message converter, schema và concurrency ra sao?
Nếu nhiều message vào DLQ sau thay đổi routing key, bạn sẽ kiểm tra sự khác biệt giữa DLX và exchange chính như thế nào?
Nếu worker dùng manual ack nhưng xác nhận nhầm delivery tag, bạn sẽ tìm nguyên nhân trong quản lý Channel ra sao?
Nếu database đã commit nhưng acknowledgment thất bại, bạn sẽ ngăn side effects bị thực thi lặp như thế nào?
Nếu producer retry và tạo hai bản message, bạn sẽ xác định nơi đặt business event ID và deduplication ra sao?
Nếu downstream trả 429 trong giờ cao điểm, bạn sẽ thiết kế retry delay mà không giữ listener thread như thế nào?
Nếu một queue critical dùng classic queue nhưng yêu cầu chịu mất node, bạn sẽ đánh giá phương án chuyển quorum như thế nào?
Nếu broker bị disk alarm và publish bị chặn, bạn sẽ ưu tiên bảo vệ dữ liệu và giảm backlog như thế nào?
Nếu một consumer mất kết nối sau khi broker failover nhưng ứng dụng vẫn healthy, bạn sẽ kiểm tra cơ chế recovery nào?
Nếu DLQ đã chứa nhiều message quá cũ, bạn sẽ xây dựng tiêu chí loại bỏ hay replay an toàn như thế nào?
Nếu RabbitMQ Management cho thấy ready messages thấp nhưng unacked rất cao, bạn sẽ khoanh vùng nguyên nhân như thế nào?
Nếu memory broker tăng đột biến sau khi bật publisher retry, bạn sẽ kiểm tra tốc độ publish và giới hạn pending nào?
Nếu một tenant nhận sự kiện của tenant khác, bạn sẽ truy nguyên routing, binding và phân quyền ra sao?
Nếu request-reply qua RabbitTemplate liên tục timeout nhưng consumer thực sự trả reply, bạn sẽ điều tra reply route như thế nào?
Nếu triển khai rolling upgrade làm message có hai schema khác nhau, bạn sẽ kiểm chứng tương thích và khôi phục ra sao?
Nếu order messages cần đúng thứ tự nhưng có nhiều consumer và redelivery, bạn sẽ thiết kế giải pháp nào ở tầng nghiệp vụ?
Bạn xây dựng kế hoạch khôi phục Spring AMQP service khi RabbitMQ, database và API downstream cùng gặp lỗi như thế nào?
