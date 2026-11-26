Câu 1. Một IntegrationFlow được khai báo bằng Java DSL thường biểu diễn điều gì khi ứng dụng chạy?
A. Chuỗi endpoint và channel được container khởi tạo quản lý
B. Một thread riêng được tạo cho mỗi dòng trong DSL
C. Một broker message được nhúng ngay trong ApplicationContext
D. Một JMS session độc lập cho mỗi method của flow
Đáp án đúng: A

Câu 2. Khi khai báo @Bean trả về IntegrationFlow, Spring Integration thường làm gì?
A. Chỉ chạy method DSL mỗi lần có một Message mới
B. Đăng ký các thành phần flow vào ApplicationContext
C. Tạo một JDBC schema lưu toàn bộ definition của flow
D. Biến flow thành một REST controller không cần endpoint
Đáp án đúng: B

Câu 3. Một message-producing endpoint triển khai SmartLifecycle có autoStartup=true thường được xử lý thế nào?
A. Chỉ chạy sau lời gọi start() thủ công từ mỗi sender
B. Tự tạo scheduler cố định cho tất cả inbound gateway
C. Bắt đầu chạy chỉ sau khi ApplicationContext đã đóng
D. Được khởi động khi context refresh theo lifecycle
Đáp án đúng: D

Câu 4. Khi cần cấu hình inbound endpoint không tự nhận dữ liệu sau startup, nên làm gì?
A. Đặt replyTimeout=0 để listener không được khởi động
B. Chuyển channel thành DirectChannel và bỏ MessageSource
C. Đặt autoStartup=false rồi chủ động start khi sẵn sàng
D. Bỏ hẳn ConsumerEndpointFactoryBean ra khỏi context
Đáp án đúng: C

Câu 5. Muốn thêm IntegrationFlow trong lúc ứng dụng đang chạy, API nào phù hợp?
A. Dùng BeanFactoryPostProcessor sau khi context refresh
B. Dùng MessageHeaders tạo endpoint mỗi lần gửi Message
C. Dùng IntegrationFlowContext để đăng ký flow động
D. Dùng MessageStore đăng ký bean definition mới
Đáp án đúng: C

Câu 6. Sau khi đăng ký flow động và muốn gỡ nó an toàn, thao tác nào phù hợp?
A. Chỉ gọi System.gc() để JVM giải phóng các endpoint
B. Xóa tên channel trong payload của Message kế tiếp
C. Đóng DataSource để mọi flow khác tự hủy theo
D. Dùng IntegrationFlowRegistration.destroy() để gỡ flow
Đáp án đúng: D

Câu 7. Khi gửi biểu thức @ordersEndpoint.stop() vào control bus, mục tiêu là gì?
A. Điều khiển ordersEndpoint.stop() qua control bus của ứng dụng
B. Xóa toàn bộ Message đã từng được xử lý bởi endpoint
C. Hủy bean definition mà không quan tâm lifecycle hiện tại
D. Bắt đầu một transaction mới cho mọi handler trong flow
Đáp án đúng: A

Câu 8. Khi một Service Activator tiêu thụ Message, endpoint thường gọi gì?
A. MessageSource.receive() để tạo một nguồn polling mới
B. MessageHandler thực thi nghiệp vụ từ message nhận
C. TransactionManager.commit() trước khi đọc payload
D. ReplyChannel.subscribe() để tự định nghĩa handler mới
Đáp án đúng: B

Câu 9. DirectChannel mặc định thực hiện dispatch tới handler bằng cách nào?
A. Gọi handler đồng bộ trong thread đang gửi Message
B. Đưa Message vào queue để worker chủ động receive()
C. Chuyển xử lý sang executor pool khác theo cấu hình
D. Phát bản sao Message tới mọi consumer cùng đăng ký
Đáp án đúng: A

