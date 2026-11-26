Câu 1. `RabbitTemplate.convertAndSend(exchange, routingKey, payload)` thực hiện thao tác nào?
A. Gửi trực tiếp payload vào queue và bỏ qua exchange.
B. Chờ consumer xử lý xong payload mới trả kết quả.
C. Chuyển payload thành message rồi gửi tới exchange theo routing key.
D. Tạo queue mới từ routing key trước khi gửi message.
Đáp án đúng: C

Câu 2. Khi gửi vào default exchange có tên rỗng, routing key thường là gì?
A. Tên queue đích mà broker đã tự binding sẵn.
B. Tên consumer đang nhận message của queue đích.
C. Tên kết nối TCP từ producer tới RabbitMQ broker.
D. Tên bean `RabbitTemplate` được tạo bởi Spring.
Đáp án đúng: A

Câu 3. Với direct exchange, thông điệp được định tuyến dựa trên yếu tố nào?
A. Thứ tự queue được khai báo trong ứng dụng Spring.
B. Routing key khớp một phần prefix của binding key.
C. Routing key khớp chính xác binding key của queue.
D. Số lượng consumer đang đọc từng queue liên kết.
Đáp án đúng: C

Câu 4. Trong topic exchange, wildcard `*` trong binding key có ý nghĩa gì?
A. Khớp chuỗi ký tự tự do có thể chứa nhiều dấu chấm.
B. Khớp từ không đến nhiều từ phân cách bằng dấu chấm.
C. Khớp đúng một từ được phân cách bởi dấu chấm.
D. Khớp mọi routing key có cùng tiền tố trước dấu chấm.
Đáp án đúng: C

Câu 5. Với topic exchange, binding `orders.#` có thể nhận routing key nào?
A. Chỉ nhận đúng `orders.created` một tầng phía sau.
B. Chỉ nhận key có đúng một dấu chấm trong tên.
C. Chỉ nhận key bằng `#` do producer trực tiếp gửi.
D. Nhận `orders` hoặc các key bắt đầu `orders.`.
Đáp án đúng: D

Câu 6. Fanout exchange phân phối một message đến các queue như thế nào?
A. Gửi một bản sao theo vòng lặp giữa các queue.
B. Chỉ gửi tới queue có consumer kết nối sớm nhất.
C. Chỉ gửi tới queue có binding key trùng routing key.
D. Gửi bản sao tới từng queue được binding với exchange.
Đáp án đúng: D

Câu 7. Vai trò của binding giữa exchange và queue trong RabbitMQ là gì?
A. Giữ bản sao message trong một bảng của database.
B. Thiết lập quan hệ định tuyến từ exchange đến queue.
C. Thiết lập một connection riêng cho từng producer.
D. Thay consumer acknowledgment bằng publisher confirm.
Đáp án đúng: B

Câu 8. Khi khai báo queue durable, điều nào đúng về tính bền vững?
A. Consumer không cần kết nối lại sau khi broker vừa restart.
B. Queue có thể tồn tại qua restart, chưa đủ đảm bảo message.
C. Mọi message trong queue tự được ack ngay khi broker restart.
D. Mọi message gửi tới queue đều chuyển sang delivery transient.
Đáp án đúng: B

Câu 9. Muốn message có khả năng sống sót khi broker khởi động lại, cấu hình nào phù hợp?
A. Dùng temporary queue và giữ một consumer luôn kết nối.
B. Dùng queue non-durable với message gửi bằng fanout exchange.
C. Dùng queue auto-delete và đặt prefetch số lượng lớn.
D. Dùng queue durable và message delivery mode persistent.
Đáp án đúng: D

Câu 10. Trong Spring AMQP, `RabbitAdmin` có thể hỗ trợ bước nào khi startup?
A. Đồng bộ toàn bộ backlog message sang queue DLQ.
B. Ghi lại transaction ở mọi database của consumer.
C. Khai báo queue, exchange và binding đã cấu hình.
D. Tự xác nhận từng message thay listener trong ứng dụng.
Đáp án đúng: C

Câu 11. Annotation `@RabbitListener(queues = "tasks.in")` khai báo điều gì?
A. Cấu hình `RabbitTemplate` kết nối server `tasks.in`.
B. Tạo publisher gửi message vào exchange `tasks.in`.
C. Đăng ký method xử lý message từ queue `tasks.in`.
D. Gắn routing key mặc định cho tất cả exchange.
Đáp án đúng: C

