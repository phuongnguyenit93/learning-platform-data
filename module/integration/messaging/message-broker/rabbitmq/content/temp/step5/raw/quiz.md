Câu 1. Trong RabbitMQ, exchange chọn queue đích cho message theo nguyên tắc nào?
A. Queue tự chọn message dựa trên số consumer đang chạy.
B. Consumer đăng ký queue nào thì exchange gửi thẳng tới đó.
C. Kiểu exchange và binding quyết định các queue được nhận.
D. Node trong cluster chọn queue theo mức tải CPU hiện tại.
Đáp án đúng: C

Câu 2. Với direct exchange, điều kiện nào làm một binding khớp với message?
A. Routing key chứa một phần bất kỳ của binding key.
B. Routing key bằng chính xác binding key của queue.
C. Routing key khớp mẫu `*` và `#` trong binding key.
D. Routing key có tiền tố giống với binding key.
Đáp án đúng: B

Câu 3. Trong topic exchange, dấu `*` và `#` trong binding key có ý nghĩa gì?
A. `*` khớp tiền tố; `#` khớp hậu tố routing key.
B. `*` khớp nhiều từ; `#` chỉ khớp đúng một từ.
C. `*` khớp một từ; `#` khớp không hoặc nhiều từ.
D. `*` khớp một ký tự; `#` khớp nhiều ký tự.
Đáp án đúng: C

Câu 4. Fanout exchange định tuyến một message được publish như thế nào?
A. Đến queue có độ ưu tiên cao nhất trong exchange.
B. Đến các queue có binding key khớp mẫu topic.
C. Đến các queue có binding key giống routing key.
D. Đến tất cả queue đang binding với exchange.
Đáp án đúng: D

Câu 5. Khi publish qua default exchange (tên rỗng), routing key nào đưa message vào queue `jobs`?
A. Routing key `worker`, trùng tên consumer nhận.
B. Routing key `jobs`, trùng tên queue cần nhận.
C. Routing key `/`, trùng tên virtual host.
D. Routing key `default`, trùng loại exchange.
Đáp án đúng: B

Câu 6. Nếu `mandatory=true` nhưng không queue nào được định tuyến, dấu hiệu nào báo message không định tuyến được?
A. Một queue tạm được broker tạo để giữ message.
B. Một binding phù hợp được broker tạo tự động.
C. Message được trả về qua sự kiện `basic.return`.
D. Message được chờ cho đến khi xuất hiện queue.
Đáp án đúng: C

Câu 7. Publisher confirm xác nhận điều gì trong quá trình gửi message?
A. Mọi consumer đã nhận bản sao của message.
B. Consumer đã hoàn tất xử lý nội dung message.
C. Broker đã tiếp nhận trách nhiệm đối với message.
D. Ứng dụng nhận đã gửi ack về publisher.
Đáp án đúng: C

Câu 8. Với RabbitMQ Java client, thao tác nào bật publisher confirms trên channel?
A. Gọi `confirmSelect` trước khi gửi các message.
B. Gọi `basicAck` trước khi gửi các message.
C. Gọi `basicRecover` trước khi gửi các message.
D. Gọi `basicQos` trước khi gửi các message.
Đáp án đúng: A

Câu 9. Trong manual acknowledgement, lệnh nào xác nhận riêng một delivery đã xử lý thành công?
A. `basicAck(deliveryTag, false)` trên channel nhận.
B. `basicAck(deliveryTag, true)` trên channel nhận.
C. `basicNack(deliveryTag, false, true)` trên channel nhận.
D. `basicReject(deliveryTag, true)` trên channel nhận.
Đáp án đúng: A

Câu 10. Với queue đã cấu hình dead-letter exchange, thao tác nào đẩy một delivery lỗi sang dead-letter?
A. Gọi `basicNack` với `requeue=true` cho delivery.
B. Gọi `basicRecover` với `requeue=true` cho delivery.
C. Gọi `basicNack` với `requeue=false` cho delivery.
D. Gọi `basicAck` với `multiple=false` cho delivery.
Đáp án đúng: C

Câu 11. Consumer mất kết nối trước khi ack manual; RabbitMQ thường xử lý delivery đó ra sao?
A. Requeue message để có thể giao lại cho consumer.
B. Chuyển message sang queue tự tạo cho lần chạy mới.
C. Giữ message đến khi consumer cũ kết nối lại.
D. Xóa message vì coi consumer đã hoàn tất xử lý.
Đáp án đúng: A

Câu 12. Để xử lý an toàn khi một message có thể được giao lại, consumer nên làm gì?
A. Bật publisher confirm để loại bỏ mọi lần giao lại.
B. Bật auto-ack để ngăn message xuất hiện trùng.
C. Tăng prefetch để mỗi message chỉ được giao một lần.
D. Lưu khóa idempotency để nhận biết lần xử lý trùng.
Đáp án đúng: D

Câu 13. Cặp cấu hình nào phù hợp để message tồn tại qua lần khởi động lại broker thông thường?
A. Queue durable và message đặt persistent.
B. Queue auto-delete và message đặt persistent.
C. Queue transient và message đặt persistent.
D. Queue exclusive và message đặt transient.
Đáp án đúng: A

Câu 14. Thiết kế nào phù hợp cho retry có trì hoãn sau khi consumer xử lý thất bại?
A. Bật auto-ack rồi gửi lại message ngay không giới hạn.
B. Cho message qua queue có TTL và DLX trỏ về queue xử lý.
C. Requeue ngay cùng message liên tục không giới hạn.
D. Đóng channel sau lỗi để broker lập tức giao lại.
Đáp án đúng: B

