Câu 1. Với JMS Queue có nhiều consumer, broker thường phân phối một message như thế nào?
A. Giao một message cho một consumer đang chờ trên queue.
B. Luôn giao message cho consumer đã đăng ký đầu tiên.
C. Chọn consumer dựa theo mức ưu tiên của message.
D. Gửi cùng một message tới mọi consumer của queue.
Đáp án đúng: A

Câu 2. Với JMS Topic có hai subscription độc lập, message được phân phối ra sao?
A. Chỉ subscription kết nối sớm nhất nhận message.
B. Message chờ đến khi mọi subscription sẵn sàng.
C. Mỗi subscription phù hợp đều có thể nhận một bản sao.
D. Topic chọn một consumer duy nhất của mọi nhóm.
Đáp án đúng: C

Câu 3. Trong JMS, đối tượng `Destination` đại diện cho thành phần nào?
A. Chính sách retry và số lần redelivery của broker.
B. Đích gửi hoặc nhận message như queue hay topic.
C. Đối tượng điều khiển transaction của producer.
D. Kết nối TCP được dùng chung bởi nhiều session.
Đáp án đúng: B

Câu 4. Nhận định nào đúng về ActiveMQ Classic và ActiveMQ Artemis?
A. Classic và Artemis dùng chung mọi định dạng cấu hình.
B. Artemis chỉ hỗ trợ AMQP còn Classic chỉ hỗ trợ JMS.
C. Artemis là một plugin cần cài vào ActiveMQ Classic.
D. Đây là hai broker độc lập với kiến trúc triển khai khác nhau.
Đáp án đúng: D

Câu 5. `ConnectionFactory` trong ứng dụng JMS có vai trò chính nào?
A. Điều phối acknowledgement của mọi JMS session được tạo.
B. Tự chuyển message lỗi vào dead-letter queue.
C. Tạo kết nối JMS tới broker theo cấu hình ứng dụng client.
D. Chọn message để giao dựa trên bộ lọc selector.
Đáp án đúng: C

Câu 6. Trong JMS, `Session` chịu trách nhiệm chính cho thao tác nào?
A. Duy trì kênh truyền giữa broker và các JMS connection.
B. Cung cấp địa chỉ broker và thông tin xác thực kết nối.
C. Tạo producer/consumer và quản lý ack hay transaction.
D. Thực hiện replication queue giữa các node broker.
Đáp án đúng: C

Câu 7. Khi không có message trong thời gian chờ, `MessageConsumer.receive(timeout)` thường trả về gì?
A. Trả về giá trị `false` để xác nhận timeout.
B. Trả lại một message rỗng có body bằng `null`.
C. Trả lại thông báo broker với delivery mode mặc định.
D. Trả về `null` nếu hết thời gian mà chưa nhận.
Đáp án đúng: D

Câu 8. Trong Java JMS, thao tác nào gửi một message qua producer?
A. Gọi `MessageConsumer.receive()` tại consumer.
B. Gọi `MessageProducer.send(...)` tại producer.
C. Gọi `Session.rollback()` ở session gửi message.
D. Gọi `Message.acknowledge()` sau khi tạo body.
Đáp án đúng: B

Câu 9. Loại message JMS nào được thiết kế để mang nội dung chuỗi?
A. `ObjectMessage` với payload bytes chưa giải mã.
B. `TextMessage` với body dạng văn bản chuỗi.
C. `BytesMessage` với nội dung là chuỗi Java.
D. `MapMessage` với một trường chuỗi bắt buộc.
Đáp án đúng: B

Câu 10. Với listener JMS không transacted và chế độ `AUTO_ACKNOWLEDGE`, ack diễn ra khi nào?
A. Sau khi listener xử lý và trả về thành công.
B. Chỉ khi ứng dụng gọi `session.commit()`.
C. Ngay trước khi broker gửi message đến listener.
D. Chỉ sau khi ứng dụng gọi `message.acknowledge()`.
Đáp án đúng: A

Câu 11. Trong chế độ JMS `CLIENT_ACKNOWLEDGE`, gọi `message.acknowledge()` có tác dụng gì?
A. Ack cả message chưa giao tới consumer trên queue.
B. Chỉ ack một message có đúng message ID truyền vào.
C. Gửi mọi message chưa commit trong session hiện tại.
D. Ack mọi message đã tiêu thụ thuộc cùng một JMS session.
Đáp án đúng: D

