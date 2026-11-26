Câu 1. Trong Spring Integration, inbound channel adapter có vai trò nào?
A. Gửi Message ra hệ ngoài và đợi response từ service
B. Nhận dữ liệu hệ ngoài rồi phát Message vào channel
C. Nhận reply từ handler rồi tạo JMS response mới
D. Chỉ ghi payload vào JDBC mà không gửi qua channel
Đáp án đúng: B

Câu 2. Outbound channel adapter phù hợp khi cần thao tác gì?
A. Gửi Message ra hệ ngoài mà không phát reply vào flow
B. Nhận bản tin broker rồi đẩy vào message channel
C. Nhận HTTP request và dùng reply từ flow trả về
D. Gọi remote service và trả response vào channel
Đáp án đúng: A

Câu 3. Một inbound gateway khác inbound adapter ở điểm nào?
A. Nhận message một chiều mà không có response xử lý
B. Poll dữ liệu ngoài theo lịch với SourcePollingChannelAdapter
C. Chỉ đẩy message tới channel, bỏ reply của handler
D. Nhận request bên ngoài và trả reply được flow tạo
Đáp án đúng: D

Câu 4. Nếu flow cần gọi hệ ngoài rồi xử lý kết quả trả về, nên chọn gì?
A. Outbound adapter gửi một chiều và không nhận response
B. Inbound adapter chờ HTTP client mở kết nối vào flow
C. Transformer chỉ đổi payload từ kiểu này sang kiểu khác
D. Outbound gateway đưa reply thành Message tiếp theo
Đáp án đúng: D

Câu 5. Với adapter đọc file theo chu kỳ, thành phần nào quy định lịch lấy dữ liệu?
A. Outbound gateway tự chọn nhịp gọi MessageSource
B. Poller kích hoạt MessageSource theo lịch được cấu hình
C. MessageConverter tạo scheduler theo tên file đầu vào
D. MessageHandler tự tạo poller khi có replyChannel
Đáp án đúng: B

Câu 6. Với JMS message-driven inbound adapter, nhận định nào phù hợp?
A. JMS listener đẩy message vào channel, không cần poller
B. MessageSource.poll liên tục thay thế JMS listener container
C. Adapter chỉ chạy khi một poller chọn file mới
D. Adapter chỉ nhận khi HTTP client gửi webhook
Đáp án đúng: A

Câu 7. MessageSource.receive() của inbound polling source thường trả gì?
A. ReplyChannel nếu cần một phản hồi từ outbound gateway
B. Message nếu có dữ liệu, hoặc null nếu chưa có
C. Một danh sách tất cả subscriber của DirectChannel
D. TransactionStatus khi không tìm thấy dữ liệu mới
Đáp án đúng: B

Câu 8. SourcePollingChannelAdapter thường thực hiện hành vi nào?
A. Nhận response của outbound HTTP gateway làm reply
B. Chuyển mọi inbound adapter thành JMS listener
C. Poll MessageSource rồi phát kết quả vào channel
D. Chỉ giữ metadata, không gọi MessageSource.receive()
Đáp án đúng: C

Câu 9. Trong Poller, fixedDelay khác fixedRate chủ yếu ở điều gì?
A. fixedDelay dùng cron, fixedRate dùng timestamp của file
B. fixedDelay chỉ áp dụng JDBC, fixedRate chỉ cho broker
C. fixedDelay đòi executor, fixedRate đòi QueueChannel
D. fixedDelay chờ sau lần chạy, fixedRate theo nhịp định kỳ
Đáp án đúng: D

Câu 10. Tùy chọn maxMessagesPerPoll=10 giới hạn điều gì?
A. Số Message tối đa lấy trong mỗi lượt kích hoạt poller
B. Số consumer có thể subscribe cùng một DirectChannel
C. Số bản tin Kafka giữ ở broker trong một partition
D. Số HTTP request gửi được trước khi gateway đóng
Đáp án đúng: A

Câu 11. Khi consumer cần chủ động receive() từ một channel, loại nào phù hợp?
A. DirectChannel dùng MessageHandler để nhận đồng bộ
B. ExecutorChannel gửi xử lý qua một TaskExecutor riêng
C. QueueChannel lưu Message cho bên nhận qua PollableChannel
D. PublishSubscribeChannel fan-out tới nhiều subscriber
Đáp án đúng: C

Câu 12. DirectChannel có hành vi gửi message mặc định nào?
A. Gọi handler đồng bộ trên cùng thread của sender
B. Xếp Message vào queue để consumer nhận theo poller
C. Chuyển dispatch sang executor thread riêng biệt
D. Lưu Message ở broker trước khi handler xử lý
Đáp án đúng: A

