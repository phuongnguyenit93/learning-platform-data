Câu 1. Khi tích hợp Jakarta Messaging trong Spring, Spring JMS chủ yếu cung cấp điều gì?
A. Một broker lưu queue ngay trong ApplicationContext
B. Cơ chế thay thế hoàn toàn giao thức JMS của provider
C. Một database transaction manager dùng chung mọi broker
D. Template và listener container làm việc với JMS provider
Đáp án đúng: D

Câu 2. Khi nhiều consumer cùng nhận trên một queue JMS, hành vi thông thường là gì?
A. Mỗi message được gửi tới tất cả consumer của queue
B. Mỗi message được phân phối cho một consumer đủ điều kiện
C. Message chỉ được nhận nếu consumer dùng durable subscription
D. Message được nhân bản cho từng listener trong cùng session
Đáp án đúng: B

Câu 3. Với topic JMS, lựa chọn nào mô tả đúng mô hình phân phối?
A. Mỗi message chỉ cấp cho một consumer trên toàn topic
B. Topic luôn xử lý theo một luồng consumer duy nhất
C. Consumer phải dùng receiveAndConvert để được đăng ký
D. Publisher gửi tới các subscription đủ điều kiện
Đáp án đúng: D

Câu 4. Khi dùng JmsTemplate để gửi tới topic thay cho queue, cấu hình nào liên quan?
A. Bật pubSubDomain cho chế độ destination dạng topic
B. Bật sessionTransacted để tự chuyển queue thành topic
C. Đặt receiveTimeout dương để tạo một topic destination
D. Dùng @EnableJms để thay đổi mọi destination sang topic
Đáp án đúng: A

Câu 5. JMS ConnectionFactory có trách nhiệm chính nào?
A. Định tuyến message qua các repository của Spring Data
B. Ánh xạ TextMessage thành POJO theo tên destination
C. Chọn advice chạy quanh từng lời gọi JMS listener
D. Cung cấp connection tới hệ thống JMS theo cấu hình
Đáp án đúng: D

Câu 6. Đối với JmsTemplate đã cấu hình, nhận định nào về việc dùng lại phù hợp?
A. Cần tạo JmsTemplate mới cho từng message được gửi
B. Có thể tái sử dụng để gửi nhận qua các lời gọi khác nhau
C. Nên giữ Session riêng trong field của JmsTemplate dùng chung
D. Chỉ được dùng trong thread của listener container
Đáp án đúng: B

Câu 7. Khi cần tự tạo TextMessage và đặt property trước khi gửi, nên dùng gì?
A. JmsTemplate.send kết hợp MessageCreator tạo message
B. JmsTemplate.receiveAndConvert với converter mặc định
C. @JmsListener để tạo message trong phương thức consumer
D. DefaultJmsListenerContainerFactory để gửi một message
Đáp án đúng: A

Câu 8. Khác biệt thường gặp của convertAndSend so với send là gì?
A. Payload được chuyển thành JMS Message trước khi gửi
B. Payload được phát tới mọi queue trên cùng ConnectionFactory
C. Message luôn được gửi trong một transaction XA
D. Message được nhận và xác nhận trước khi hàm trả về
Đáp án đúng: A

Câu 9. Nếu gọi receiveAndConvert mà queue chưa có message, điều gì cần chú ý?
A. Lời gọi tự tạo một placeholder message và trả về ngay
B. Listener container tự khởi tạo để nhận thay cho thread gọi
C. Lời gọi có thể chờ theo receiveTimeout được cấu hình
D. Broker bắt buộc phát exception ngay khi queue trống
Đáp án đúng: C

Câu 10. Khi muốn lời gọi receive không chờ vô hạn, lựa chọn nào phù hợp?
A. Bật pubSubDomain vì topic không bao giờ chặn receive
B. Đặt receiveTimeout dương để giới hạn thời gian đợi
C. Đặt sessionTransacted để receive tự trở thành nonblocking
D. Dùng @SendTo để biến receive thành async callback
Đáp án đúng: B

