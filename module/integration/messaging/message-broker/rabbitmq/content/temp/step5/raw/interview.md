Trong những tình huống nào bạn sẽ chọn RabbitMQ để giao tiếp bất đồng bộ giữa các dịch vụ?
Bạn đánh giá những tiêu chí nào khi lựa chọn RabbitMQ thay vì gọi HTTP đồng bộ?
Mô hình AMQP 0-9-1 giúp tách publisher, broker và consumer như thế nào?
Một thông điệp đi qua những thành phần nào từ lúc publisher gửi đến khi consumer xử lý xong?
Exchange có trách nhiệm gì trong quá trình phân phối thông điệp?
Queue lưu giữ và chuyển thông điệp đến consumer theo cơ chế nào?
Binding kết nối exchange và queue như thế nào?
Routing key được publisher và exchange sử dụng ra sao?
Bạn thiết kế direct exchange cho nhiều loại lệnh nghiệp vụ như thế nào?
Fanout exchange phù hợp với những trường hợp phát sự kiện nào?
Bạn xây dựng quy tắc topic exchange cho hệ thống nhiều miền nghiệp vụ như thế nào?
Headers exchange có ưu điểm và giới hạn gì khi định tuyến theo thuộc tính thông điệp?
Default exchange định tuyến đến queue theo tên ra sao?
Hai ký tự đại diện * và # trong topic routing tạo ra những cách khớp khác nhau như thế nào?
Một queue gắn với nhiều binding sẽ nhận thông điệp theo cách nào?
Exchange-to-exchange binding có thể giải quyết bài toán định tuyến phức tạp nào?
Bạn sử dụng alternate exchange để xử lý thông điệp không tìm thấy đích như thế nào?
Bạn phát hiện thông điệp không được định tuyến bằng cờ mandatory và publisher return ra sao?
Bạn thiết kế routing key thế nào để dễ mở rộng mà không làm ảnh hưởng consumer cũ?
Bạn phân biệt cách gửi command và phát domain event qua RabbitMQ như thế nào?
Những thông tin nào nên nằm trong payload và những thông tin nào nên nằm trong message properties?
Bạn xây dựng và quản lý hợp đồng dữ liệu giữa publisher và consumer như thế nào?
Bạn xử lý thay đổi schema thông điệp khi các dịch vụ nâng cấp lệch phiên bản ra sao?
Correlation ID và message ID giúp truy vết giao dịch bất đồng bộ như thế nào?
Vhost giúp tách biệt môi trường hoặc nhóm ứng dụng như thế nào?
Bạn lựa chọn số lượng TCP connection và AMQP channel dựa trên các yếu tố nào?
Vì sao việc dùng chung một channel giữa nhiều luồng Java cần được xem xét cẩn thận?
Heartbeat và cơ chế phát hiện mất kết nối ảnh hưởng đến ứng dụng như thế nào?
Bạn thiết kế hành vi tái kết nối để tránh tạo quá nhiều connection cùng lúc ra sao?
Bạn tổ chức khai báo exchange, queue và binding khi nhiều dịch vụ cùng khởi động thế nào?
Durable exchange và durable queue đảm bảo những điều gì sau khi broker khởi động lại?
Persistent message khác gì với durable queue về khả năng giữ dữ liệu?
Bạn kiểm chứng một thông điệp đã được broker chấp nhận và lưu an toàn theo cơ chế nào?
Publisher confirm hoạt động như thế nào từ góc nhìn publisher?
Bạn chọn synchronous confirm hay asynchronous confirm dựa vào yêu cầu hiệu năng và độ tin cậy nào?
Bạn quản lý nhiều thông điệp đang chờ publisher confirm ra sao?
Publisher nên xử lý phản hồi nack từ broker như thế nào?
Publisher return và publisher confirm cung cấp những tín hiệu khác nhau ra sao?
Bạn đánh đổi những gì khi dùng AMQP transaction thay cho publisher confirm?
Consumer acknowledgement quyết định việc xóa thông điệp khỏi queue như thế nào?
Bạn chọn auto acknowledgement hay manual acknowledgement trong những tình huống nào?
Cờ multiple của basic.ack có thể ảnh hưởng đến các delivery đang chờ như thế nào?
Bạn phân biệt basic.reject và basic.nack trong xử lý thông điệp lỗi ra sao?
Cờ requeue tác động thế nào đến thông điệp bị từ chối?
Bạn giải thích và sử dụng cờ redelivered của một delivery như thế nào?
Nếu consumer ghi dữ liệu thành công rồi chết trước khi ack, hệ thống nên xử lý lần giao lại ra sao?
Bạn thiết kế consumer có tính idempotent bằng những khóa và ràng buộc dữ liệu nào?
Bạn đánh giá phát biểu đảm bảo exactly-once khi dùng RabbitMQ như thế nào?
Thứ tự thông điệp có thể thay đổi trong những điều kiện xử lý và giao lại nào?
Bạn duy trì thứ tự xử lý theo từng đơn hàng khi cần chạy nhiều consumer như thế nào?
Competing consumers giúp tăng thông lượng và gây ra những đánh đổi gì?
Single active consumer giải quyết những yêu cầu xử lý tuần tự nào?
Prefetch ảnh hưởng như thế nào đến số lượng thông điệp chưa ack và khả năng chia tải?
Bạn điều chỉnh prefetch dựa trên thời gian xử lý và tài nguyên consumer ra sao?
Bạn điều tra tình trạng consumer giữ nhiều unacknowledged messages nhưng xử lý chậm như thế nào?
Một consumer bị hủy subscription hoặc mất kết nối sẽ ảnh hưởng đến các delivery chưa ack ra sao?
Bạn xử lý graceful shutdown để giảm khả năng thông điệp bị xử lý dở như thế nào?
Message TTL và queue TTL giải quyết những vòng đời dữ liệu khác nhau như thế nào?
Bạn thiết kế cơ chế hết hạn thông điệp để tránh thực thi một lệnh đã lỗi thời ra sao?
Priority queue có thể ảnh hưởng đến công bằng và hiệu năng xử lý như thế nào?
Kích thước payload và tần suất thông điệp ảnh hưởng đến thiết kế broker ra sao?
Bạn phân biệt lỗi tạm thời và lỗi không thể phục hồi khi consumer xử lý message như thế nào?
Bạn tổ chức retry sao cho lỗi tạm thời không làm nghẽn luồng thông điệp chính?
Dead-letter exchange được cấu hình và kích hoạt trong những trường hợp nào?
Một thông điệp đi từ queue chính sang dead-letter queue qua các routing rule nào?
Bạn khai thác thông tin x-death để phân tích lịch sử thông điệp thất bại ra sao?
Bạn thiết kế retry có trì hoãn bằng các queue và TTL như thế nào?
Bạn áp dụng exponential backoff và jitter cho retry để giải quyết vấn đề gì?
Bạn quy định số lần thử lại tối đa dựa trên những tiêu chí nghiệp vụ nào?
Bạn nhận diện và cô lập poison message như thế nào?
Bạn phát hiện và ngăn vòng lặp requeue liên tục tiêu tốn tài nguyên ra sao?
Bạn thiết kế nơi lưu giữ thông điệp lỗi để hỗ trợ điều tra như thế nào?
Bạn xây dựng quy trình replay thông điệp từ dead-letter queue ra sao?
Bạn kiểm tra những điều kiện nào trước khi replay hàng loạt thông điệp lỗi?
Những chỉ số nào giúp phát hiện dead-letter queue đang tăng bất thường?
Bạn đánh đổi những gì giữa TTL-based delay và cơ chế delayed-message chuyên dụng?
Bạn xử lý retry thế nào khi một thông điệp đã hết hạn nghiệp vụ?
Bạn xác định timeout xử lý message thế nào khi tác vụ phụ thuộc dịch vụ bên ngoài?
Trong tình huống nào RPC qua RabbitMQ là lựa chọn hợp lý?
Bạn thiết kế reply queue và cơ chế thu hồi phản hồi RPC quá hạn như thế nào?
Bạn dùng correlation ID để ghép phản hồi RPC với request đang chờ ra sao?
Bạn xử lý eventual consistency giữa các dịch vụ sau khi phát sự kiện như thế nào?
Transactional outbox giải quyết điểm không nhất quán giữa database và publish như thế nào?
Nếu transaction database thành công nhưng publisher chưa gửi được sự kiện, bạn phục hồi như thế nào?
Nếu publisher bị mất kết nối sau khi gửi nhưng trước khi nhận confirm, bạn quyết định gửi lại ra sao?
Bạn bảo đảm tác dụng phụ không bị lặp khi consumer hoàn tất công việc nhưng ack thất bại như thế nào?
Bạn thiết kế một quy trình có thể kiểm toán được khi cùng message bị giao lại nhiều lần ra sao?
Bạn khởi tạo ConnectionFactory của RabbitMQ Java Client với các tham số nào?
Bạn dùng Java Client để tạo exchange, queue và binding một cách an toàn khi khởi động như thế nào?
Bạn quản lý vòng đời Connection và Channel trong ứng dụng Java như thế nào?
Bạn bố trí worker thread và channel để xử lý song song mà không vi phạm giới hạn thread-safety ra sao?
Bạn gửi message kèm routing key và properties bằng Java Client như thế nào?
Bạn triển khai theo dõi publisher confirms bằng callback trong Java như thế nào?
Bạn xử lý message trả về do không định tuyến được bằng Java Client ra sao?
Bạn tổ chức callback basicConsume để phân biệt xử lý thành công và thất bại như thế nào?
Delivery tag ràng buộc với channel ảnh hưởng đến thao tác ack trong Java ra sao?
Bạn lựa chọn basicGet hay push consumer dựa trên đặc điểm tải nào?
Bạn giới hạn số tác vụ xử lý song song khi callback nhận thông điệp nhanh hơn khả năng xử lý ra sao?
Bạn truyền quyền ack từ worker thread về đúng channel như thế nào?
Bạn kiểm tra hành vi automatic connection recovery của Java Client trong những tình huống nào?
Bạn phân loại lỗi kết nối, lỗi channel và lỗi nghiệp vụ trong mã Java ra sao?
Bạn lựa chọn định dạng serialize message để nhiều phiên bản ứng dụng Java cùng sử dụng như thế nào?
Bạn dùng content type và version metadata để giải mã payload an toàn ra sao?
Bạn viết integration test cho publisher và consumer với RabbitMQ thật hoặc Testcontainers như thế nào?
Bạn mô phỏng tình huống broker mất kết nối trong lúc publish để kiểm thử cơ chế phục hồi ra sao?
Bạn kiểm thử tình huống giao lại trùng message để chứng minh consumer có tính idempotent như thế nào?
Bạn cấu hình kết nối RabbitMQ trong ứng dụng Spring Boot theo môi trường ra sao?
RabbitTemplate hỗ trợ những bước nào khi gửi và chuyển đổi message trong Spring AMQP?
Bạn sử dụng RabbitAdmin và các Declarable bean để quản lý topology như thế nào?
Bạn quyết định khai báo queue bằng mã nguồn hay quản lý bằng policy tại broker dựa trên tiêu chí nào?
Bạn thiết kế phương thức @RabbitListener để tách logic nghiệp vụ khỏi xử lý hạ tầng như thế nào?
Listener container của Spring AMQP quản lý consumer và vòng đời kết nối ra sao?
Bạn lựa chọn SimpleRabbitListenerContainerFactory hay DirectRabbitListenerContainerFactory theo đặc điểm tải nào?
Bạn điều chỉnh concurrency và max concurrency của listener dựa trên dữ liệu đo lường như thế nào?
Bạn cấu hình manual acknowledgement trong @RabbitListener để ack đúng thời điểm ra sao?
Bạn xử lý exception trong listener để quyết định retry, reject hoặc dead-letter như thế nào?
Bạn cấu hình ErrorHandler trong Spring AMQP nhằm phân biệt lỗi chuyển đổi dữ liệu và lỗi xử lý ra sao?
Bạn tổ chức retry interceptor tại listener mà vẫn giới hạn được số lần chạy lại như thế nào?
Bạn cấu hình dead-letter routing cho queue tiêu thụ bởi Spring AMQP như thế nào?
Bạn dùng publisher confirm callback trong RabbitTemplate để theo dõi từng lần gửi ra sao?
Bạn sử dụng CorrelationData nhằm đối soát kết quả publish của các message đồng thời như thế nào?
Bạn phối hợp returns callback với publisher confirms trong Spring AMQP ra sao?
Bạn cấu hình message converter JSON trong Spring AMQP và quản lý dữ liệu không tương thích như thế nào?
Bạn kiểm soát type headers và lớp dữ liệu được phép deserialize để giảm rủi ro bảo mật ra sao?
Bạn đánh giá ranh giới transaction giữa Spring database transaction và message acknowledgement như thế nào?
Bạn hạn chế việc consumer phụ thuộc một tác vụ xử lý dài trong listener thread như thế nào?
Bạn xây dựng bài kiểm thử end-to-end cho RabbitTemplate và @RabbitListener như thế nào?
Bạn xử lý sự khác biệt cấu hình giữa local, staging và production trong Spring AMQP ra sao?
Bạn triển khai graceful shutdown của Spring listener container khi còn message đang xử lý như thế nào?
Bạn giải quyết việc nâng cấp thư viện Spring AMQP và RabbitMQ Client khi broker đổi phiên bản ra sao?
Bạn quyết định sử dụng classic queue hay quorum queue dựa trên yêu cầu nào?
Quorum queue sử dụng đồng thuận giữa các replica để bảo vệ dữ liệu như thế nào?
Bạn chọn số replica của quorum queue theo mục tiêu chịu lỗi và chi phí vận hành ra sao?
Một quorum queue phản ứng thế nào khi mất leader trong quá trình đang có publisher và consumer?
Bạn giải thích tác động của việc mất đa số replica đến khả năng ghi và đọc quorum queue như thế nào?
Bạn xử lý message bị giao lại nhiều lần với delivery limit của quorum queue ra sao?
Bạn lập kế hoạch chuyển đổi một classic queue đang hoạt động sang quorum queue như thế nào?
Bạn phát hiện khai báo queue xung đột với thuộc tính đã có trên broker bằng cách nào?
Bạn phân tích giới hạn thông lượng của một queue có một leader như thế nào?
Bạn phân bổ queue leaders và tải giữa các node RabbitMQ như thế nào?
Bạn chia luồng message thành nhiều queue để giảm điểm nghẽn mà vẫn giữ yêu cầu ordering ra sao?
Bạn lựa chọn topology cluster RabbitMQ khi các node nằm trên những vùng mạng khác nhau như thế nào?
Bạn phân biệt mục tiêu của clustering, federation và shovel trong kiến trúc nhiều địa điểm ra sao?
Bạn xây dựng quy trình nâng cấp từng node của cluster để giảm gián đoạn như thế nào?
Bạn kiểm tra tương thích policy, queue type và phiên bản RabbitMQ trước khi nâng cấp ra sao?
Bạn xác định RPO và RTO cho hệ thống dùng RabbitMQ theo yêu cầu nghiệp vụ như thế nào?
Bạn lập phương án backup, khôi phục cấu hình và xử lý thông điệp chưa tiêu thụ sau thảm họa ra sao?
Memory alarm và disk alarm của RabbitMQ ảnh hưởng đến khả năng publish như thế nào?
Bạn dùng những chỉ số nào để phân biệt message ready và message unacknowledged trong một queue?
Bạn đo throughput publish, deliver, ack và redelivery để nhận diện nghẽn hệ thống như thế nào?
Bạn đo độ trễ từ lúc phát sự kiện đến khi nghiệp vụ hoàn tất bằng cách nào?
Bạn nhận biết broker bị flow control và lần theo nguyên nhân từ đâu?
Bạn điều chỉnh prefetch cùng số lượng consumer để cân bằng độ trễ và thông lượng ra sao?
Bạn phân tích nguyên nhân consumer sử dụng CPU cao hoặc bị giới hạn bởi I/O như thế nào?
Bạn đánh đổi những gì giữa tốc độ publish và cơ chế xác nhận bền vững?
Bạn thiết kế bài load test có traffic tăng đột biến và message thất bại như thế nào?
Bạn autoscale consumer theo queue depth, tốc độ xử lý và độ trễ như thế nào?
Bạn dự báo thời gian tiêu hết backlog sau khi dịch vụ downstream phục hồi ra sao?
Bạn áp dụng giới hạn tải và backpressure từ producer đến consumer như thế nào?
Bạn xác định giới hạn số queue, connection, channel và message phù hợp với tài nguyên cụm ra sao?
Bạn tối ưu hóa payload, batching hoặc mô hình publish khi lưu lượng tăng mạnh như thế nào?
Bạn lập dashboard và alert cho queue backlog, redelivery, DLQ, memory và disk ra sao?
Bạn dùng trace ID và structured logging để lần theo một thông điệp qua nhiều dịch vụ như thế nào?
Bạn xây dựng runbook ứng phó khi queue tăng nhanh nhưng hệ thống giám sát không báo lỗi như thế nào?
Bạn thiết kế vhost, user và quyền truy cập để thực hiện nguyên tắc ít quyền nhất ra sao?
Bạn cấp quyền configure, write và read cho publisher và consumer theo vai trò như thế nào?
Bạn cấu hình TLS giữa ứng dụng và broker và xác minh danh tính server ra sao?
Bạn lập quy trình xoay vòng chứng chỉ TLS mà không ngắt các dịch vụ lâu như thế nào?
Bạn lưu trữ, cấp phát và xoay vòng mật khẩu hoặc token kết nối RabbitMQ như thế nào?
Bạn kiểm soát cổng mạng và khả năng truy cập RabbitMQ Management UI/API ra sao?
Bạn tích hợp phương thức xác thực tập trung với RabbitMQ khi hệ thống yêu cầu như thế nào?
Bạn cô lập dữ liệu và quyền truy cập giữa nhiều khách hàng trên cùng hạ tầng như thế nào?
Bạn bảo vệ thông tin nhạy cảm trong payload, log và dead-letter queue ra sao?
Bạn thu thập nhật ký truy cập và các thay đổi topology để phục vụ kiểm toán như thế nào?
Bạn xử lý sự cố một exchange có binding sai khiến message không đến queue dự kiến ra sao?
Nếu ready messages tăng liên tục nhưng consumer vẫn kết nối, bạn sẽ điều tra theo thứ tự nào?
Nếu unacknowledged messages tăng cao sau khi triển khai phiên bản mới, bạn sẽ khoanh vùng nguyên nhân như thế nào?
Khi publisher liên tục nhận confirm chậm hoặc timeout, bạn sẽ kiểm tra những lớp nào?
Khi tỷ lệ redelivery tăng đột biến, bạn sẽ phân biệt lỗi ứng dụng với lỗi hạ tầng ra sao?
Nếu cluster quorum queue mất đa số node trong giờ cao điểm, bạn sẽ ưu tiên hành động nào và vì sao?
Nếu broker kích hoạt disk alarm khi còn rất nhiều thông điệp đang chờ, bạn sẽ xử lý an toàn như thế nào?
Khi một node hỏng giữa lúc consumer đang ack, bạn sẽ kiểm tra rủi ro mất hoặc lặp xử lý ra sao?
Nếu một message lỗi liên tục làm nghẽn queue đơn hàng, bạn sẽ cô lập và khôi phục luồng xử lý thế nào?
Khi phiên bản mới thay đổi schema message khiến consumer cũ không đọc được, bạn sẽ tổ chức rollback như thế nào?
Bạn triển khai thay đổi tên exchange hoặc routing key mà vẫn duy trì tương thích với phiên bản cũ ra sao?
Nếu người dùng nhận hai email xác nhận từ cùng một sự kiện, bạn sẽ truy dấu và sửa cơ chế nào?
Bạn thiết kế gửi lệnh thanh toán để một message bị giao lại không tạo hai giao dịch như thế nào?
Khi dịch vụ downstream ngừng hoạt động nhiều giờ, bạn sẽ chọn retry, lưu backlog và cảnh báo theo tiêu chí nào?
Bạn giữ thứ tự cập nhật trạng thái của cùng một đơn hàng khi nhiều instance consumer chạy song song như thế nào?
Bạn xác nhận toàn bộ thông điệp quan trọng đã được xử lý sau một sự cố broker kéo dài ra sao?