Câu 13. Khi thay DirectChannel bằng ExecutorChannel, điều gì cần chú ý?
A. Đổi thread nên transaction ThreadLocal không tự truyền qua
B. Transaction JDBC của caller được chuyển tự động theo Message
C. ExecutorChannel tự bọc handler bằng REQUIRES_NEW
D. Mỗi lần send được bảo đảm commit trong một session JMS
Đáp án đúng: A

Câu 14. FileReadingMessageSource thường phát payload loại nào?
A. String chứa toàn bộ file sau khi đọc nội dung UTF-8
B. byte[] đã chuyển đổi tự động theo message converter
C. Đối tượng File chỉ đến tệp đã tìm trên local disk
D. InputStream remote của SFTP được giữ bởi poller
Đáp án đúng: C

Câu 15. Để chỉ lấy các file đuôi .csv ở file inbound adapter, nên cấu hình gì?
A. FileWritingMessageHandler với tên file đầu ra .csv
B. Gateway replyChannel với selector cho header contentType
C. JMS message selector áp vào local File object
D. FileListFilter hoặc filename pattern khi scan thư mục
Đáp án đúng: D

Câu 16. Nếu AcceptOnceFileListFilter chỉ nhớ file trong RAM, hệ quả nào có thể xảy ra?
A. Trạng thái file được tự lưu bền vào metadata store
B. File đã nhận tự bị chuyển sang remote archive folder
C. Restart ứng dụng khiến filter đọc lại file cũ
D. Filter tự ghi checksum vào SQL khi ApplicationContext đóng
Đáp án đúng: C

Câu 17. Để tránh xử lý file khi hệ khác còn đang ghi, quy trình nào hữu ích?
A. Tăng nhịp poller để nhận file trước khi bị khóa
B. Gửi message qua ExecutorChannel để hoàn tất file
C. Ghi file tạm và rename sau khi ghi hoàn thành
D. Đặt replyTimeout trên inbound gateway trước khi đọc
Đáp án đúng: C

Câu 18. FileWritingMessageHandler chủ yếu xử lý nhu cầu nào?
A. Poll thư mục nguồn rồi phát File vào MessageChannel
B. Liệt kê thư mục SFTP qua lệnh ls và trả reply
C. Trả response HTTP từ incoming request của gateway
D. Ghi payload Message thành file tại thư mục đích
Đáp án đúng: D

Câu 19. Khi đặt tên file đích từ metadata message, cách nào phù hợp?
A. KafkaHeaders.TOPIC khi không có KafkaTemplate
B. MessageHeaders.REPLY_CHANNEL làm absolute path
C. IntegrationMessageHeaderAccessor.ID thay root directory
D. FileHeaders.FILENAME hoặc expression đặt filename
Đáp án đúng: D

Câu 20. SFTP inbound synchronizing adapter thường làm gì trước khi phát Message?
A. Đồng bộ file SFTP về thư mục local rồi phát file
B. Upload file local lên SFTP rồi bỏ qua reply từ server
C. Chạy lệnh ls và trả danh sách filename cho gateway
D. Chỉ phát stream remote và không cần local directory
Đáp án đúng: A

Câu 21. Khi muốn đọc file SFTP trực tiếp dạng stream, chọn adapter nào?
A. SFTP synchronizing inbound adapter luôn tải local
B. SFTP outbound gateway với lệnh put một chiều
C. SFTP streaming inbound adapter không cần local copy
D. FileWritingMessageHandler ghi file remote từ payload
Đáp án đúng: C

Câu 22. Với SFTP streaming adapter, thao tác nào tránh giữ connection quá lâu?
A. Đóng stream và trả session khi xử lý xong file
B. Giữ InputStream mở trong singleton tới shutdown
C. Để JVM tự hủy SessionFactory lúc garbage collect
D. Tạo static SftpSession dùng chung cho mọi consumer
Đáp án đúng: A

Câu 23. SFTP outbound channel adapter phù hợp với trường hợp nào?
A. Đọc stream file SFTP và phát vào inbound channel
B. Upload file từ Message tới SFTP, không phát reply
C. Thực hiện ls trên server rồi nhận reply Message
D. Poll local file từ directory rồi tạo Message<File>
Đáp án đúng: B

Câu 24. Muốn chạy lệnh ls/get SFTP và dùng kết quả trong flow, chọn gì?
A. SFTP inbound synchronizer chỉ chạy theo poller
B. SFTP outbound gateway trả kết quả lệnh remote
C. SFTP outbound adapter gửi file mà không có reply
D. FileReadingMessageSource quét file trên máy SFTP
Đáp án đúng: B