Câu 11. Trong cấu hình Spring JMS dùng annotation, @EnableJms được dùng để làm gì?
A. Kích hoạt hạ tầng phát hiện và xử lý @JmsListener
B. Đăng ký một JMS provider mới vào classpath ứng dụng
C. Tự tạo queue vật lý cho mỗi lớp có annotation @Service
D. Bật JSON serialization cho toàn bộ JMS destinations
Đáp án đúng: A

Câu 12. Annotation @JmsListener(destination="orders") thường khai báo điều gì?
A. Một method phát message lên topic orders lúc khởi động
B. Một bean ConnectionFactory mang tên orders
C. Một listener endpoint tiêu thụ từ destination orders
D. Một transaction manager áp dụng cho queue orders
Đáp án đúng: C

Câu 13. Vì sao method có @JmsListener thường cần thuộc bean Spring quản lý?
A. Annotation tự được JVM gọi khi tạo object bằng new
B. Provider JMS tự quét toàn bộ classpath để tìm method
C. Spring phát hiện listener trên các bean được quản lý
D. Method sẽ hoạt động dù ApplicationContext chưa tạo
Đáp án đúng: C

Câu 14. Khi có hai listener container factory khác cấu hình, @JmsListener chọn một factory bằng gì?
A. Gắn @Primary trên tên queue trong destination string
B. Chỉ định thuộc tính containerFactory theo tên bean
C. Đặt tên phương thức trùng class của factory cần dùng
D. Chỉ tăng concurrency để Spring tự chọn factory khác
Đáp án đúng: B

Câu 15. DefaultJmsListenerContainerFactory thường được cấu hình để cung cấp gì?
A. Một MessageCreator tự gửi cho mọi queue lúc startup
B. Một JMS Message chỉ giữ payload dưới dạng byte[]
C. Một subscription manager độc lập khỏi ConnectionFactory
D. Các thiết lập cho container nhận message của listener
Đáp án đúng: D

Câu 16. Nếu tăng concurrency listener trên queue từ một consumer lên nhiều consumer, hệ quả nào đáng xem xét?
A. Mọi message sẽ được nhân bản sang tất cả consumer
B. Tăng xử lý song song nhưng có thể ảnh hưởng thứ tự
C. JMS sẽ luôn giữ thứ tự xử lý nghiệp vụ trên nhiều thread
D. Mỗi consumer tự tạo một destination khác nhau
Đáp án đúng: B

Câu 17. Khi @JmsListener nhận payload String từ TextMessage, việc bind payload phụ thuộc vào gì?
A. Tên queue phải trùng tên biến String trong method
B. ClientID của listener phải bằng nội dung TextMessage
C. Converter ánh xạ từ TextMessage sang tham số String
D. Session phải dùng CLIENT_ACKNOWLEDGE trước khi bind
Đáp án đúng: C

Câu 18. Nếu listener cần lấy JMSCorrelationID riêng trong tham số method, cơ chế nào phù hợp?
A. Sử dụng @Header với tên JMS header tương ứng
B. Sử dụng @Payload để bind correlation ID thành message body
C. Sử dụng @SendTo trên tham số để đọc header từ request
D. Đặt tên @JmsListener trùng với giá trị correlation ID
Đáp án đúng: A

Câu 19. SimpleMessageConverter mặc định của Spring JMS thường chuyển String thành kiểu message nào?
A. TextMessage khi chuyển String sang JMS message
B. BytesMessage khi chuyển String sang JMS message
C. MapMessage khi chuyển String sang JMS message
D. StreamMessage khi chuyển String sang JMS message
Đáp án đúng: A