Câu 10. ExecutorChannel tạo ra khác biệt quan trọng nào so với DirectChannel?
A. Đưa handler sang TaskExecutor và có thể đổi thread
B. Mặc định persist Message trước khi gọi MessageHandler
C. Gọi mọi handler trên cùng sender thread theo thứ tự
D. Tự tạo một reply Message khi handler không trả kết quả
Đáp án đúng: A

Câu 11. QueueChannel phù hợp khi bên nhận muốn làm gì?
A. Nhận callback ngay khi đăng ký MessageHandler subscribe
B. Nhận broadcast copy cùng lúc với mọi subscriber
C. Gọi receive() để chủ động lấy Message từ queue
D. Tự tạo HTTP response cho inbound MessageGateway
Đáp án đúng: C

Câu 12. PublishSubscribeChannel thường phù hợp cho tình huống nào?
A. Đảm bảo một Message chỉ có một consumer trên channel
B. Bắt mỗi subscriber poll MessageSource theo fixedRate
C. Lưu Message bền vững vào database theo mặc định
D. Phát một Message đến nhiều subscriber của channel
Đáp án đúng: D

Câu 13. Với QueueChannel có capacity giới hạn và đã đầy, send có thể chịu ảnh hưởng của gì?
A. Chờ gửi hoặc thất bại nếu QueueChannel đã đầy
B. Reply timeout của một gateway không liên quan queue
C. Số lượng topic mà JMS broker đang quảng bá
D. Kiểu scalar của payload trong MessageHeaders
Đáp án đúng: A

Câu 14. Khi muốn bỏ Message có chủ đích mà không chuyển cho consumer thật, channel nào hữu ích?
A. nullChannel xử lý theo hướng bỏ Message được gửi đến
B. QueueChannel chờ đến khi consumer nhận Message
C. ExecutorChannel tiếp tục chạy business logic nền
D. PublishSubscribeChannel phát tới mọi subscriber đã đăng ký
Đáp án đúng: A

Câu 15. WireTap gắn vào channel thường hỗ trợ nhu cầu gì?
A. Thay payload chính bằng một bản ghi của MessageStore
B. Tự retry mọi endpoint bị lỗi phía sau channel
C. Gửi bản sao Message sang kênh quan sát riêng
D. Chuyển mọi channel từ đồng bộ sang bất đồng bộ
Đáp án đúng: C

Câu 16. Khi PublishSubscribeChannel không cấu hình executor, điều gì dễ xảy ra nếu một subscriber xử lý chậm?
A. Mỗi subscriber mặc định được chạy trên một thread riêng
B. Sender phải chờ subscriber chậm trong quá trình dispatch
C. Channel tự loại subscriber chậm và chuyển sang poller
D. Message được ghi xuống JDBC store trước khi phát
Đáp án đúng: B

Câu 17. Một polling consumer khác message-driven consumer chủ yếu ở đâu?
A. Polling consumer nhận callback ngay khi Message được gửi
B. Consumer chủ động nhận từ PollableChannel theo poller
C. Message-driven consumer bắt buộc dùng cron cho mỗi message
D. Message-driven consumer chỉ xử lý được Message từ JDBC
Đáp án đúng: B

Câu 18. Khi poller có fixedDelay, thời điểm lần kích hoạt tiếp thường tính thế nào?
A. Từ thời điểm ứng dụng khởi động không xét lượt chạy
B. Từ lúc JMS consumer gửi acknowledgement tới broker
C. Từ sau mỗi lần gateway nhận reply trong cùng flow
D. Từ khi lần chạy trước kết thúc rồi chờ khoảng delay
Đáp án đúng: D

Câu 19. maxMessagesPerPoll=5 trên poller nên được hiểu là gì?
A. Hàng đợi QueueChannel được giới hạn đúng năm phần tử
B. Mỗi lần kích hoạt poller lấy tối đa năm Message
C. Mỗi endpoint chỉ được gửi năm Message trong đời ứng dụng
D. Mọi message payload bị giới hạn trong năm kilobyte
Đáp án đúng: B