Câu 25. Muốn ghi nhớ file remote đã lấy sau nhiều lần restart, cần gì?
A. AcceptOnceFileListFilter chỉ có state trong RAM
B. MessageHeaders.ID có giá trị không đổi qua các lần chạy
C. DefaultPollerMetadata tự lưu danh sách file vào cơ sở dữ liệu
D. Persistent file filter dùng MetadataStore để lưu dấu vết
Đáp án đúng: D

Câu 26. Khi thao tác SFTP liên tục tạo session rất tốn kém, nên dùng gì?
A. CachingSessionFactory để tái sử dụng SFTP session
B. Tạo SessionFactory mới cho mỗi message được gửi
C. Giữ một session trong static field toàn ứng dụng
D. Đặt maxMessagesPerPoll cao để pool session tăng vô hạn
Đáp án đúng: A

Câu 27. HTTP inbound gateway xử lý request-reply thế nào?
A. Poll URL HTTP ngoài rồi trả nội dung cho listener
B. Nhận HTTP request và trả response từ reply Message
C. Gửi outbound HTTP request và phát response vào channel
D. Nhận JMS Message rồi gửi HTTP callback đến client
Đáp án đúng: B

Câu 28. Với HTTP webhook không cần phản hồi dữ liệu nghiệp vụ từ flow, chọn gì?
A. HTTP inbound gateway bắt buộc nhận reply Message
B. HTTP outbound gateway gọi dịch vụ webhook ở ngoài
C. HTTP inbound channel adapter cho tiếp nhận một chiều
D. HTTP outbound adapter chuyển request ngược thành inbound
Đáp án đúng: C

Câu 29. HTTP outbound gateway phù hợp với tình huống nào?
A. Nhận HTTP request và chờ reply từ handler nội bộ
B. Phát HTTP request nhưng không chuyển response vào flow
C. Gọi HTTP bên ngoài rồi phát response Message vào flow
D. Poll HTTP URL để đưa message vào inbound channel
Đáp án đúng: C

Câu 30. HTTP outbound channel adapter khác outbound gateway ở điểm nào?
A. Nhận HTTP request rồi đợi handler trả response
B. Nhận một Message từ remote HTTP listener container
C. Tạo replyChannel chứa nội dung của HTTP response
D. Gửi HTTP request nhưng không phát response vào flow
Đáp án đúng: D

Câu 31. Interface khai @MessagingGateway thường cung cấp khả năng nào?
A. Gọi flow bằng method Java thông qua request/reply channels
B. Tự mở endpoint HTTP cho mọi method trên interface
C. Tự tạo poller cho tất cả @Gateway method trả void
D. Biến MessageSource thành một Kafka broker listener
Đáp án đúng: A

Câu 32. Một messaging gateway cần reply nhưng handler không phản hồi, tùy chọn nào có ích?
A. fixedDelay quyết định thời gian đợi response của gateway
B. maxMessagesPerPoll quyết định thời gian timeout reply
C. replyTimeout giới hạn thời gian đợi reply của gateway
D. sendTimeout quyết định mọi handler đã trả reply hay chưa
Đáp án đúng: C

Câu 33. JMS message-driven inbound adapter thường thực hiện luồng nào?
A. Gửi Message tới JMS destination qua JmsTemplate
B. Gửi request JMS và chờ correlation reply từ broker
C. Nhận file qua JDBC poller rồi publish JMS event
D. Nhận JMS Message từ listener rồi gửi vào channel
Đáp án đúng: D

Câu 34. Khi gửi Message tới JMS queue mà không cần reply, dùng thành phần nào?
A. JMS inbound adapter nhận message từ JMS queue
B. JMS outbound gateway tạo request và chờ reply
C. JMS inbound gateway nhận rồi trả JMS response
D. JMS outbound channel adapter gửi message một chiều
Đáp án đúng: D

Câu 35. JMS outbound gateway hỗ trợ tình huống nào?
A. Nhận JMS message-driven event và gửi vào channel
B. Gửi JMS request rồi đợi reply từ consumer bên ngoài
C. Đọc Message từ queue theo poller rồi bỏ qua reply
D. Chỉ chuyển JMS TextMessage thành đối tượng Java
Đáp án đúng: B

Câu 36. Để một JMS outbound gateway nhận đúng reply, yếu tố nào quan trọng?
A. Correlation ID và reply destination để ghép phản hồi
B. Tên bean service dùng làm message selector bắt buộc
C. Kafka partition key quyết định địa chỉ reply queue
D. FileHeaders.FILENAME được dùng làm JMS request ID
Đáp án đúng: A