Câu 12. Producer gửi một Java object, consumer muốn nhận object tương ứng. Cần đồng bộ gì?
A. Cấu hình cùng tên handler bean cho hai ứng dụng.
B. Cấu hình cùng số prefetch cho producer và consumer.
C. Cấu hình cùng thời gian timeout của hai listener.
D. Cấu hình message converter và định dạng payload hai bên.
Đáp án đúng: D

Câu 13. Thành phần nào thường dùng để cấu hình consumer concurrency và ack mode?
A. `BindingBuilder` được gọi lúc khai báo exchange.
B. `CorrelationData` được truyền khi publisher gửi.
C. `RabbitTemplate` được cấu hình để gửi message.
D. `SimpleRabbitListenerContainerFactory` của listener.
Đáp án đúng: D

Câu 14. Với container `AcknowledgeMode.AUTO`, listener xử lý thành công thì điều gì xảy ra?
A. Container gửi acknowledgment sau khi listener hoàn tất.
B. Container chỉ xác nhận khi producer nhận publisher confirm.
C. Broker chờ ứng dụng gọi `channel.basicAck()` thủ công.
D. Broker xác nhận message ngay khi bắt đầu TCP handshake.
Đáp án đúng: A

Câu 15. Ở chế độ `AcknowledgeMode.MANUAL`, sau xử lý thành công nên làm gì?
A. Gọi `basicAck(deliveryTag, false)` trên channel phù hợp.
B. Gọi `basicRecover` để yêu cầu gửi lại message hiện tại.
C. Gọi `basicPublish` với routing key ban đầu của message.
D. Gọi `basicCancel` để đóng consumer trước khi xác nhận.
Đáp án đúng: A

Câu 16. Khi gọi `basicNack(deliveryTag, false, false)`, broker thường xử lý gì?
A. Tự đảm bảo lưu message sang database của consumer.
B. Từ chối rồi luôn đưa message trở lại đầu queue gốc.
C. Tự phát publisher confirm cho message vừa tiêu thụ.
D. Từ chối không requeue; có thể dead-letter nếu đã cấu hình.
Đáp án đúng: D

Câu 17. Đặt `defaultRequeueRejected=false` cho listener container có ý nghĩa gì?
A. Mọi producer sẽ tự ngừng publish đến cùng exchange.
B. Message bị reject do lỗi sẽ không mặc định requeue.
C. Message listener xử lý thành công sẽ không được ack.
D. Toàn bộ queue sẽ tự chuyển sang chế độ auto-delete.
Đáp án đúng: B

Câu 18. `AmqpRejectAndDontRequeueException` thường dùng trong trường hợp nào?
A. Yêu cầu reject mà không requeue một message lỗi.
B. Yêu cầu xác nhận thủ công message đã được xử lý.
C. Yêu cầu rollback giao dịch ở mọi cơ sở dữ liệu.
D. Yêu cầu gửi lại message với routing key vừa nhận.
Đáp án đúng: A

Câu 19. Publisher confirm ACK từ RabbitMQ biểu thị điều gì?
A. Broker đã chấp nhận publish theo cơ chế confirm.
B. Message đã được ghi vào database của ứng dụng.
C. Consumer đã commit thành công tác vụ nghiệp vụ.
D. Message đã đến đúng queue dù không có binding nào.
Đáp án đúng: A

Câu 20. Muốn phát hiện message không được route đến queue nào, producer cần gì?
A. Chỉ kiểm tra publisher confirm có trạng thái ACK.
B. Bật mandatory và xử lý returned message callback.
C. Chỉ cấu hình prefetch count trên listener container.
D. Chỉ tăng delivery mode lên persistent cho message.
Đáp án đúng: B

Câu 21. Dùng `CorrelationData` trong publisher confirm chủ yếu để làm gì?
A. Đối chiếu phản hồi confirm với lượt publish tương ứng.
B. Thay thế routing key trong binding của topic exchange.
C. Chuyển đổi payload object sang định dạng JSON mặc định.
D. Xác thực danh tính user đang đọc queue tại consumer.
Đáp án đúng: A

Câu 22. Do mất kết nối trước ack, cùng một message có thể được giao lại. Receiver nên làm gì?
A. Bỏ qua mọi message có cờ redelivered dù chưa từng xử lý.
B. Tin mỗi lần broker giao message đều chỉ xảy ra đúng một lần.
C. Xử lý idempotent dựa trên message ID hoặc khóa nghiệp vụ.
D. Chỉ tăng concurrency để tránh hoàn toàn việc giao trùng.
Đáp án đúng: C

