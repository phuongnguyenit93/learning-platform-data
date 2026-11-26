Câu 01. Luồng nhận đơn hàng cần đưa mỗi message vào đúng kênh theo giá trị `orderType`. Mẫu nào phù hợp nhất?
A. Message Filter giữ hoặc bỏ qua thông điệp theo điều kiện
B. Content-Based Router chọn kênh theo thuộc tính message
C. Message Transformer thay payload trước khi giao cho kênh
D. Recipient List Router chuyển tới nhiều kênh đã liệt kê
Đáp án đúng: B

Câu 02. Một luồng chỉ cho đơn hàng có `amount > 0` tiếp tục; đơn không hợp lệ cần bị loại. Mẫu nào phù hợp?
A. Content Enricher bổ sung field vào nội dung đơn hàng
B. Message Splitter tạo một message cho từng dòng hàng
C. Message Filter cho message hợp lệ đi tiếp, bỏ phần còn lại
D. Service Activator gọi dịch vụ nghiệp vụ nhận message
Đáp án đúng: C

Câu 03. Cần đổi payload JSON của sự kiện thành DTO nội bộ trước khi xử lý. Mẫu nào đúng mục đích?
A. Wire Tap sao chép message để đưa sang kênh quan sát
B. Content-Based Router chọn kênh theo field của payload
C. Message Aggregator gom message theo khóa tương quan
D. Message Transformer chuyển payload sang dạng dữ liệu khác
Đáp án đúng: D

Câu 04. Một message chứa danh sách 12 sản phẩm cần tách để xử lý độc lập từng sản phẩm. Chọn mẫu nào?
A. Message Filter loại message không đạt điều kiện chọn
B. Message Bridge chuyển tiếp message giữa hai channel
C. Message Splitter tách list thành message cho mỗi phần tử
D. Message Aggregator tập hợp từng message thành một nhóm
Đáp án đúng: C

Câu 05. Sau xử lý từng dòng hàng, cần gom các kết quả cùng đơn thành một response. Chọn mẫu nào?
A. Message Splitter chia dữ liệu theo từng dòng của đơn hàng
B. Message Aggregator ghép kết quả cùng khóa tương quan
C. Message Filter chỉ giữ message có kết quả được chấp nhận
D. Message Router chọn kênh xử lý theo trạng thái của đơn
Đáp án đúng: B

Câu 06. Muốn gọi luồng message thông qua method Java có request/reply mà không tự thao tác channel, dùng gì?
A. Recipient List Router gửi message qua nhiều nhánh xử lý
B. Inbound Channel Adapter chỉ phát sự kiện theo lịch polling
C. Messaging Gateway nối lời gọi method với trao đổi message
D. Wire Tap chuyển bản sao message sang kênh ghi dấu vết
Đáp án đúng: C

Câu 07. Một endpoint nhận message và gọi `invoiceService.generate()` để thực thi nghiệp vụ. Mẫu EIP nào hợp lý?
A. Message Router dùng payload xác định kênh đích
B. Message Aggregator ghép kết quả xử lý vào một nhóm
C. Message Splitter tách message thành các phần tử riêng
D. Service Activator gọi dịch vụ nghiệp vụ khi nhận message
Đáp án đúng: D

Câu 08. Cần thêm header `tenantId` cho message nhưng giữ nguyên payload. Mẫu nào phù hợp?
A. Payload Transformer chuyển nội dung sang kiểu mới
B. Message Filter chặn message không thuộc tenant
C. Header Enricher thêm header mà giữ nguyên phần payload
D. Message Splitter chia payload theo từng tenant
Đáp án đúng: C

Câu 09. Muốn quan sát message trên nhánh phụ nhưng không đổi tuyến xử lý chính, nên áp dụng mẫu nào?
A. Message Aggregator nhóm message vào đầu ra chung
B. Wire Tap gửi bản sao message sang channel giám sát
C. Message Bridge chuyển message sang channel tiếp theo
D. Content-Based Router thay channel chính theo điều kiện
Đáp án đúng: B

Câu 10. Một sự kiện cần gửi đến hai nhánh cảnh báo và lưu trữ nếu thỏa các điều kiện riêng. Mẫu nào thích hợp?
A. Message Filter loại sự kiện khi một điều kiện không thỏa
B. Message Transformer đổi payload trước khi định tuyến nhánh
C. Content-Based Router chọn một nhánh theo khóa loại sự kiện
D. Recipient List Router gửi message tới các nhánh phù hợp
Đáp án đúng: D

