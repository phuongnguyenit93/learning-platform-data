Câu 01. Trong Spring Cloud Stream, bean `Supplier<OrderEvent>` thường đóng vai trò nào?
A. Phát event qua output binding, không cần input binding
B. Nhận sự kiện từ hai input binding rồi tổng hợp kết quả
C. Nhận sự kiện qua input binding và không phát kết quả
D. Biến đổi sự kiện input thành sự kiện ở output binding
Đáp án đúng: A

Câu 02. Bean `Function<OrderEvent, InvoiceEvent>` thường được nối vào luồng sự kiện ra sao?
A. Phát message vào output binding mà không có input
B. Đọc message từ input binding rồi kết thúc không phát đi
C. Nhận input rồi trả kết quả qua output binding
D. Đăng ký binding động mà không thực hiện biến đổi dữ liệu
Đáp án đúng: C

Câu 03. Với `Consumer<PaymentEvent>`, mô tả nào đúng về binding của hàm?
A. Nhận message từ input binding, không có output binding
B. Nhận và trả message qua một input và một output binding
C. Định nghĩa hai output binding cho mỗi message được nhận
D. Phát message vào output binding, không cần input binding
Đáp án đúng: A

Câu 04. Một bean `Function` tên `normalize` có một input; tên input binding mặc định là gì?
A. `input-normalize-0` là tên input binding theo quy ước
B. `normalize-out-0` là tên input binding theo quy ước
C. `normalize-in-1` là tên input binding theo quy ước
D. `normalize-in-0` là tên input binding theo quy ước
Đáp án đúng: D

Câu 05. Bean `Supplier` tên `invoiceSource` có một output; binding mặc định tên gì?
A. `invoiceSource-in-0` là output binding của supplier
B. `invoiceSource-out-0` là output binding của supplier
C. `invoiceSource-out-1` là output binding của supplier
D. `output-invoiceSource-0` là output binding của supplier
Đáp án đúng: B

Câu 06. Ứng dụng có nhiều functional bean và muốn chọn `processOrder` để binding; dùng gì?
A. `spring.cloud.function.definition=processOrder` chọn hàm
B. `spring.cloud.stream.bindings.group=processOrder` chọn hàm
C. `spring.cloud.stream.poller.fixedDelay=processOrder` chọn hàm
D. `spring.cloud.stream.defaultBinder=processOrder` chọn hàm
Đáp án đúng: A

Câu 07. Khi đặt `spring.cloud.function.definition=normalize|enrich`, pipeline chạy theo thứ tự nào?
A. Một hàm dùng để tạo binding, hàm kia chỉ kiểm lỗi
B. Kết quả `enrich` trở thành input của `normalize`
C. Kết quả `normalize` trở thành input của `enrich`
D. Hai hàm chạy độc lập trên hai bản sao của message
Đáp án đúng: C

Câu 08. Muốn phát message ra output binding từ logic không nằm trong `Supplier`, nên dùng gì?
A. `StreamBridge.send` gửi payload đến output binding
B. `InputDestination.send` gửi payload khi chạy production
C. `OutputDestination.receive` gửi payload khi chạy production
D. `BindingService.unbind` gửi payload đến output binding
Đáp án đúng: A

Câu 09. Ứng dụng có cả Kafka và Rabbit binder; thuộc tính nào chọn binder cho một binding?
A. `spring.cloud.stream.bindings.<name>.destination` chọn binder
B. `spring.cloud.stream.bindings.<name>.contentType` chọn binder
C. `spring.cloud.stream.bindings.<name>.group` chọn binder
D. `spring.cloud.stream.bindings.<name>.binder` chọn binder
Đáp án đúng: D

Câu 10. Muốn binding `orders-in-0` đọc destination `orders.events`, nên cấu hình gì?
A. `...bindings.orders-in-0.contentType=orders.events`
B. `...bindings.orders-in-0.destination=orders.events`
C. `...bindings.orders-in-0.group=orders.events`
D. `...bindings.orders-in-0.binder=orders.events`
Đáp án đúng: B