Câu 23. Khi lỗi downstream tạm thời, chiến lược retry nào hợp lý?
A. Retry giới hạn với backoff, có lối thoát cho message lỗi.
B. Retry liên tục không giới hạn ngay trên cùng một consumer.
C. Đặt TTL về không để vô hiệu hóa toàn bộ cơ chế redelivery.
D. Requeue ngay lập tức để mọi consumer nhận lại thật nhanh.
Đáp án đúng: A

Câu 24. Với payload lỗi vĩnh viễn, cách xử lý nào giúp tránh vòng lặp giao lại?
A. Bỏ publisher confirm để broker tự loại message lỗi.
B. Không requeue, đưa qua luồng xử lý lỗi hoặc DLQ.
C. Luôn requeue liên tục mà không lưu thông tin chẩn đoán.
D. Tăng số consumer để cùng xử lý lại payload hỏng.
Đáp án đúng: B

Câu 25. Cấu hình `x-dead-letter-exchange` trên queue nhằm mục đích gì?
A. Chỉ định exchange giữ tất cả message trước khi routing.
B. Chỉ định exchange nhận message bị dead-letter từ queue.
C. Chỉ định exchange quản lý connection pool của producer.
D. Chỉ định exchange sẽ tự xác nhận mọi consumer message.
Đáp án đúng: B

Câu 26. Khi message hết TTL trong queue có DLX được cấu hình, điều gì có thể xảy ra?
A. Message tự được đưa ngược lại producer với confirm ACK.
B. Message bắt buộc quay lại đúng queue gốc ngay lập tức.
C. Message luôn tự được retry bởi `@RabbitListener` của app.
D. Message có thể được dead-letter qua DLX đã chỉ định.
Đáp án đúng: D

Câu 27. Header `x-death` được RabbitMQ bổ sung trong hoàn cảnh nào?
A. Khi listener nhận message lần đầu không cần reject.
B. Khi producer tạo request HTTP để publish message.
C. Khi message đã trải qua cơ chế dead-letter ở broker.
D. Khi broker tạo TCP connection mới cho consumer.
Đáp án đúng: C

Câu 28. Trong RabbitMQ, `prefetchCount` chủ yếu kiểm soát điều gì?
A. Số exchange được phép binding với một queue duy nhất.
B. Số byte tối đa trong mỗi frame AMQP của message.
C. Số message chưa ack được cấp trước cho consumer.
D. Số lần producer có thể tự retry sau publisher confirm.
Đáp án đúng: C

Câu 29. Khi tăng concurrency cho listener ghi database, nguyên tắc nào nên áp dụng?
A. Đổi queue sang auto-delete để mở thêm nhiều consumer.
B. Cân theo năng lực database và số message đang xử lý.
C. Giữ vô hạn message unacked để cân bằng các worker.
D. Tăng đến giới hạn CPU, không cần xét độ trễ của database.
Đáp án đúng: B

Câu 30. Một transaction RabbitMQ và transaction database riêng có bảo đảm atomic không?
A. Có; `@Transactional` luôn tạo distributed transaction.
B. Có; RabbitMQ tự rollback database khi broker có lỗi.
C. Có; publisher confirm đồng nghĩa DB đã được commit.
D. Không; cần cơ chế như outbox để đồng bộ hai hệ thống.
Đáp án đúng: D

Câu 31. Để kiểm chứng retry, reject và DLQ của `@RabbitListener`, bài test nào phù hợp?
A. Chỉ mock `RabbitTemplate` rồi kiểm tra annotation.
B. Chạy RabbitMQ thật, tạo lỗi và kiểm tra ack cùng DLQ.
C. Chỉ so file cấu hình của Spring trước khi khởi động.
D. Chỉ đo thời gian startup mà không gửi message lỗi.
Đáp án đúng: B

Câu 32. Khi vận hành Spring AMQP, nhóm số liệu nào giúp phát hiện backlog và lỗi?
A. Queue depth, unacked, redelivery, DLQ và consumer rate.
B. Tốc độ publish, số exchange, binding và thời gian uptime.
C. Thread listener, heap, network RTT và số socket đang mở.
D. Số kết nối, heartbeat, publisher confirms và CPU broker.
Đáp án đúng: A