Câu 12. Đặc điểm nào gắn với JMS `DUPS_OK_ACKNOWLEDGE`?
A. Buộc ứng dụng ack từng message ngay khi nhận được.
B. Cam kết không thể có message trùng khi kết nối mất.
C. Ack có thể bị trì hoãn, dẫn tới giao trùng.
D. Tự rollback mọi message nếu consumer xử lý lỗi.
Đáp án đúng: C

Câu 13. Khi dùng JMS transacted session, gọi `commit()` sẽ thực hiện điều gì?
A. Commit các send và các ack đã nhận trong transaction JMS session.
B. Chỉ commit các message gửi, không bao gồm acknowledgement.
C. Commit mọi transaction thuộc cùng JMS connection.
D. Đồng thời commit giao dịch ở mọi database bên ngoài.
Đáp án đúng: A

Câu 14. Nếu một JMS transacted session thực hiện `rollback()`, hành vi nào phù hợp?
A. Hủy send chưa commit, giao lại message đã nhận.
B. Các message gửi chưa commit vẫn được phát đi.
C. Các message đã nhận bị ack và xóa vĩnh viễn.
D. Giữ các send chưa commit cho transaction tiếp theo.
Đáp án đúng: A

Câu 15. Cờ `JMSRedelivered` của một message cho biết điều gì?
A. Message sẽ luôn được phân phối đúng thứ tự tuyệt đối.
B. Message đã được consumer xử lý và commit database.
C. Message được đánh dấu là đã từng được giao trước đó.
D. Message đang được gửi tới một durable subscription.
Đáp án đúng: C

Câu 16. Consumer có thể nhận lại message khi mất kết nối trước ack. Cách xử lý phù hợp?
A. Chỉ dựa cờ `JMSRedelivered` để bỏ message giao lại.
B. Lưu idempotency key để tránh áp dụng tác động lặp.
C. Giữ toàn bộ state xử lý trùng trong RAM một instance.
D. Chuyển mọi consumer sang auto-ack để loại message trùng.
Đáp án đúng: B

Câu 17. Thiết lập `DeliveryMode.PERSISTENT` trong JMS nhằm yêu cầu điều gì?
A. Yêu cầu broker lưu bền message khi được hỗ trợ.
B. Tự đồng bộ transaction JMS với database bên ngoài.
C. Không giới hạn thời gian sống của mọi message.
D. Buộc broker chờ consumer ack trước khi xác nhận send.
Đáp án đúng: A

Câu 18. Durable subscription trên JMS Topic hỗ trợ khả năng nào?
A. Biến một topic thành queue với duy nhất một consumer.
B. Tự ack message trước khi consumer xử lý nội dung.
C. Gửi mọi message cũ cho subscriber mới không đăng ký.
D. Giữ message phù hợp khi subscriber tạm mất kết nối.
Đáp án đúng: D

Câu 19. JMS message selector thường lọc dựa trên dữ liệu nào?
A. Header và property của message theo biểu thức lọc.
B. Nội dung bytes tùy ý nằm sâu trong message body.
C. Trạng thái listener và thời gian chờ nhận message.
D. Tên connection và địa chỉ mạng của client tiêu thụ.
Đáp án đúng: A

Câu 20. Đặt thời gian sống (TTL) khi gửi JMS message giúp kiểm soát điều gì?
A. Xác định thời điểm message hết hạn nếu chưa được xử lý.
B. Thời gian broker giữ kết nối TCP chưa hoạt động.
C. Số consumer tối đa được kết nối tới destination.
D. Số lượt retry tối đa của message khi consumer lỗi.
Đáp án đúng: A

Câu 21. Với JMS message priority, cách hiểu nào phù hợp?
A. Xác nhận message đã được consumer xử lý xong.
B. Có thể tác động thứ tự giao message.
C. Xác định số lượt retry của từng message.
D. Bảo đảm thứ tự giao trên mọi broker trong cụm.
Đáp án đúng: B

Câu 22. Đích DLQ của broker thường dùng cho nhóm message nào?
A. Message chưa có consumer kết nối trên queue bền vững.
B. Message lỗi quá giới hạn redelivery đã đặt.
C. Message thiếu bản sao đồng bộ để được ghi bền vững.
D. Message đang được giao lại nhưng chưa hết số lần thử.
Đáp án đúng: B