Câu 11. Trong Spring Integration, loại channel nào hỗ trợ publish thông điệp đến nhiều subscriber?
A. PublishSubscribeChannel phân phối tới nhiều subscriber
B. DirectChannel chọn một handler để giao đồng bộ message
C. QueueChannel giữ message cho consumer chủ động poll
D. ExecutorChannel chuyển việc giao message qua executor
Đáp án đúng: A

Câu 12. Với `DirectChannel` mặc định, handler nhận message thường chạy theo mô hình nào?
A. Handler nhận message qua TCP socket từ dispatcher
B. Handler thực thi trong thread của bên gọi `send`
C. Handler được lưu trong hàng đợi để poll sau
D. Handler chạy trên thread pool gắn sẵn vào channel
Đáp án đúng: B

Câu 13. Cần channel lưu message đợi poller hoặc consumer chủ động `receive()`. Chọn loại nào?
A. ExecutorChannel bàn giao message cho task executor
B. PublishSubscribeChannel phát message tới nhiều subscriber
C. DirectChannel gọi subscriber khi producer gửi message
D. QueueChannel lưu message để được lấy ra bởi consumer
Đáp án đúng: D

Câu 14. Khi muốn tách thread xử lý handler khỏi thread producer qua một task executor, dùng loại channel nào?
A. ExecutorChannel ủy quyền dispatch message cho TaskExecutor
B. DirectChannel gọi handler trực tiếp trên thread producer
C. QueueChannel chờ consumer gọi `receive` trên thread riêng
D. PriorityChannel lưu message cho consumer lấy theo mức ưu tiên
Đáp án đúng: A

Câu 15. Trong Spring Integration, một `Message<?>` chứa hai thành phần chính nào?
A. Controller và ViewResolver xử lý một HTTP request
B. Payload và ConnectionFactory mở kết nối đến broker
C. Payload và headers mang dữ liệu cùng metadata
D. Topic và partition xác định đường vào của Kafka
Đáp án đúng: C

Câu 16. Muốn thêm header trên message hiện có theo hướng bất biến, cách nào phù hợp?
A. Gọi `msg.setHeader(...)` sửa đối tượng message tại chỗ
B. Gọi `msg.getPayload().setHeader(...)` sửa vùng metadata
C. Dùng `MessageBuilder.fromMessage(msg).setHeader(...).build()`
D. Gọi `msg.getHeaders().put(...)` sửa trực tiếp header map
Đáp án đúng: C

Câu 17. Để tách sender khỏi logic xử lý và cho phép thay endpoint, abstraction nào đóng vai trò trung gian?
A. MessageChannel kết nối endpoint gửi và endpoint nhận
B. Service Activator khiến sender phụ thuộc lời gọi service
C. MessageGroupStore thay toàn bộ các điểm kết nối channel
D. CorrelationStrategy trực tiếp nhận và chuyển tiếp message
Đáp án đúng: A

Câu 18. Một interface gắn `@MessagingGateway` cần gửi request đến channel `orderRequests`. Thuộc tính nào cấu hình điều này?
A. `defaultRequestChannel = "orderRequests"` định tuyến request
B. `defaultRequestTimeout = "orderRequests"` chọn kênh request
C. `defaultReplyChannel = "orderRequests"` chọn kênh request
D. `errorChannel = "orderRequests"` chọn kênh request
Đáp án đúng: A

Câu 19. Một gateway chờ response cho request; header chuẩn nào chỉ định nơi gửi reply của message?
A. `correlationId` xác định channel nhận thông điệp trả lời
B. `replyChannel` xác định channel nhận thông điệp trả lời
C. `sequenceNumber` xác định channel nhận thông điệp trả lời
D. `errorChannel` xác định channel nhận thông điệp trả lời
Đáp án đúng: B

Câu 20. Cần nối hai channel và chuyển nguyên message, không cần đổi nội dung hay quyết định tuyến. Endpoint nào đúng?
A. MessageSplitter chia payload thành nhiều message con
B. MessageFilter đánh giá predicate và bỏ message sai
C. BridgeHandler chuyển message giữa channel không đổi nội dung
D. Aggregator gom nhiều message thành một payload mới
Đáp án đúng: C