Câu 20. Khi gắn TaskExecutor vào poller để xử lý đồng thời, điều gì cần quan tâm?
A. Mọi Message được bảo đảm xử lý theo thứ tự poll ban đầu
B. Các tác vụ poll có thể chồng lấn thời gian và tranh tài nguyên
C. Transaction JDBC của scheduler luôn truyền sang thread mới
D. Poller tự duy trì một session global cho mọi handler
Đáp án đúng: B

Câu 21. Khi một splitter phát nhiều phần tử từ một Message, header nào thường phục vụ ghép nhóm lại?
A. replyTimeout, sendTimeout và channel capacity của flow
B. contentType, fileName và lastModified của source
C. priority, errorChannel và integrationFlowId của bean
D. correlationId cùng sequenceNumber và sequenceSize
Đáp án đúng: D

Câu 22. Aggregator dùng correlation strategy chủ yếu để làm gì?
A. Chọn TaskExecutor để chuyển việc xử lý giữa các thread
B. Gán các Message liên quan vào cùng một message group
C. Xác định bean lifecycle nào phải start trước broker
D. Biến Message payload thành JDBC ResultSet từ metadata
Đáp án đúng: B

Câu 23. ReleaseStrategy của aggregator quyết định điều gì?
A. Tên MessageChannel mà splitter sẽ gửi fragment
B. Kích thước queue sẽ được lưu vào một MessageStore
C. Điều kiện khi nào một message group đủ để phát kết quả
D. Bắt buộc transaction manager commit trước khi nhận
Đáp án đúng: C

Câu 24. Nếu aggregator phải xử lý nhóm chưa đủ fragment sau một khoảng thời gian, cần cân nhắc gì?
A. Đặt autoStartup=false trên toàn ApplicationContext
B. Group timeout và policy release một phần hoặc loại
C. Dùng DirectChannel để mặc định sinh missing fragment
D. Tắt correlation header cho những fragment chưa đến
Đáp án đúng: B

Câu 25. MessageGroupStore trong runtime Spring Integration phục vụ nhu cầu gì?
A. Lưu định nghĩa Java bean của mọi IntegrationFlow
B. Lưu trạng thái các nhóm Message phục vụ aggregator
C. Lưu tất cả Java thread và stack trace của poller
D. Thay message converter để chuyển object thành JSON
Đáp án đúng: B

Câu 26. Khi QueueChannel cần lưu message bền vững hơn in-memory, lựa chọn nào phù hợp?
A. Dùng DirectChannel vì nó luôn ghi message vào database
B. Đặt @Transactional trên DTO để tự lưu payload
C. Cấu hình ChannelMessageStore có backend bền vững
D. Bật replyChannel để message không mất sau restart
Đáp án đúng: C

Câu 27. MetadataStore thường phù hợp để lưu loại trạng thái nào của flow?
A. Toàn bộ object graph bean và classloader của flow
B. Mọi Message payload của một QueueChannel không cấu hình
C. Mọi HTTP response trong ApplicationContext cache
D. Lưu metadata xử lý hoặc khóa phục vụ phát hiện trùng lặp
Đáp án đúng: D

Câu 28. IdempotentReceiverInterceptor có thể giúp flow kiểm soát điều gì?
A. Tự tạo transaction XA cho mỗi message mới nhận
B. Thay Poller bằng WebSocket message-driven source
C. Phát hiện Message trùng qua idempotency key
D. Bảo đảm broker không bao giờ gửi lại cùng payload
Đáp án đúng: C

Câu 29. Nếu một message có thể được giao lại do retry hoặc broker redelivery, handler nên có đặc điểm gì?
A. Dựa vào MessageHeaders.ID mặc định để bảo đảm exactly-once
B. Idempotent theo khóa nghiệp vụ để tránh side effect trùng
C. Bắt mọi exception rồi luôn ghi kết quả thành công
D. Dùng QueueChannel vô hạn để không cần deduplication
Đáp án đúng: B