Câu 11. Khi đổi binder từ Kafka sang Pulsar, nhóm việc kiểm tra nào vẫn cần thiết?
A. Kiểm ordering, retry và schema theo đặc tính broker mới
B. Giữ nguyên hành vi offset/ack do binder trừu tượng hóa
C. Thay `Function` bằng `CommandLineRunner` để dùng Pulsar
D. Đổi group thành tên topic để giữ lại Kafka offset cũ
Đáp án đúng: A

Câu 12. Với Kafka binder, cấu hình `.group=payments` cho consumer nhằm mục đích gì?
A. Chọn partition key `payments` cho message đầu ra
B. Chọn Kafka cluster `payments` cho outbound binding
C. Đặt consumer vào nhóm `payments` để chia partition
D. Đổi tên topic thành `payments` trước khi producer gửi
Đáp án đúng: C

Câu 13. Hai ứng dụng dùng group Kafka khác nhau nhưng cùng đọc một topic; hành vi nào đúng?
A. Chỉ group được tạo đầu tiên nhận message từ topic
B. Group mới đọc tiếp offset vừa commit của group cũ
C. Hai group chia cùng một offset không thể tách riêng
D. Mỗi group có tiến độ tiêu thụ độc lập với group kia
Đáp án đúng: D

Câu 14. Nhiều instance thuộc cùng một Kafka consumer group thường chia message thế nào?
A. Mỗi instance nhận bản sao từng record của cùng partition
B. Mỗi instance tự tạo topic mới cho cùng một destination
C. Các consumer độc lập cùng commit chung một offset topic
D. Các partition được phân cho consumer trong cùng group
Đáp án đúng: D

Câu 15. Trong RabbitMQ binder, các instance cùng named consumer group thường nhận message thế nào?
A. Cùng cạnh tranh lấy message từ queue gắn với group
B. Mỗi instance đọc cùng Kafka partition theo offset riêng
C. Group được chuyển thành tên exchange không có queue
D. Mỗi instance giữ queue độc lập dù cùng group name
Đáp án đúng: A

Câu 16. Topic Kafka có ba partition và năm consumer trong cùng một group; tối đa bao nhiêu consumer đọc partition đồng thời?
A. Hai consumer đọc partition, ba consumer tự tạo topic mới
B. Ba consumer có partition, hai consumer không được gán
C. Năm consumer mỗi người đọc một tập record cùng partition
D. Một consumer đọc cả topic; bốn consumer chỉ làm standby
Đáp án đúng: B

Câu 17. Với partition count giữ nguyên, gửi các message có cùng key Kafka thường đem lại gì?
A. Các message cùng key được phát tới các group độc lập
B. Các message cùng key được định tuyến vào cùng partition
C. Các message cùng key buộc phải ghi vào topic khác nhau
D. Các message cùng key được chuyển thẳng sang DLQ mặc định
Đáp án đúng: B

Câu 18. Bảo đảm thứ tự record trong Kafka được áp dụng ở phạm vi nào?
A. Thứ tự được giữ chung giữa các group của cùng topic
B. Thứ tự được giữ chung giữa nhiều topic khác nhau
C. Thứ tự được giữ trong phạm vi từng Kafka partition
D. Thứ tự được giữ chung giữa các partition của topic
Đáp án đúng: C

Câu 19. Muốn chọn partition theo thuộc tính `customerId` của message đầu ra, cấu hình nào liên quan?
A. Binding `contentType` trích key để partition
B. Consumer `maxAttempts` trích key để partition
C. Producer `partitionKeyExpression` trích key để partition
D. Consumer `concurrency` trích key để partition
Đáp án đúng: C

Câu 20. Một hàm xử lý `Message<OrderEvent>` có thể đọc dữ liệu và metadata qua đâu?
A. `headers` chứa dữ liệu và `payload` chứa metadata
B. `destination` chứa dữ liệu và `group` chứa metadata
C. `binder` chứa dữ liệu và `poller` chứa metadata
D. `payload` chứa dữ liệu và `headers` chứa metadata
Đáp án đúng: D