Câu 23. Trong Artemis, address dùng anycast có hành vi định tuyến nào?
A. Gửi bản sao tới mọi queue đang gắn với cùng address.
B. Luôn gửi message trực tiếp tới một consumer được chỉ tên.
C. Chỉ phát message tới durable topic subscription.
D. Định tuyến message tới một queue phù hợp để tiêu thụ.
Đáp án đúng: D

Câu 24. Trong Artemis, multicast routing phù hợp với kịch bản nào?
A. Giao message vào một queue duy nhất để cạnh tranh.
B. Gửi bản sao tới các queue `MULTICAST` thỏa bộ lọc.
C. Chỉ phân phối message tới consumer nhận sớm nhất.
D. Tự chọn node broker có bộ nhớ trống lớn nhất.
Đáp án đúng: B

Câu 25. Quan hệ giữa address và queue trong ActiveMQ Artemis được mô tả đúng nhất ra sao?
A. Queue làm nhiệm vụ định tuyến; address lưu message.
B. Address định tuyến message; queue giữ message để nhận.
C. Queue chỉ là bí danh address và không lưu message riêng.
D. Mỗi address chỉ có thể liên kết với đúng một queue.
Đáp án đúng: B

Câu 26. Trong ActiveMQ Classic, Virtual Topic hữu ích khi muốn làm gì?
A. Dùng một queue chung để mọi nhóm consumer chia nhau.
B. Một message topic chỉ tới một client đang kết nối.
C. Cho các nhóm queue nhận bản sao và chia tải riêng.
D. Tạo một durable subscription chung cho mọi nhóm consumer.
Đáp án đúng: C

Câu 27. Khi chuyển JMS client từ ActiveMQ Classic sang Artemis, cần kiểm tra gì để tránh gửi hoặc nhận sai destination?
A. Kiểm tra số thread listener và giá trị prefetch của consumer.
B. Kiểm tra mức sử dụng heap và thời gian thu gom rác.
C. Kiểm tra TTL và độ ưu tiên của message trên client.
D. Kiểm tra giao thức client và destination trên broker Artemis.
Đáp án đúng: D

Câu 28. Để consumer chỉ đọc được queue được cấp quyền, broker cần kết hợp gì?
A. Sử dụng selector để lọc message theo tên consumer.
B. Cấp quyền gửi trên topic rồi dùng lại cho mọi queue.
C. Xác thực danh tính và phân quyền trên destination.
D. Bật TLS và dùng chung một tài khoản cho mọi consumer.
Đáp án đúng: C

Câu 29. Khi Java client kết nối broker qua TLS, bước nào giúp giảm giả mạo máy chủ?
A. Xác minh chuỗi chứng chỉ qua truststore và hostname broker.
B. Dùng username/password thay việc xác minh broker.
C. Dùng cổng TLS nhưng tắt xác minh danh tính broker.
D. Chỉ kiểm tra tên host, bỏ qua chuỗi chứng chỉ.
Đáp án đúng: A

Câu 30. Muốn điều tra queue ùn tắc và message xử lý lỗi ở ActiveMQ, bộ metrics nào phù hợp nhất?
A. Queue depth, dequeue rate, producer count và CPU.
B. DLQ count, enqueue rate, connection count và uptime.
C. Inflight count, redelivery count, heap usage và clients.
D. Queue depth, inflight, redelivery count và DLQ count.
Đáp án đúng: D

Câu 31. Khi consumer chậm làm queue tăng nhanh, điều chỉnh nào có thể giúp giảm quá tải?
A. Bỏ việc ack để broker không thấy message đã nhận.
B. Tăng prefetch không giới hạn cho mọi consumer.
C. Tăng TTL của toàn bộ message khi hàng đợi đang lớn.
D. Điều chỉnh prefetch và concurrency khi cần.
Đáp án đúng: D

Câu 32. Để kiểm thử redelivery của message không được ack, cách nào hiệu quả?
A. Ngắt consumer sau khi ack thành công rồi đọc queue.
B. Yêu cầu producer gửi lại rồi kiểm tra số message mới.
C. Ngắt consumer trước ack, kiểm tra message giao lại.
D. Đóng session sau commit và kiểm tra message đã nhận.
Đáp án đúng: C
