Câu 01. Trong Kafka consumer group, offset được commit cho một partition biểu thị vị trí nào?
A. Offset kế tiếp mà consumer sẽ đọc khi khôi phục vị trí
B. Offset lớn nhất của các partition trong consumer group
C. Offset của record cuối được trả về nhưng chưa xử lý
D. Offset đầu tiên của topic sau mỗi đợt consumer poll
Đáp án đúng: A

Câu 02. Khi group chưa có committed offset hợp lệ, `auto.offset.reset=earliest` có tác dụng gì?
A. Chọn bản ghi mới nhất đã ghi của partition để bắt đầu
B. Chọn offset nhỏ nhất đã commit bởi group khác
C. Chọn bản ghi còn lưu sớm nhất của partition để bắt đầu
D. Chọn offset của lần poll gần nhất tại consumer instance
Đáp án đúng: C

Câu 03. Khi đặt `enable.auto.commit=false` cho Kafka consumer, điều gì thay đổi?
A. Consumer không được gọi Kafka poll cho đến khi ack
B. Broker tự commit offset vào log sau mỗi lần fetch
C. Kafka client không tự commit offset định kỳ theo cấu hình
D. Spring Kafka container ngừng commit offset sau xử lý
Đáp án đúng: C

Câu 04. Trong Spring Kafka, AckMode.RECORD thường commit offset vào thời điểm nào?
A. Sau mỗi record được listener xử lý thành công
B. Chỉ khi listener gọi acknowledgment trực tiếp
C. Sau khi toàn bộ records từ poll đã xử lý xong
D. Ngay trước mỗi lần gọi listener nhận message
Đáp án đúng: A

Câu 05. Với AckMode.BATCH trong record listener, thời điểm commit thông thường là gì?
A. Sau khi nhận từng record trước khi xử lý
B. Sau khi mỗi record được xác nhận thủ công
C. Sau khi toàn bộ các partition kết thúc rebalance
D. Sau khi xử lý xong các records từ một lần poll
Đáp án đúng: D

Câu 06. Trong AckMode.MANUAL, sau khi listener gọi `acknowledge()`, commit thường được quản lý thế nào?
A. Commit trước khi listener xử lý record tiếp theo
B. Commit định kỳ theo cấu hình auto commit của Kafka client
C. Commit ngay tại lệnh acknowledge cho từng record
D. Commit theo quy tắc batch sau khi hoàn tất các ack cần thiết
Đáp án đúng: D

Câu 07. Với AckMode.MANUAL_IMMEDIATE, gọi `acknowledge()` trên consumer thread sẽ có hành vi nào?
A. Chuyển ack thành giao dịch producer đang mở
B. Dồn ack lại và commit khi kết thúc lần poll
C. Commit offset tại thời điểm lời gọi acknowledge
D. Chỉ đánh dấu record để retry trước lúc commit
Đáp án đúng: C

Câu 08. Với thao tác ghi dữ liệu cần hoàn tất trước khi xác nhận, lựa chọn ack nào an toàn hơn?
A. Gọi acknowledgment ngay trước khi bắt đầu ghi dữ liệu
B. Gọi acknowledgment sau khi side effect đã bền vững
C. Commit offset từ callback khi chưa biết kết quả ghi
D. Bật auto-commit dù quá trình ghi còn trong hàng đợi
Đáp án đúng: B

Câu 09. Khi dùng `asyncAcks` trong Spring Kafka, điều nào đúng với các ack cùng một lần poll?
A. Ack khác thứ tự; commit chờ các khoảng trống được lấp
B. Chuyển chế độ ack thành Kafka auto commit định kỳ
C. Tạo giao dịch mới cho từng record ack đến muộn
D. Cho phép commit vượt qua record chưa ack theo offset cao
Đáp án đúng: A

Câu 10. Khi một listener gọi `Acknowledgment.nack()` theo điều kiện hỗ trợ, mục tiêu nào phù hợp?
A. Chuyển record lỗi thành JSON rồi ghi vào DLT
B. Xóa record lỗi khỏi topic trước khi tiếp tục xử lý
C. Seek để các record chưa xử lý được đọc lại sau khoảng chờ
D. Commit offset của các record chưa xử lý vào group
Đáp án đúng: C