Câu 20. Khi gửi nhận POJO dưới dạng JSON qua JMS, giải pháp nào phù hợp?
A. Đổi MessageCreator thành JmsTransactionManager để serialize
B. Dùng ObjectMessage và mặc định coi Java serialization là JSON
C. Cấu hình MappingJackson2MessageConverter với type metadata
D. Chỉ đặt pubSubDomain=true để kích hoạt Jackson converter
Đáp án đúng: C

Câu 21. Để thêm JMSCorrelationID lên message khi dùng convertAndSend, hook nào phù hợp?
A. ErrorHandler chỉnh message sau khi listener xử lý thành công
B. DestinationResolver tự chèn mọi correlation ID từ payload
C. JmsListenerEndpointRegistry gắn header vào mọi outgoing message
D. MessagePostProcessor chỉnh message sau conversion, trước send
Đáp án đúng: D

Câu 22. JMS message selector chủ yếu dùng nguồn dữ liệu nào khi lọc message?
A. JSON field trong body được tự động parse qua Jackson
B. Selector lọc theo header và property, không đọc body
C. Các dòng log do listener container phát ra sau xử lý
D. Tên Java method consumer thay cho message property
Đáp án đúng: B

Câu 23. Muốn selector tier = 'gold' hoạt động, sender cần chuẩn bị gì?
A. Đặt tên destination thành tier.gold khi gửi message
B. Đặt JSON body có field tier mà không cần property
C. Đặt property tier kiểu phù hợp trên JMS Message
D. Đặt @Qualifier("gold") trên bean ConnectionFactory
Đáp án đúng: C

Câu 24. Trong luồng request-reply qua JMS, JMSCorrelationID thường hỗ trợ mục tiêu gì?
A. Ghép response với request có định danh liên quan
B. Chọn mode topic thay cho queue khi listener khởi động
C. Giữ message tránh bị retry nếu listener ném exception
D. Gắn tên bean gửi vào subscription durable ở broker
Đáp án đúng: A

Câu 25. Khi requester muốn chỉ rõ queue để gửi response, JMS header nào thích hợp?
A. JMSExpiration mang tên queue nhận phản hồi
B. JMSPriority mang route trở về cho requester
C. JMSReplyTo mang destination dùng cho phản hồi
D. JMSType chứa tên ConnectionFactory của người gửi
Đáp án đúng: C

Câu 26. Một JMS Message có JMSMessageID do provider cấp thường được dùng ra sao?
A. Bảo đảm logic consumer chỉ chạy đúng một lần trọn đời
B. Tự thay thế mọi business key khi lưu dữ liệu ứng dụng
C. Hỗ trợ định danh và theo dõi message trong hệ thống
D. Làm khóa giao dịch XA dùng chung nhiều hệ cơ sở dữ liệu
Đáp án đúng: C

Câu 27. Khi @JmsListener trả về giá trị và cần gửi tới đích trả lời cố định, có thể dùng gì?
A. @SendTo chỉ định destination nhận kết quả từ listener
B. @EnableJms trên return type để tự tạo reply queue
C. @Primary trên ConnectionFactory để định tuyến response
D. @AfterReturning trong class @Aspect thay thế gửi JMS reply
Đáp án đúng: A

Câu 28. Khi listener container dùng sessionTransacted=true, xử lý thành công thường dẫn tới gì?
A. Session được commit để xác nhận thao tác JMS của lượt xử lý
B. Mọi transaction JDBC hiện có cũng commit đồng thời
C. Message được chuyển sang topic để đánh dấu đã hoàn tất
D. Provider tự loại toàn bộ message khác cùng JMSCorrelationID
Đáp án đúng: A

Câu 29. Nếu listener đang xử lý trong JMS session transacted rồi ném lỗi và session rollback, điều gì có thể xảy ra?
A. Message đã bị xóa vĩnh viễn trước khi code listener chạy
B. Message có thể được redeliver theo chính sách của broker
C. Message sẽ tự chuyển thành một HTTP retry qua WebClient
D. Transaction của database khác tự rollback theo JMS session
Đáp án đúng: B