Câu 37. AMQP inbound gateway khác inbound channel adapter ở điểm nào?
A. Adapter chỉ nhận request khi có replyTo header
B. Gateway bắt buộc dùng poller đọc queue theo cron
C. Adapter trả RPC response tới producer theo mặc định
D. Gateway nhận request và có thể trả reply AMQP
Đáp án đúng: D

Câu 38. Gửi Message qua RabbitMQ mà không cần reply trong flow nên dùng gì?
A. AMQP inbound gateway nhận request rồi gửi response
B. AMQP outbound gateway gửi RPC và chờ kết quả
C. AMQP outbound channel adapter phát message ra broker
D. AMQP inbound channel adapter nhận message broker
Đáp án đúng: C

Câu 39. Nếu cần RPC qua RabbitMQ rồi xử lý kết quả, thành phần nào phù hợp?
A. AMQP outbound channel adapter không trả reply Message
B. AMQP outbound gateway gửi request rồi phát reply
C. AMQP inbound gateway nhận request từ Rabbit listener
D. AMQP inbound adapter đưa event vào MessageChannel
Đáp án đúng: B

Câu 40. Kafka message-driven inbound adapter thường thực hiện gì?
A. Tạo Kafka record để gửi đến topic trên broker
B. Nhận Kafka record từ consumer và phát vào channel
C. Poll SQL query rồi chuyển row sang Kafka record
D. Gọi HTTP service rồi publish reply vào Kafka topic
Đáp án đúng: B

Câu 41. Kafka outbound channel adapter thường dùng để làm gì?
A. Gửi Message từ flow thành Kafka record tới topic
B. Nhận Kafka record rồi phát vào inbound MessageChannel
C. Chờ RPC response từ Kafka qua message reply channel
D. Poll file remote rồi tự phân phối vào Kafka partition
Đáp án đúng: A

Câu 42. Khi một Kafka inbound adapter xử lý lỗi, điều gì ảnh hưởng redelivery?
A. Chỉ MessageHeaders.ID quyết định offset được commit
B. Chính sách offset, acknowledgement và error handler
C. Thêm QueueChannel sẽ bảo đảm mỗi record xử lý một lần
D. Đổi poller fixedRate là broker tự gửi lại dữ liệu
Đáp án đúng: B

Câu 43. JDBC inbound channel adapter lấy dữ liệu theo cơ chế nào?
A. Subscribe JDBC transaction log mà không cần CDC adapter
B. Nhận callback từ trigger SQL qua HTTP request
C. Poll Kafka topic rồi viết row vào database đích
D. Poll SQL query theo lịch và phát kết quả vào channel
Đáp án đúng: D

Câu 44. JDBC outbound channel adapter thường phục vụ tác vụ nào?
A. Poll SQL select rồi phát các row vào channel
B. Chạy SQL query và chuyển row list thành reply Message
C. Chạy SQL update từ Message mà không trả reply
D. Nhận JDBC event rồi trả response HTTP cho client
Đáp án đúng: C

Câu 45. Khi cần gửi SQL query và nhận dữ liệu cho bước tiếp theo, dùng gì?
A. JDBC outbound adapter chỉ thực thi SQL update một chiều
B. JDBC outbound gateway trả kết quả query thành reply
C. JDBC inbound adapter poll dữ liệu theo lịch độc lập
D. JDBC poller trả reply theo requestMessage headers
Đáp án đúng: B

Câu 46. Khi endpoint bất đồng bộ phát sinh lỗi, làm sao định tuyến lỗi vào flow?
A. Phát ErrorMessage tới errorChannel theo cấu hình
B. Tự biến exception thành Message với header replyChannel
C. Poller tự commit lỗi rồi bỏ qua ErrorMessage
D. MessageHeaders.ID làm khóa định tuyến exception
Đáp án đúng: A

Câu 47. Khi retry và redelivery có thể tạo message trùng, xử lý nào phù hợp?
A. Retry vô hạn rồi dựa broker tự loại side effect trùng
B. Tắt correlation header để broker tự đánh dấu message
C. Giới hạn retry và dùng idempotency theo business key
D. Tăng consumer concurrency để bảo đảm exactly-once
Đáp án đúng: C

Câu 48. Muốn kiểm thử adapter cùng broker hay remote service mà không ảnh hưởng production, nên làm gì?
A. Chỉ unit test từng handler, không cần MessageChannel
B. Dùng dịch vụ thử nghiệm và kiểm tra trao đổi end-to-end
C. Chỉ xác nhận bean adapter đã khởi tạo trong context
D. Mock protocol rồi coi session remote đã được xác thực
Đáp án đúng: B