Câu 11. Trong cùng một consumer group, một partition Kafka tại thời điểm ổn định được gán ra sao?
A. Một consumer trong group giữ quyền xử lý partition đó
B. Các consumer trong group đều nhận bản sao partition
C. Hai consumer đồng thời xử lý partition để tăng throughput
D. Một consumer bất kỳ từ group khác sở hữu partition đó
Đáp án đúng: A

Câu 12. Một topic có 6 partitions, listener container concurrency=10 và chỉ subscribe topic này: điều gì thường xảy ra?
A. Tối đa 6 consumer con có partition được giao để đọc
B. Container tự tăng số partition của topic lên 10
C. Mỗi consumer đọc cả 6 partitions để xử lý song song
D. Cả 10 consumer đều chia chung một partition để đọc
Đáp án đúng: A

Câu 13. Kafka consumer setting `max.poll.records` chủ yếu giới hạn điều gì?
A. Số producer request có thể gửi trong mỗi transaction
B. Số record tối đa tồn tại trong một Kafka topic
C. Số partitions được phân công cho một consumer
D. Số record tối đa được trả từ một lần gọi poll
Đáp án đúng: D

Câu 14. Khi xử lý quá lâu không gọi `poll()`, cấu hình nào đặc biệt liên quan đến rebalance?
A. `fetch.max.wait.ms` giới hạn khoảng cách giữa các lần poll
B. `linger.ms` giới hạn khoảng cách giữa các lần poll
C. `max.poll.interval.ms` giới hạn thời gian giữa các poll
D. `delivery.timeout.ms` giới hạn khoảng cách giữa các lần poll
Đáp án đúng: C

Câu 15. Thông số `session.timeout.ms` trong group protocol dựa trên heartbeat giúp kiểm soát gì?
A. Thời gian Kafka lưu dữ liệu trên từng partition
B. Thời gian chờ heartbeat trước khi member bị coi là mất
C. Thời gian retry một record lỗi trước khi chuyển DLT
D. Thời gian tối đa để producer đợi xác nhận từ broker
Đáp án đúng: B

Câu 16. Khi cấu hình `group.instance.id` cho consumer, lợi ích đáng chú ý là gì?
A. Bật quản lý Kafka transactions giữa các member
B. Static membership giảm rebalance khi consumer khởi động lại
C. Thay consumer group id bằng partition id cho mỗi record
D. Cho phép nhiều consumer cùng đọc một partition trong group
Đáp án đúng: B

Câu 17. So với eager rebalance, `CooperativeStickyAssignor` có đặc điểm gì?
A. Thu hồi đồng thời các partitions ở mỗi thành viên
B. Chuyển group offsets sang topic retry khi có rebalance
C. Giữ các record trong bộ nhớ thay vì đọc từ Kafka log
D. Có thể thu hồi partitions từng phần để giảm gián đoạn xử lý
Đáp án đúng: D

Câu 18. Muốn dọn state khi partition bị revoke và khởi tạo lại khi được assign, callback nào hữu ích?
A. `KafkaTemplate` đăng ký callbacks cho partition assignment
B. `DeadLetterPublishingRecoverer` đăng ký callbacks group member
C. `Acknowledgment` thực hiện callbacks trước và sau rebalance
D. `ConsumerAwareRebalanceListener` nhận revoke/assign callbacks
Đáp án đúng: D

Câu 19. Trong Spring Kafka, component nào thường kết hợp backoff với logic retry/recovery cho record listener?
A. `RecordFilterStrategy` xử lý lỗi record cùng retry và recoverer
B. `KafkaTransactionManager` xử lý lỗi record cùng retry và recoverer
C. `DefaultErrorHandler` xử lý lỗi record cùng retry và recoverer
D. `KafkaTemplate` xử lý lỗi listener cùng retry và recoverer
Đáp án đúng: C

Câu 20. Với `FixedBackOff(1000L, 2L)` trong error handler, có bao nhiêu lần retry sau lần xử lý đầu thất bại?
A. Một lần retry sau lần xử lý đầu, chờ hai giây
B. Hai lần retry sau lần đầu, cách nhau khoảng một giây
C. Ba lần retry gồm cả lần gọi đầu tiên
D. Không retry, chỉ ghi lỗi vào Dead Letter Topic
Đáp án đúng: B