Câu 30. Với DefaultMessageListenerContainer dùng AUTO_ACKNOWLEDGE, giả định nào rủi ro?
A. Listener có thể nhận TextMessage được Spring chuyển đổi
B. Container vẫn cần connection và session do provider cấp
C. Acknowledgement phụ thuộc mode và loại listener container
D. Lỗi callback mặc nhiên dẫn đến broker phát lại message
Đáp án đúng: D

Câu 31. Khi cần điều khiển xác nhận message sau xử lý, tính năng JMS nào đáng cân nhắc?
A. Message selector vì nó tự xác nhận mọi message lọc ra
B. CLIENT_ACKNOWLEDGE với cơ chế ack của JMS Session
C. MessageConverter vì JSON hợp lệ đồng nghĩa đã ack
D. setPubSubDomain vì topic cung cấp manual ack riêng
Đáp án đúng: B

Câu 32. JmsTransactionManager của Spring chủ yếu quản lý phạm vi nào?
A. Một transaction XA chung cho mọi DataSource được inject
B. Transaction HTTP và JMS cùng trong WebFlux request
C. Local transaction của JMS Session trên ConnectionFactory
D. Transaction persistence của JPA EntityManager được chọn
Đáp án đúng: C

Câu 33. Nếu nghiệp vụ phải ghi database và phát JMS đáng tin cậy nhưng không có XA, chiến lược nào phù hợp?
A. Gọi convertAndSend trước commit DB rồi coi là nguyên tử
B. Đặt @JmsListener trên repository để kết nối hai transaction
C. Dùng @Primary để database và queue chung commit boundary
D. Transactional outbox để phối hợp commit dữ liệu và phát tin
Đáp án đúng: D

Câu 34. Dead-letter queue trong hệ thống JMS thường được điều khiển chủ yếu ở đâu?
A. JmsTemplate tự tạo một DLQ cho mỗi lời gọi send
B. MessageConverter tự chuyển JSON lỗi thành DLQ
C. Chính sách của broker về message không xử lý được
D. @SendTo tự đăng ký DLQ cho mọi @JmsListener
Đáp án đúng: C

Câu 35. Với một poison message liên tục làm listener thất bại, cách xử lý nào phù hợp?
A. Retry liên tục không giới hạn để luôn giữ thứ tự queue
B. Giới hạn redelivery rồi chuyển message gây lỗi vào DLQ
C. Bỏ transaction để message tự biến mất khỏi queue
D. Đổi consumer thành topic để xoá message gây lỗi
Đáp án đúng: B

Câu 36. Vì sao handler nhận JMS nên được thiết kế idempotent?
A. Session transacted bảo đảm business logic chạy đúng một lần
B. Broker tự rollback mọi HTTP side effect của consumer
C. Message có thể được giao lại khi thất bại hoặc retry
D. Selector giúp loại toàn bộ message trùng theo body
Đáp án đúng: C

Câu 37. Header JMSRedelivered nên được hiểu thế nào trong ứng dụng?
A. Tín hiệu message có thể đã được phân phối trước đó
B. Bằng chứng chính xác consumer đã ghi DB thành công trước
C. Cam kết broker sẽ không giao lại message lần nữa
D. Cơ chế xác nhận message thay cho session acknowledgement
Đáp án đúng: A

Câu 38. Khi JmsTemplate.send trả về mà không có lỗi, điều gì được xác nhận hợp lý?
A. Consumer đã commit transaction nghiệp vụ với message đó
B. Tất cả subscriber của topic đã lưu kết quả xuống database
C. Message đã qua DLQ rồi được xử lý thành công
D. Gửi tới provider hoàn tất, chưa chứng minh consumer đã xử lý
Đáp án đúng: D