Câu 15. Tình huống nào có thể khiến RabbitMQ dead-letter một message khi queue có DLX?
A. Broker gửi publisher confirm cho message mới nhận.
B. Publisher gửi message nhưng exchange thiếu binding.
C. Consumer ack thành công sau khi đã xử lý message.
D. Message hết TTL trong queue trước khi được xử lý.
Đáp án đúng: D

Câu 16. Đặc điểm cốt lõi nào đúng với RabbitMQ quorum queue?
A. Sao chép log giữa các thành viên theo đồng thuận Raft.
B. Sao chép message bằng chính sách classic mirroring.
C. Lưu message duy nhất trên node kết nối publisher.
D. Đồng bộ message bằng cách đối chiếu binding key.
Đáp án đúng: A

Câu 17. Quorum queue có ba thành viên cần bao nhiêu thành viên hoạt động để duy trì đa số?
A. Cả ba thành viên của nhóm quorum còn sẵn sàng.
B. Một thành viên của nhóm quorum còn sẵn sàng.
C. Hai consumer của queue đang cùng hoạt động.
D. Hai thành viên của nhóm quorum còn sẵn sàng.
Đáp án đúng: D

Câu 18. Trong RabbitMQ cluster, phát biểu nào đúng về sao chép message?
A. Mỗi binding tự sao chép message đến mọi node.
B. Mỗi exchange đều giữ bản sao trên mọi node.
C. Mọi classic queue đều sao chép lên tất cả node.
D. Quorum queue sao chép dữ liệu qua các thành viên.
Đáp án đúng: D

Câu 19. Đặt `prefetch=10` cho một consumer nhằm kiểm soát điều gì?
A. Số message tối đa được publish trong một lượt.
B. Số queue tối đa được khai báo trên connection.
C. Số delivery chưa ack có thể cấp cho consumer.
D. Số binding tối đa được khai báo cho một queue.
Đáp án đúng: C

Câu 20. Khi RabbitMQ kích hoạt memory alarm, hành vi nào có thể xảy ra?
A. Chuyển các queue sang quorum để giải phóng RAM.
B. Tăng prefetch của consumer để giảm lượng RAM sử dụng.
C. Chặn publisher tạm thời đến khi áp lực RAM giảm.
D. Xóa message persistent để nhanh chóng giải phóng RAM.
Đáp án đúng: C

Câu 21. Virtual host (vhost) hỗ trợ quản lý RabbitMQ theo cách nào?
A. Giới hạn mỗi vhost chỉ có một exchange và một queue.
B. Phân tách không gian tên và quyền truy cập tài nguyên.
C. Tạo một JVM riêng cho các consumer trong vhost.
D. Tạo một cluster riêng cho từng publisher trong vhost.
Đáp án đúng: B

Câu 22. Khi client kết nối RabbitMQ qua TLS và kiểm tra chứng chỉ máy chủ, lợi ích nào đạt được?
A. Kết nối được mã hóa và xác thực danh tính máy chủ.
B. Không cần quản lý user, password hay permission nữa.
C. Message tự động có bản sao trên một node dự phòng.
D. Client tự nhận quyền publish vào toàn bộ các queue.
Đáp án đúng: A

Câu 23. Trong Spring AMQP, thành phần nào thường dùng để publish message vào exchange?
A. `QueueBuilder` gửi message theo routing key.
B. `RabbitTemplate` gửi message theo routing key.
C. `SimpleRabbitListenerContainerFactory` gửi message.
D. `@RabbitListener` gửi message theo routing key.
Đáp án đúng: B

Câu 24. Annotation nào của Spring AMQP thường gắn với phương thức consumer nhận message?
A. `@EventListener` đăng ký phương thức xử lý message.
B. `@RabbitListener` đăng ký phương thức xử lý message.
C. `@Scheduled` đăng ký phương thức xử lý message.
D. `@Bean` đăng ký phương thức xử lý message.
Đáp án đúng: B

Câu 25. Khi Spring AMQP listener dùng acknowledge mode MANUAL, thao tác nào dùng để ack thành công?
A. Gọi `basicAck` với deliveryTag của message đã xử lý.
B. Gọi `confirmSelect` với deliveryTag của message đã xử lý.
C. Gọi `basicQos` với deliveryTag của message đã xử lý.
D. Gọi `basicPublish` với deliveryTag của message đã xử lý.
Đáp án đúng: A

Câu 26. Cách nào tránh vòng lặp vô hạn với message luôn gây lỗi trong consumer?
A. Bật auto-ack cho mọi lỗi để có thể gửi lại message.
B. Luôn requeue ngay message lỗi để thử lại không giới hạn.
C. Tăng prefetch liên tục cho đến khi consumer xử lý được.
D. Giới hạn lượt retry rồi chuyển message sang dead-letter queue.
Đáp án đúng: D

Câu 27. Khi nhiều consumer xử lý song song một queue, điều nào cần lưu ý về thứ tự?
A. Broker chờ tất cả consumer rảnh rồi mới giao.
B. Mọi message luôn hoàn tất đúng thứ tự publish.
C. Mỗi consumer sẽ nhận một bản sao của mọi message.
D. Thứ tự hoàn tất có thể khác thứ tự vào queue.
Đáp án đúng: D

Câu 28. Bộ chỉ số nào giúp theo dõi queue đang tồn đọng và tốc độ xử lý?
A. Tên queue, số binding và kích thước file log.
B. Số ready, unacked, consumer và tốc độ xử lý.
C. Tên vhost, số exchange và tên connection.
D. Phiên bản client, số plugin và số file cấu hình.
Đáp án đúng: B
