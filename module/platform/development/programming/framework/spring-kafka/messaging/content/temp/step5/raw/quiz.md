Câu 1. Trong Spring Kafka 3.x, `KafkaTemplate.send(topic, key, value)` trả về kiểu nào?
A. `ConsumerRecord<K,V>` chứa dữ liệu đã được consumer đọc.
B. `RecordMetadata` trả trực tiếp ngay khi gọi method send.
C. `Mono<SendResult<K,V>>` được Reactor tự động subscribe.
D. `CompletableFuture<SendResult<K,V>>` theo cơ chế bất đồng bộ.
Đáp án đúng: D

Câu 2. `KafkaTemplate.send(...)` hoàn thành thành công khi nào theo cấu hình producer?
A. Khi listener của mọi consumer group xử lý xong record.
B. Khi tất cả replica và subscriber trả kết quả nghiệp vụ.
C. Khi transaction database của consumer đã được commit.
D. Khi broker xác nhận gửi theo mức `acks` đã cấu hình.
Đáp án đúng: D

Câu 3. Một method gắn `@KafkaListener(topics="orders")` nhận dữ liệu bằng cơ chế nào?
A. Controller MVC nhận webhook rồi chuyển payload tới listener.
B. Listener container poll Kafka rồi chuyển record tới method.
C. Kafka broker gọi HTTP endpoint do annotation tự tạo.
D. Producer gọi trực tiếp method Java sau mỗi lần gửi message.
Đáp án đúng: B

Câu 4. Trong `@KafkaListener(groupId="billing")`, `groupId` ảnh hưởng điều gì?
A. Broker tạo partition mới tên `billing` khi listener chạy.
B. KafkaTemplate dùng `billing` làm transactional producer ID.
C. Consumer của listener tham gia group có tên `billing`.
D. Producer gửi mọi record đến topic có tên `billing`.
Đáp án đúng: C

Câu 5. Kafka bảo đảm thứ tự record theo offset trong phạm vi nào?
A. Trên mọi partition của topic theo thứ tự thời gian gửi.
B. Trong cùng một partition của topic đối với consumer.
C. Giữa các topic cùng được xử lý trong một consumer group.
D. Giữa các consumer group đang đọc cùng một partition.
Đáp án đúng: B

Câu 6. Một topic có 3 partition, group có 5 consumer cùng subscribe; tối đa bao nhiêu consumer nhận assignment?
A. Một consumer nhận topic; bốn consumer làm standby.
B. Năm consumer được chia đều từng partition khi poll.
C. Mỗi consumer nhận đủ ba partition của topic đó.
D. Ba consumer nhận partition; hai consumer có thể nhàn rỗi.
Đáp án đúng: D

Câu 7. Hai consumer group khác nhau cùng subscribe topic `events`; hành vi nào đúng?
A. Mỗi group quản lý offset và nhận luồng record riêng.
B. Broker chỉ cho một group đọc một topic tại thời điểm.
C. Hai group chia chung offset và luân phiên các record.
D. Group thứ hai chỉ nhận record chưa được group đầu đọc.
Đáp án đúng: A

Câu 8. Producer gửi nhiều record với cùng key và số partition không đổi; tác động thường gặp là gì?
A. Partitioner theo key đưa các record tới cùng partition.
B. Kafka tự bảo đảm record vào mọi partition để cân bằng tải.
C. Broker tạo một topic riêng cho từng key khi ghi message.
D. Consumer group tự gán key thành offset chung toàn topic.
Đáp án đúng: A

Câu 9. Trong Kafka, offset của một record có ý nghĩa gì?
A. Số thứ tự toàn cục của record trên mọi topic của cluster.
B. Thời điểm chính xác broker xác nhận producer gửi record.
C. Vị trí của record trong log thuộc một partition cụ thể.
D. Định danh consumer group đã xử lý record lần gần nhất.
Đáp án đúng: C

Câu 10. Khi consumer group đã commit offset 42 cho partition, offset commit thường biểu thị điều gì?
A. Vị trí 42 là record tiếp theo nhóm sẽ đọc khi phục hồi.
B. Record ở offset 42 đã được xóa vĩnh viễn khỏi partition.
C. Partition được tăng số bản sao từ 1 lên 42 trên broker.
D. Toàn bộ consumer group phải bắt đầu đọc lại từ offset 0.
Đáp án đúng: A

Câu 11. Một record đã được consumer đọc, nhưng chưa hết retention; điều nào thường đúng?
A. Record được chuyển thành metadata và bỏ phần payload.
B. Broker xóa record ngay sau khi listener xác nhận offset.
C. Kafka chuyển record ra DLT ngay khi consumer commit offset.
D. Record vẫn còn trong log theo chính sách lưu giữ của topic.
Đáp án đúng: D