Câu 30. Với DirectChannel đồng bộ, nếu handler ném exception và không có advice bắt lỗi, sender thường thấy gì?
A. Exception có thể lan ngược về lời gọi send của sender
B. Lỗi được lưu bền vào queue và sender luôn thành công
C. Message luôn bị broker gửi lại mà không cần transaction
D. Gateway tự trả phản hồi thành công dù handler thất bại
Đáp án đúng: A

Câu 31. Khi xử lý trong ExecutorChannel bị lỗi ngoài thread sender, cơ chế nào hữu ích?
A. Ném cùng Throwable trực tiếp vào stack của sender
B. Đặt replyTimeout để tự convert mọi lỗi thành JSON
C. Gọi DirectChannel.send lần nữa trên thread của caller
D. Phát ErrorMessage tới errorChannel được cấu hình
Đáp án đúng: D

Câu 32. ErrorMessage trong Spring Messaging thường mang payload kiểu gì?
A. TransactionStatus dùng để commit message bị lỗi
B. MessageChannel chứa danh sách subscriber gặp lỗi
C. MessageGroupStore chứa các fragment đã release
D. Throwable chứa thông tin lỗi của quá trình xử lý
Đáp án đúng: D

Câu 33. Khi endpoint được cấu hình errorChannel riêng, mục đích chính là gì?
A. Định tuyến thông tin lỗi tới flow xử lý sự cố đã chọn
B. Chuyển mọi lời gọi đồng bộ thành transaction XA
C. Thay thế replyChannel bằng queue lưu mọi message
D. Bật retry vô hạn cho message trước khi báo lỗi
Đáp án đúng: A

Câu 34. RequestHandlerRetryAdvice chủ yếu được áp dụng ở đâu?
A. Bên trong MessageSource để tăng maxMessagesPerPoll
B. Trên MessageChannel để thay toàn bộ channel type
C. Retry quanh lời gọi của MessageHandler
D. Trên ApplicationContext để retry refresh bean
Đáp án đúng: C

Câu 35. Khi retry của một handler đã hết lượt mà vẫn lỗi, lựa chọn vận hành nào phù hợp?
A. Tiếp tục retry vô hạn để broker tự hủy message
B. Đưa lỗi sau lượt retry cuối vào recoverer hoặc error flow
C. Commit mọi transaction ngoài bất kể exception cuối
D. Bỏ correlationId để lỗi không truyền đến caller
Đáp án đúng: B

Câu 36. Khi dùng retry advice với downstream không idempotent, rủi ro nào cần chú ý?
A. Advice tự đảm bảo external API chỉ được gọi một lần
B. Retry mặc định rollback mọi HTTP side effect trước đó
C. Lời gọi lặp có thể tạo side effect nghiệp vụ trùng
D. Retry luôn tạo message ID mới và loại được bản trùng
Đáp án đúng: C

Câu 37. Khi poller dùng transactional advice và flow downstream chạy đồng bộ, phạm vi transaction thường như thế nào?
A. Bao bước polling và xử lý downstream đồng bộ trong transaction
B. Chỉ bao scheduler trước khi bất kỳ Message nào được đọc
C. Bao cả TaskExecutor ở thread khác mà không cần context
D. Tự gộp mọi broker transaction vào cùng một XA global
Đáp án đúng: A

Câu 38. Khi flow qua ExecutorChannel, transaction JDBC gắn ThreadLocal ở sender sẽ ra sao?
A. Luôn tiếp tục trên thread worker với cùng JDBC Connection
B. Tự commit vào lúc executor chấp nhận Message
C. Được giữ nguyên trong MessageHeaders mặc định của Spring
D. Không tự mang transaction từ sender sang thread mới
Đáp án đúng: D

Câu 39. Trong một flow ghi database rồi gửi message ra broker khác, điều nào cần lưu ý?
A. Local transaction không commit nguyên tử cả hai resource
B. Một @Transactional JDBC sẽ commit luôn broker transaction
C. DirectChannel tự biến hai resource thành XA transaction
D. ErrorChannel sẽ rollback các side effect đã commit
Đáp án đúng: A