Câu 21. Khi splitter được cấu hình áp dụng sequence header, thông tin nào hỗ trợ downstream aggregator?
A. Các header host, port và transaction isolation level
B. Chỉ header HTTP status và content type của message
C. Các header correlation, sequence number và sequence size
D. Chỉ tên bean, thread pool và tên message handler
Đáp án đúng: C

Câu 22. Ở các kết quả sau split, header `correlationId` thường được dùng để làm gì?
A. Công bố tổng số phần tử cần đợi của một nhóm message
B. Xác định channel dành riêng cho exception khi xử lý
C. Xác định thứ tự phần tử trong nhóm sau khi tách
D. Định danh các message thuộc cùng một nhóm correlation
Đáp án đúng: D

Câu 23. Trong các phần message do splitter sinh ra, `sequenceNumber` biểu diễn thông tin gì?
A. Vị trí của message trong chuỗi sau thao tác tách
B. Số phần tử tổng cộng của nhóm cần aggregation
C. Khóa nghiệp vụ để chia message vào từng group
D. Số lần endpoint thử lại khi xử lý bị thất bại
Đáp án đúng: A

Câu 24. Khi `sequenceSize` có giá trị 6 trên message sau split, nó biểu diễn gì?
A. Số nhánh channel được Message Router kích hoạt
B. Tổng số phần tử dự kiến của chuỗi message liên quan
C. Vị trí hiện tại của phần tử trong chuỗi message đó
D. Số lượng retries tối đa của một message handler
Đáp án đúng: B

Câu 25. Cần gom các sự kiện theo `batchId` trong payload thay vì header mặc định. Phần mở rộng nào phù hợp?
A. MessageGroupProcessor chỉ nhận message sau khi release
B. CorrelationStrategy tính khóa group từ `batchId`
C. ErrorMessageStrategy tạo khóa nhóm từ exception message
D. ReleaseStrategy tính thời điểm gom nhóm từ `batchId`
Đáp án đúng: B

Câu 26. Trong Aggregator, thành phần nào quyết định khi group đủ điều kiện phát kết quả?
A. CorrelationStrategy xác định lúc message được gửi vào channel
B. MessageGroupProcessor chọn luồng retry nếu group chưa đủ
C. ChannelResolver xác định thời gian nhóm chờ message
D. ReleaseStrategy đánh giá lúc nhóm message được giải phóng
Đáp án đúng: D

Câu 27. Khi Aggregator cần tạo payload đầu ra từ các phần tử đã tập hợp, extension nào thực hiện việc đó?
A. ErrorMessageStrategy chọn các trường làm output body
B. CorrelationStrategy phân phối từng message đến consumer
C. ReleaseStrategy chuyển đổi payload của từng message
D. MessageGroupProcessor tổng hợp các message trong group
Đáp án đúng: D

Câu 28. Một aggregator cần giữ nhóm đang chờ qua lần khởi động lại ứng dụng. Cấu hình nào đáp ứng?
A. Dùng MessageGroupStore bền vững lưu nhóm trên JDBC
B. Dùng DirectChannel làm nơi giữ message group lâu dài
C. Dùng MessageBuilder cache toàn bộ các group vào heap
D. Dùng SimpleMessageStore chỉ trong bộ nhớ của một JVM
Đáp án đúng: A

Câu 29. Group có thể chờ thiếu message mãi; muốn đặt thời gian chờ và quyết định có trả kết quả một phần. Chọn gì?
A. Cấu hình `requestTimeout` và `replyTimeout` cho gateway
B. Cấu hình `maxAttempts` và `backOffPolicy` cho advice
C. Cấu hình `receiveTimeout` và `sendTimeout` cho channel
D. Cấu hình `groupTimeout` và `sendPartialResultOnExpiry`
Đáp án đúng: D

Câu 30. Các phần tử tới sai thứ tự nhưng cần giữ từng message và phát lại theo số sequence, mẫu nào phù hợp?
A. Recipient List Router gửi bản sao tới mỗi consumer khác nhau
B. Resequencer sắp message theo sequence rồi phát từng phần
C. Aggregator gom các phần tử thành một message tổng hợp
D. Transformer sửa payload để giảm kích thước từng phần tử
Đáp án đúng: B