Câu 21. Sau khi retry cạn, component nào thường gửi record lỗi sang Dead Letter Topic?
A. `DeadLetterPublishingRecoverer` xuất bản record lỗi tới DLT
B. `ConsumerAwareRebalanceListener` gửi record lỗi tới DLT
C. `KafkaListenerEndpointRegistry` gửi record lỗi tới DLT
D. `KafkaTransactionManager` xuất bản record lỗi tới DLT
Đáp án đúng: A

Câu 22. Với cấu hình mặc định của `DeadLetterPublishingRecoverer`, đích DLT thường như thế nào?
A. Topic gốc thêm `.error`, buộc chuyển về partition số 0
B. Topic gốc thêm `.DLT`, giữ partition có cùng số
C. Topic gốc thêm `.retry`, phân phối lại partition ngẫu nhiên
D. Topic lỗi lưu chung vào `__consumer_offsets` mặc định
Đáp án đúng: B

Câu 23. Khi record được publish sang DLT, header nào giúp điều tra nguyên nhân và nơi phát sinh lỗi?
A. Chỉ có group.id mới và số consumer đang active
B. Chỉ có TLS certificates và request latency của producer
C. Chỉ có tên transaction manager và SQL connection id
D. Thông tin topic/partition/offset gốc và exception được đính kèm
Đáp án đúng: D

Câu 24. Trong Spring Kafka, `@RetryableTopic` thường triển khai loại retry nào?
A. Non-blocking retry qua retry topics trước khi tới DLT
B. Retry bằng cách khóa Kafka partition trong transaction mới
C. Retry bằng cách commit offset và bỏ record lỗi không phát lại
D. Blocking retry ngay trong thread poll cho tới khi hết backoff
Đáp án đúng: A

Câu 25. Với cấu hình `@RetryableTopic`, annotation nào có thể xử lý record đã chuyển vào DLT?
A. `@TopicPartition` đăng ký method nhận exception DLT
B. `@DltHandler` định nghĩa method xử lý message trong DLT
C. `@KafkaHandler` tự xác nhận message DLT qua transactions
D. `@RetryListener` định nghĩa method nhận riêng message DLT
Đáp án đúng: B

Câu 26. Khi dùng retry topics không chặn, yêu cầu thứ tự xử lý theo key có rủi ro nào?
A. Các record cùng key bị giữ ở topic gốc tới hết retry
B. Broker sẽ khóa các partition liên quan đến record retry
C. Consumer group sẽ phát lại toàn bộ topic theo thứ tự cũ
D. Record đến sau có thể vượt record đang retry
Đáp án đúng: D

Câu 27. Nếu deserialization thất bại trước khi gọi `@KafkaListener`, cấu hình nào hỗ trợ chuyển lỗi vào error handling?
A. `Acknowledgment` tạo payload mặc định cho record lỗi
B. `KafkaTransactionManager` biến lỗi parse thành retry topic
C. Dùng `ErrorHandlingDeserializer` để lỗi được recover
D. `JsonSerializer` tự sửa bytes hỏng trước khi listener chạy
Đáp án đúng: C

Câu 28. Khi biết exception là lỗi dữ liệu không phục hồi được, API nào của `DefaultErrorHandler` phù hợp?
A. `clearThreadState()` xóa record lỗi khỏi Kafka topic
B. `setCommitRecovered(false)` ép retry thêm sau mỗi lỗi
C. `addNotRetryableExceptions(...)` đánh dấu lỗi bỏ retry
D. `setAckAfterHandle(true)` tăng số lần retry trong backoff
Đáp án đúng: C

Câu 29. Với một poison pill liên tục làm listener lỗi, cách vận hành phù hợp nhất là gì?
A. Tăng số retries vô hạn để record có thể tự hết lỗi
B. Tắt cảnh báo DLT để tránh phát sinh alert liên tục
C. Commit record lỗi như thành công mà không giữ dấu vết
D. Retry có giới hạn, DLT và cảnh báo lỗi kéo dài
Đáp án đúng: D

Câu 30. Khi processing thành công nhưng consumer chết trước khi commit offset, điều gì có thể xảy ra?
A. Broker xóa record ngay sau khi handler chạy thành công
B. Có thể nhận lại record, cần chống xử lý trùng
C. Những record sau được chuyển vào DLT vì group rebalance
D. Offset đã commit nhờ giao dịch của listener
Đáp án đúng: B