Câu 39. Nếu một queue có nhiều consumer song song, cần lưu ý điều gì về thứ tự xử lý?
A. JMS sẽ chặn mọi consumer phụ cho tới khi consumer đầu commit
B. Thứ tự hoàn tất nghiệp vụ có thể khác thứ tự message được gửi
C. Mọi handler được chạy trên cùng một thread dù concurrency tăng
D. Broker sẽ tự tuần tự hóa transaction ở tất cả service
Đáp án đúng: B

Câu 40. Một durable subscription trên topic nhằm giải quyết nhu cầu nào?
A. Biến topic thành queue có duy nhất một subscriber đang chạy
B. Thay thế hoàn toàn broker persistence bằng memory cache
C. Giữ message cho subscription khi subscriber tạm offline
D. Bỏ yêu cầu định danh subscription khi kết nối lại
Đáp án đúng: C

Câu 41. Khi subscriber topic không durable bị offline trong lúc publisher gửi, điều gì nên dự kiến?
A. Broker tự lưu toàn bộ message vô hạn cho subscriber đó
B. Subscription trở thành durable nếu listener có @Component
C. JmsTemplate tự replay message khi subscriber kết nối lại
D. Message lúc subscriber offline thường không được giữ lại
Đáp án đúng: D

Câu 42. Khi nhiều lời gọi JMS ngắn cần giảm chi phí tạo session, lựa chọn nào phù hợp?
A. Tạo raw ConnectionFactory và đóng toàn bộ broker sau mỗi send
B. CachingConnectionFactory để tái sử dụng tài nguyên JMS theo cấu hình
C. Đổi mọi queue thành topic để provider giữ session cache
D. Dùng receiveTimeout âm để session không bao giờ được trả về
Đáp án đúng: B

Câu 43. DefaultMessageListenerContainer thường chịu trách nhiệm gì khi Spring context chạy?
A. Quản lý consumer, session và vòng đời listener
B. Tự tạo schema quan hệ cho payload của mọi destination
C. Chuyển JMS Message thành HTTP response của controller
D. Lưu toàn bộ message vào Map trước khi listener xử lý
Đáp án đúng: A

Câu 44. Khi muốn nhận thông báo lỗi không được xử lý từ listener callback, nên cấu hình gì?
A. MessagePostProcessor trên JmsTemplate gửi message đi
B. DestinationResolver để đổi queue khi callback lỗi
C. MessageSelector để tự ghi stack trace của listener
D. Thiết lập ErrorHandler trên JMS listener container
Đáp án đúng: D

Câu 45. Vì sao nên dùng JmsTemplate và listener container thay vì tự giữ Session dùng chung tùy ý?
A. Một Session JMS mặc định thread-safe cho mọi listener
B. Template tự biến broker thành bộ nhớ trong process
C. Container bảo đảm mọi DB transaction commit cùng JMS
D. Template và container hỗ trợ quản lý tài nguyên JMS
Đáp án đúng: D

Câu 46. Để kiểm thử @JmsListener gồm selector, conversion và redelivery, cách nào hiệu quả?
A. Kiểm thử tích hợp với broker cùng dữ liệu kiểm soát
B. Chỉ unit test @Component được scan mà không gửi message
C. Chỉ mock JmsTemplate để kết luận broker redeliver đúng
D. Chỉ kiểm tra phương thức listener có annotation đúng
Đáp án đúng: A

Câu 47. Khi vận hành JMS production, nhóm số liệu nào nên theo dõi?
A. Tên từng method listener và số lượng class trong jar
B. Độ sâu queue, redelivery, lỗi listener và độ trễ xử lý
C. Số lần Java compiler tạo bytecode của JmsTemplate
D. Số field JSON trong từng payload như tag metric riêng
Đáp án đúng: B

Câu 48. Khi trace đi qua sender JMS sang listener, cần cân nhắc điều gì?
A. Dựa vào ThreadLocal sender vì context tự qua broker
B. Đặt cùng bean name cho sender và listener để nối trace
C. Tăng concurrency để broker sinh cùng traceId cho mọi message
D. Propagate trace context qua message property/header phù hợp
Đáp án đúng: D