Câu 21. Muốn hỗ trợ chuyển đổi payload JSON tới kiểu Java đã khai báo, setting nào liên quan?
A. `binder=application/json` hướng dẫn message converter
B. `partitioned=application/json` hướng dẫn message converter
C. `group=application/json` hướng dẫn message converter
D. `contentType=application/json` giúp chuyển đổi payload
Đáp án đúng: D

Câu 22. Khi dùng Avro với Schema Registry, giá trị vận hành chính là gì?
A. Quản lý session HTTP và header ủy quyền người dùng
B. Quản lý offset consumer và gán partition theo user
C. Quản lý phiên bản schema và kiểm tương thích dữ liệu
D. Quản lý lịch retry và số record trong dead-letter queue
Đáp án đúng: C

Câu 23. Khi thêm field vào Avro record, cách nào giảm nguy cơ làm hỏng consumer cũ?
A. Đổi kiểu field đang dùng mà không tăng schema version
B. Xóa field cũ để reader dùng schema mới ít cột hơn
C. Đổi toàn bộ tên field cũ sang tên viết tắt khi build
D. Thêm field với default và kiểm tương thích schema
Đáp án đúng: D

Câu 24. Với mô hình at-least-once, consumer phải chuẩn bị cho khả năng nào?
A. Một event có thể được giao lại và xử lý nhiều lần
B. Mỗi event thất bại sẽ bị xóa ngay không cần retry
C. Mỗi event được giữ trong memory cho tới khi app restart
D. Mỗi event được xử lý đúng một lần kể cả DB ngoài
Đáp án đúng: A

Câu 25. Nếu broker giao lại event tạo đơn hàng, cách nào giúp tránh ghi trùng nghiệp vụ?
A. Tăng số consumer instance để tránh retry của event
B. Ghi event ID đã xử lý để bỏ qua bản giao lại
C. Đổi group name mỗi lần consumer nhận cùng event
D. Tăng `maxAttempts` để tránh áp dụng side effect trùng
Đáp án đúng: B

Câu 26. Với imperative consumer và lỗi tạm thời, property nào giới hạn số lần xử lý lại?
A. `consumer.concurrency` điều chỉnh số lượt thử xử lý
B. `consumer.maxAttempts` điều chỉnh số lượt thử xử lý
C. `consumer.partitioned` điều chỉnh số lượt thử xử lý
D. `consumer.useNativeDecoding` điều chỉnh số lượt thử xử lý
Đáp án đúng: B

Câu 27. Vì sao nên thêm backoff giữa các lần retry khi hệ thống downstream đang quá tải?
A. Chuyển các message lỗi sang topic mới theo từng lần gọi
B. Thay đổi schema của payload để lần retry tiếp thành công
C. Tăng số lượng partition của topic ngay khi retry
D. Giảm việc gọi dồn dập vào phụ thuộc đang gặp lỗi
Đáp án đúng: D

Câu 28. Khi một message lỗi dữ liệu liên tục khiến consumer kẹt, DLQ có ích gì?
A. Giữ record lỗi để sửa payload ngay trước lần retry
B. Tách record lỗi sang DLQ để xử lý bản ghi khác
C. Tự chỉnh payload lỗi thành schema tương thích hơn
D. Tự tăng offset của các group chưa nhận message lỗi
Đáp án đúng: B

Câu 29. Kafka binder có consumer group cấu hình sẵn; muốn đưa record lỗi sang DLQ, option nào thường dùng?
A. `autoBindDlq=true` trong cấu hình consumer Kafka binder
B. `partitionKeyExpression=true` trong cấu hình consumer
C. `enableDlq=true` trong cấu hình consumer Kafka binder
D. `useNativeDecoding=true` trong cấu hình consumer
Đáp án đúng: C

Câu 30. Với RabbitMQ binder và named group, cờ nào dùng để tự khai báo dead-letter queue?
A. `partitionCount=true` trong cấu hình Rabbit consumer
B. `autoBindDlq=true` trong cấu hình Rabbit consumer
C. `useNativeEncoding=true` trong cấu hình Rabbit consumer
D. `enableDlq=true` trong cấu hình Rabbit consumer
Đáp án đúng: B