Câu 31. Trong Spring Integration, lỗi của handler chạy bất đồng bộ thường được chuyển tới channel nào khi được cấu hình?
A. `errorChannel` nhận ErrorMessage từ handler bất đồng bộ
B. `nullChannel` thu thập ErrorMessage để client nhận lại
C. `inputChannel` tự lưu ErrorMessage vào message group
D. `replyChannel` nhận ErrorMessage khi đường xử lý báo lỗi
Đáp án đúng: A

Câu 32. Đối với một `ErrorMessage`, payload chính thường mang loại dữ liệu nào?
A. Một Throwable mô tả exception trong xử lý message
B. Một String chứa tên input channel đã nhận message
C. Một Collection gồm các reply đã được trả về
D. Một MessageGroup lưu các phần tử trước aggregator
Đáp án đúng: A

Câu 33. Khi handler gắn vào DirectChannel xử lý đồng bộ và ném exception, điều gì thường xảy ra với `send()`?
A. Exception được retry vô hạn bởi dispatcher channel
B. Exception được lưu vào QueueChannel chờ poller đọc
C. Exception lan về caller nếu không được advice xử lý
D. Exception tự biến thành một reply message thành công
Đáp án đúng: C

Câu 34. Muốn handler được retry theo chính sách số lần và backoff, advice nào phù hợp?
A. ExpressionEvaluatingRequestHandlerAdvice thực hiện retry
B. RequestHandlerRetryAdvice bao handler bằng chính sách retry
C. WireTapAdvice lặp lời gọi handler theo số attempts
D. RequestHandlerCircuitBreakerAdvice định nghĩa chính sách retry
Đáp án đúng: B

Câu 35. Sau khi retry vẫn thất bại, muốn phát lỗi sang channel riêng qua Spring Retry recoverer, dùng gì?
A. DefaultAggregatingMessageGroupProcessor chuyển lỗi sang channel
B. MessageFilter tự retry và chuyển lỗi sang kênh mặc định
C. ServiceActivatingHandler tự phát recovery event khi lỗi
D. ErrorMessageSendingRecoverer đưa lỗi tới channel cấu hình
Đáp án đúng: D

Câu 36. Khi nhận lại cùng một event do broker giao lặp, interceptor nào hỗ trợ kiểm soát xử lý trùng?
A. MessageSplitter tách event thành các phần xử lý nhỏ
B. IdempotentReceiverInterceptor nhận diện message trùng khóa
C. WireTap chuyển bản sao event vào kênh theo dõi message
D. HeaderEnricher thêm thông tin chẩn đoán vào event
Đáp án đúng: B

Câu 37. Cần lưu khóa event đã xử lý giữa các instance để hạn chế xử lý trùng; kho nào phù hợp?
A. MetadataStore dùng chung lưu khóa idempotency đã xử lý
B. DirectChannel là kho persistent key giữa các instance
C. CorrelationStrategy ghi trạng thái vào exception headers
D. MessageHistory được chia sẻ như cơ sở dữ liệu khóa event
Đáp án đúng: A

Câu 38. Đầu ra của một nhánh cần cố ý loại bỏ mà không đưa vào handler khác; channel đặc biệt nào dùng được?
A. `errorChannel` nhận và bỏ các message gửi đến nó
B. `replyChannel` nhận và bỏ các message gửi đến nó
C. `nullChannel` nhận và bỏ các message gửi đến nó
D. `inputChannel` nhận và bỏ các message gửi đến nó
Đáp án đúng: C

Câu 39. Muốn kiểm thử integration flow và thay endpoint thật bằng mock dưới TestContext, hỗ trợ nào phù hợp?
A. `@SpringIntegrationTest` cùng `MockIntegrationContext`
B. `@MessagingGateway` cùng `ApplicationEventPublisher`
C. `@SpringJUnitConfig` cùng `MessageGroupStore`
D. `@EnableIntegration` cùng `BeanFactoryPostProcessor`
Đáp án đúng: A

Câu 40. Để truy vết các component endpoint đã đi qua, thông tin nào hữu ích khi bật history?
A. ReleaseStrategy ghi HTTP method và response status
B. ErrorMessageStrategy theo dõi các span OpenTelemetry
C. MessageGroupStore chỉ ghi trạng thái thread pool handler
D. MessageHistory lưu dấu các component message đi qua
Đáp án đúng: D