Câu 12. Trong listener cần xác nhận thủ công, cấu hình nào phù hợp?
A. Chọn `AckMode.RECORD` rồi gọi `ConsumerRecord.acknowledge()`.
B. Dùng `AckMode.BATCH` rồi gọi `ConsumerFactory.acknowledge()`.
C. Bật `enable.auto.commit=true` và gọi `KafkaTemplate.flush()`.
D. Dùng AckMode thủ công và gọi `Acknowledgment.acknowledge()`.
Đáp án đúng: D

Câu 13. Với listener record, `AckMode.RECORD` của container ảnh hưởng thời điểm commit thế nào?
A. Container commit offset sau khi listener xử lý record xong.
B. Container ủy quyền KafkaTemplate commit offset của producer.
C. Container chỉ commit sau khi toàn bộ topic được tiêu thụ.
D. Container commit trước khi record được giao cho listener.
Đáp án đúng: A

Câu 14. `ConcurrentKafkaListenerContainerFactory.setConcurrency(3)` thường điều chỉnh điều gì?
A. Số bản sao dữ liệu do leader broker ghi cho mỗi record.
B. Số producer KafkaTemplate được tạo cho mỗi lần gửi record.
C. Số consumer đồng thời của listener container theo cấu hình.
D. Số partition Kafka phải tạo mới mỗi khi ứng dụng khởi động.
Đáp án đúng: C

Câu 15. Muốn method `@KafkaListener` nhận nhiều record trong một lần gọi, cần gì?
A. Đặt `@KafkaListener` trên method có một `ConsumerRecord`.
B. Dùng `KafkaTemplate.executeInTransaction()` trên consumer method.
C. Giữ record listener mặc định và đổi tên tham số thành list.
D. Bật batch listener trong container factory và nhận danh sách.
Đáp án đúng: D

Câu 16. Ứng dụng trao đổi JSON qua Kafka; để consumer đọc đúng DTO và an toàn kiểu, nên làm gì?
A. Để `StringDeserializer` tự đổi mọi JSON thành DTO domain.
B. Dùng `ByteArrayDeserializer` rồi coi đó là Bean Validation.
C. Dùng `JsonSerializer` ở consumer để giải mã record nhận.
D. Cấu hình `JsonDeserializer` với kiểu đích và trusted packages.
Đáp án đúng: D

Câu 17. Khi deserializer của Kafka gặp payload lỗi trước khi vào listener, Spring Kafka hỗ trợ gì?
A. Đặt `AckMode.RECORD` để tự sửa dữ liệu lỗi trong payload.
B. Bọc deserializer bằng `ErrorHandlingDeserializer` để ghi lỗi.
C. Dùng `DefaultErrorHandler` mà không cần capture lỗi deserializer.
D. Dùng `JsonSerializer` để chuyển payload lỗi thành Java object.
Đáp án đúng: B

Câu 18. Trong `@KafkaListener`, muốn nhận topic nguồn qua method parameter, cách nào phù hợp?
A. Inject `@Header(KafkaHeaders.RECEIVED_TOPIC)` vào parameter.
B. Inject `@Header(KafkaHeaders.GROUP_ID)` làm tên topic.
C. Inject `@Header(KafkaHeaders.TOPIC)` để nhận topic gốc.
D. Inject `@Payload(KafkaHeaders.RECEIVED_TOPIC)` vào parameter.
Đáp án đúng: A

Câu 19. Khi `@KafkaListener` ném exception, thành phần nào thường cấu hình retry/backoff ở container?
A. Dùng `ReplyingKafkaTemplate` để tự retry record bất kỳ.
B. Dùng `DefaultErrorHandler` cùng chính sách `BackOff`.
C. Dùng `KafkaTemplate` làm transaction manager cho listener.
D. Dùng `RecordFilterStrategy` để tự chạy lại lời gọi bị lỗi.
Đáp án đúng: B

Câu 20. Sau khi retry thất bại, muốn chuyển record sang dead-letter topic, dùng thành phần nào?
A. Dùng `KafkaTransactionManager` để thay toàn bộ error handler.
B. Dùng `JsonDeserializer` để tạo topic dead-letter mới.
C. Dùng `DeadLetterPublishingRecoverer` với KafkaTemplate.
D. Dùng `Acknowledgment` để tự phát message vào DLT.
Đáp án đúng: C

Câu 21. Khi dùng `DeadLetterPublishingRecoverer` mặc định, tên topic DLT thường được suy ra thế nào?
A. Từ topic gốc thêm hậu tố `.DLT` theo resolver mặc định.
B. Từ group ID thêm hậu tố `.errors` theo consumer factory.
C. Từ tên listener thêm hậu tố `.failed` theo KafkaTemplate.
D. Từ tên partition thêm hậu tố `.retry` theo broker config.
Đáp án đúng: A