Câu 31. Khi lỗi deserialization xảy ra trước khi hàm `Consumer<T>` được gọi, nên kiểm gì?
A. Bộ đếm lỗi nghiệp vụ trong Consumer sau khi xử lý payload
B. Nhánh catch trong thân hàm khi nó chưa được gọi
C. Nhánh return của Supplier sau khi phát record lỗi
D. Kiểm xử lý lỗi binder ở bước deserialization
Đáp án đúng: D

Câu 32. Nếu consumer xác nhận message trước khi ghi DB thành công, rủi ro chính là gì?
A. Record sẽ được broker phát lại cho nhóm khác tức thì
B. Record sẽ tự chuyển thành Kafka Streams state store
C. Record có thể mất tác động nghiệp vụ nếu app crash
D. Record làm tăng partition count trên broker khi retry
Đáp án đúng: C

Câu 33. Trong Spring Cloud Stream test binder, API nào thường được dùng để đưa message vào input?
A. `StreamBridge.receive` phát message tới input binding
B. `BinderHealthIndicator.send` phát message tới input binding
C. `InputDestination.send` phát message tới input binding
D. `OutputDestination.send` phát message tới input binding
Đáp án đúng: C

Câu 34. Trong kiểm thử bằng test binder, API nào đọc message đã đi ra output binding?
A. `BindingService.receive` nhận message output
B. `OutputDestination.receive` nhận message output
C. `InputDestination.receive` nhận message output
D. `StreamBridge.receive` nhận message output
Đáp án đúng: B

Câu 35. Trong Kafka Streams binder, kiểu nào biểu diễn luồng record theo sự kiện?
A. `KTable<K,V>` biểu diễn dãy record theo sự kiện
B. `GlobalKTable<K,V>` biểu diễn dãy record theo sự kiện
C. `KeyValueStore<K,V>` biểu diễn dãy record theo sự kiện
D. `KStream<K,V>` biểu diễn dãy record theo sự kiện
Đáp án đúng: D

Câu 36. Trong Kafka Streams, `KTable<K,V>` thường đại diện khái niệm nào?
A. Trạng thái hiện tại theo key trong một bảng cập nhật
B. Snapshot độc lập của mỗi partition sau một lượt poll
C. Một changelog topic làm nhiệm vụ thay consumer group
D. Chuỗi sự kiện độc lập theo timestamp producer
Đáp án đúng: A

Câu 37. Khi aggregate event theo key qua Kafka Streams, state store giúp gì?
A. Đổi state record thành schema mới để tránh repartition
B. Lưu trạng thái tích lũy để tính toán qua nhiều record
C. Giữ bản sao source topic theo offset của từng consumer
D. Lưu key group để thay thế Kafka offset commit
Đáp án đúng: B

Câu 38. Kafka Streams dùng changelog topic cho state store nhằm mục đích gì?
A. Changelog khôi phục state store sau rebalance hoặc restart
B. Ghi event nguồn để thay thế source topic khi task khởi động
C. Ghi offset để thay thế consumer group coordinator của Kafka
D. Phát output record ra nhiều topic bất kể partition key
Đáp án đúng: A

Câu 39. Một consumer group tăng lag và DLQ cũng tăng; thông tin nào nên kiểm tra?
A. So lag với throughput, lỗi, retry và tốc độ event vào
B. Chỉ thời gian build image của consumer trong pipeline
C. Chỉ số bean Spring đăng ký ở ApplicationContext
D. Chỉ dung lượng executable của broker khi triển khai
Đáp án đúng: A

Câu 40. Khi Kafka Streams dùng exactly-once cho Kafka I/O, điều nào cần lưu ý với DB ngoài?
A. Commit offset Kafka là bằng chứng DB ngoài đã commit xong
B. Giao dịch Kafka cũng commit DB ngoài trong cùng transaction
C. Giao dịch Kafka không tự bao phủ commit trong DB ngoài
D. Producer idempotence đủ để ngăn side effect trùng trong DB
Đáp án đúng: C