Câu 31. Bật `enable.idempotence=true` ở Kafka producer giải quyết vấn đề nào trong phạm vi Kafka?
A. Tự gom offset của consumer vào transaction gửi record
B. Hạn chế record trùng từ lần gửi retry của producer
C. Khử trùng event đã xử lý ở các database bên ngoài Kafka
D. Cấm consumer nhận lại record khi offset chưa commit
Đáp án đúng: B

Câu 32. Producer cấu hình `acks=all` mong đợi xác nhận từ đâu?
A. Leader chỉ xác nhận ngay khi nhận request từ producer
B. Mỗi replica nằm ngoài ISR phải xác nhận trước khi ack
C. Leader đợi các bản sao trong ISR xác nhận việc ghi
D. Consumer group xác nhận đọc record rồi producer mới ack
Đáp án đúng: C

Câu 33. Khi dùng `acks=all`, setting broker/topic nào tăng ràng buộc số replica còn đồng bộ để chấp nhận ghi?
A. `max.poll.records` quy định ngưỡng ISR cần thiết
B. `auto.offset.reset` quy định ngưỡng ISR cần thiết
C. `min.insync.replicas` quy định ngưỡng ISR cần thiết
D. `default.replication.factor` điều khiển số records mỗi poll
Đáp án đúng: C

Câu 34. Với Kafka producer transactions, `transactional.id` giúp cơ chế nào?
A. Bật việc ghi vào SQL database cùng broker theo XA
B. Đặt consumer group id để gắn offset vào các transaction
C. Buộc topic chỉ có một partition trong suốt giao dịch
D. Fencing producer cũ dùng cùng transactional.id
Đáp án đúng: D

Câu 35. Trong Spring Kafka, transaction manager nào quản lý giao dịch dành cho Kafka producer?
A. `KafkaTransactionManager` quản lý Kafka producer transaction
B. `DataSourceTransactionManager` bao các thao tác Kafka transaction
C. `JpaTransactionManager` bao các thao tác Kafka trong transaction
D. `JmsTransactionManager` bao các thao tác Kafka trong transaction
Đáp án đúng: A

Câu 36. Consumer muốn không đọc các record của Kafka transaction đã abort, cần cấu hình gì?
A. `isolation.level=read_committed` để bỏ các record đã abort
B. `auto.offset.reset=latest` để bỏ transaction abort
C. `acks=all` trên consumer để bỏ các transaction abort
D. `enable.auto.commit=false` để bỏ record của transaction abort
Đáp án đúng: A

Câu 37. Trong chuỗi consume-transform-produce Kafka, exactly-once được bảo đảm bằng cách nào?
A. Dùng retry topic để xác nhận offset đã commit thành công
B. Ghi output và consumed offsets trong cùng Kafka transaction
C. Bật auto commit offsets trước khi ghi output Kafka
D. Ghi offset vào database riêng rồi gửi output không giao dịch
Đáp án đúng: B

Câu 38. Nếu ứng dụng ghi đồng thời database bên ngoài và Kafka, giới hạn quan trọng của exactly-once Kafka là gì?
A. Không có atomicity với DB; dùng outbox hoặc idempotency
B. Kafka transaction sẽ commit SQL thông qua broker coordinator
C. SQL update được rollback khi Kafka producer bị retry send
D. `read_committed` trên consumer sẽ bảo đảm atomicity cho SQL
Đáp án đúng: A

Câu 39. Khi phải giảm nhận message tạm thời mà vẫn giữ membership nhóm, Spring Kafka container hỗ trợ gì?
A. Tăng `max.poll.records` để giảm số records nhận được
B. Đóng các Kafka connections và giữ partition assignment
C. Dừng hẳn consumer poll lâu hơn `max.poll.interval.ms`
D. Pause consumer; container vẫn poll giữ group membership
Đáp án đúng: D

Câu 40. Để chẩn đoán consumer tụt hậu và tăng lỗi, bộ tín hiệu vận hành nào hữu ích nhất?
A. Chỉ số partitions tồn tại và số class trong ứng dụng
B. Lag, rebalance, retry/DLT rate và thời gian xử lý
C. Chỉ số JVM heap dùng và số lượng Java bean đang có
D. Chỉ tổng số producer trong hệ thống và uptime broker
Đáp án đúng: B