Câu 40. Khi gateway Java gọi flow request-reply, replyChannel header thường được dùng để làm gì?
A. Lưu đường dẫn file mà endpoint vừa xử lý xong
B. Gán transaction manager cho mọi downstream consumer
C. Chỉ nơi gửi Message phản hồi về gateway đang chờ
D. Xác định số thread tối đa của poller đang chạy
Đáp án đúng: C

Câu 41. Khi gateway đang đợi phản hồi nhưng flow không gửi reply, tùy chọn nào liên quan?
A. maxMessagesPerPoll giới hạn thời gian gateway chờ reply
B. fixedDelay quyết định timeout của một gateway interface
C. poller.receiveTimeout quyết định reply của mọi gateway
D. replyTimeout giới hạn thời gian gateway chờ kết quả
Đáp án đúng: D

Câu 42. Khi splitter và aggregator dùng correlationId, giá trị này thường giúp gì?
A. Nhận biết fragment thuộc cùng nhóm message gốc
B. Chọn MessageChannel executor có nhiều worker nhất
C. Xác định replyTimeout cho mỗi gateway đang đợi
D. Thay thế sequenceSize trong mọi release strategy
Đáp án đúng: A

Câu 43. MessageHistory header trong Spring Integration có giá trị thực tế nào?
A. Lưu bytecode của các bean được tạo trong ApplicationContext
B. Tự retry lời gọi handler theo danh sách component
C. Bảo đảm message được persist để phục hồi sau restart
D. Giúp truy vết các component flow Message đã đi qua
Đáp án đúng: D

Câu 44. Khi cần hình dung các node và cạnh đang có trong runtime, thành phần nào phù hợp?
A. RequestHandlerRetryAdvice tạo sơ đồ từ RetryContext
B. MessageGroupStore tự dựng bản đồ Java package
C. IntegrationGraphServer cung cấp mô hình đồ thị tích hợp
D. QueueChannel tự liệt kê mọi dependency của bean
Đáp án đúng: C

Câu 45. Khi muốn quan sát số message và thời gian xử lý qua endpoint, hướng nào phù hợp?
A. Dùng MessageHeaders.ID để suy ra trực tiếp latency
B. Đặt tất cả channel thành QueueChannel không giới hạn
C. Kích hoạt metrics cho endpoint hỗ trợ IntegrationManagement
D. Giữ mọi Message trong heap để đếm khi shutdown
Đáp án đúng: C

Câu 46. Nếu QueueChannel tăng độ sâu nhanh hơn tốc độ consumer, biện pháp nào nên cân nhắc?
A. Tăng độ sâu queue không giới hạn để không mất thứ tự
B. Tắt errorChannel để hệ thống tự tiêu thụ nhanh hơn
C. Chuyển mọi message thành nullChannel mà không đánh giá nghiệp vụ
D. Theo dõi backlog, giới hạn capacity hay scale consumer
Đáp án đúng: D

Câu 47. Để kiểm thử flow bị lỗi hoặc retry ở runtime, phương pháp nào đáng tin cậy?
A. Chỉ xác nhận bean IntegrationFlow có trong ApplicationContext
B. Inject Message rồi xác minh output, lỗi và các lượt retry
C. Chỉ chạy compile Java và giả định retry hoạt động đúng
D. Chỉ mock handler rồi bỏ qua channel và poller trong kiểm thử
Đáp án đúng: B

Câu 48. Khi kiểm tra một endpoint triển khai SmartLifecycle còn chạy không, API nào hữu ích?
A. isRunning() trả trạng thái lifecycle hiện tại của endpoint
B. isAutoStartup() xác nhận endpoint đang chạy tức thời
C. getPhase() cho biết endpoint còn message đang đợi
D. getBeanName() xác nhận endpoint có consumer hoạt động
Đáp án đúng: A