Câu 22. `@RetryableTopic` trong Spring Kafka chủ yếu thực hiện chiến lược nào?
A. Lặp vô hạn cùng record trên consumer thread ban đầu.
B. Dùng retry topic để trì hoãn xử lý rồi chuyển DLT nếu cần.
C. Khóa partition gốc cho tới khi handler thành công lần nữa.
D. Thay retry bằng Kafka producer transaction trên mọi record.
Đáp án đúng: B

Câu 23. Vì sao retry qua topic riêng cần cân nhắc khi nghiệp vụ yêu cầu thứ tự tuyệt đối theo key?
A. Broker đợi record lỗi được xử lý trước khi phát record mới.
B. Retry topic luôn dùng cùng offset với topic gốc để giữ thứ tự.
C. Record retry có thể được xử lý muộn hơn record kế tiếp.
D. Consumer tự khóa producer của key tới lúc retry kết thúc.
Đáp án đúng: C

Câu 24. Kafka producer bật `enable.idempotence=true` mang lại bảo đảm nào?
A. Loại bỏ record trùng nghiệp vụ giữa các consumer group.
B. Tự rollback mọi lần cập nhật database của phía consumer.
C. Giảm ghi trùng do retry gửi của producer tới một partition.
D. Ngăn mọi request ghi trùng qua các lần restart ứng dụng.
Đáp án đúng: C

Câu 25. Listener xử lý thành công nhưng chết trước khi offset được commit; rủi ro nào còn tồn tại?
A. Record có thể được giao lại; handler nên hỗ trợ idempotency.
B. Record bị xóa khỏi Kafka ngay khi method return thành công.
C. Kafka mặc định ghi nhận offset trong database của handler.
D. Consumer kế tiếp bỏ qua record vì payload đã được xử lý.
Đáp án đúng: A

Câu 26. Muốn KafkaTemplate gửi nhiều record trong một Kafka transaction, dùng API nào?
A. Dùng `send(...).join()` để mở transaction trên từng topic.
B. Dùng `executeInTransaction(...)` với producer có cấu hình tx.
C. Dùng `KafkaListenerEndpointRegistry.stop()` trước khi gửi.
D. Dùng `ConsumerFactory.createConsumer()` để commit producer.
Đáp án đúng: B

Câu 27. Consumer đặt `isolation.level=read_committed` sẽ xử lý transaction record thế nào?
A. Đọc record chưa commit rồi rollback nếu consumer báo lỗi.
B. Đọc mọi record nhưng tự gắn trạng thái commit vào header.
C. Đọc record đã abort và gửi trực tiếp vào dead-letter topic.
D. Đọc record của tx đã commit, bỏ qua record của tx abort.
Đáp án đúng: D

Câu 28. Với read-process-write Kafka exactly-once, yếu tố nào cần phối hợp trong transaction?
A. Producer idempotence tự commit cả offset và SQL transaction.
B. Record output và offset nguồn được ghi nhận trong Kafka tx.
C. Consumer auto-commit offset trước khi producer gửi output.
D. Dead-letter topic tự gắn offset nguồn vào database tx.
Đáp án đúng: B

Câu 29. Vì sao Kafka transaction không tự bảo đảm exactly-once cho side effect trong database ngoài Kafka?
A. Consumer group tự rollback bảng SQL khi producer thất bại.
B. Kafka transaction tự mở XA transaction với mỗi JDBC DataSource.
C. Thay đổi database không được bao gồm nguyên tử trong Kafka tx.
D. Broker tự kiểm tra commit database trước khi ghi offset nguồn.
Đáp án đúng: C

Câu 30. Một Kafka listener xử lý lâu hơn `max.poll.interval.ms`; hệ quả có thể xảy ra là gì?
A. Consumer tự mở thêm partition mới để giữ ownership hiện tại.
B. Consumer bị xem không tiến triển và partition bị rebalance.
C. Broker tăng `max.poll.records` để consumer xử lý nhanh hơn.
D. Producer tự chuyển record đang xử lý sang một topic DLT.
Đáp án đúng: B

Câu 31. Muốn integration test `KafkaTemplate` và `@KafkaListener` trên broker thực, cách nào phù hợp?
A. Dùng Embedded Kafka hoặc Testcontainers rồi assert send/receive.
B. Mock KafkaTemplate và suy ra broker đã commit record.
C. Unit test serializer để suy ra offset consumer đã commit.
D. Kiểm tra annotation listener và giả định group đã join.
Đáp án đúng: A

Câu 32. Khi lag tăng sau deploy Spring Kafka, bộ số liệu nào hữu ích để chẩn đoán?
A. Theo dõi số partition, không đo tốc độ xử lý của listener.
B. Theo dõi producer throughput, bỏ qua consumer lag và retry.
C. Theo dõi consumer lag, thời gian xử lý, retry và DLT.
D. Theo dõi `acks` producer mà bỏ qua trạng thái consumer group.
Đáp án đúng: C
