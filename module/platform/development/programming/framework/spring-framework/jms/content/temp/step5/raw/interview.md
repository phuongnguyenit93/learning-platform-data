Bạn giải thích Spring JMS cung cấp những abstraction nào để ứng dụng Spring làm việc với Jakarta Messaging?
Bạn phân biệt trách nhiệm của Spring JMS với trách nhiệm của JMS broker khi gửi và nhận thông điệp như thế nào?
Bạn mô tả vai trò của Jakarta Messaging API và JMS provider trong một ứng dụng sử dụng Spring Framework ra sao?
Bạn sẽ lựa chọn gửi bất đồng bộ qua JMS thay vì gọi HTTP trực tiếp giữa hai service trong tình huống nào?
Bạn phân biệt queue và topic theo cách nhiều Spring consumers nhận một thông điệp như thế nào?
Bạn sẽ xác định một tác vụ phù hợp với point-to-point queue hay publish-subscribe topic dựa trên yêu cầu nào?
Bạn phân tích tác động của việc nhiều listener cùng theo dõi một queue đối với số lần xử lý thông điệp như thế nào?
Bạn giải thích vì sao hai subscriber độc lập của một topic có thể nhận những bản sao thông điệp khác nhau ra sao?
Bạn sẽ thiết kế tên destination ổn định giữa các phiên bản producer và consumer Spring như thế nào?
Bạn phân biệt destination name dạng chuỗi và đối tượng jakarta.jms.Destination khi cấu hình Spring JMS ra sao?
Bạn đánh giá khi nào cần tách message contract khỏi entity nội bộ của service gửi thông điệp như thế nào?
Bạn sẽ thiết kế giao tiếp bất đồng bộ bảo đảm producer không phụ thuộc vào việc consumer đang chạy ra sao?
Bạn phân tích rủi ro giả định thông điệp JMS luôn chỉ được xử lý đúng một lần như thế nào?
Bạn phân biệt delivery guarantee của broker với idempotency của nghiệp vụ khi sử dụng Spring JMS ra sao?
Bạn sẽ xác định đâu là dữ liệu bắt buộc trong message body và đâu là metadata nên đưa vào header ra sao?
Bạn giải thích khác biệt giữa message producer, consumer và listener container trong một ứng dụng Spring như thế nào?
Bạn lựa chọn đồng bộ nhận thông điệp bằng JmsTemplate hay xử lý qua listener container theo tiêu chí nào?
Bạn phân tích ảnh hưởng của các cuộc gọi nhận blocking đối với thread ứng dụng khi dùng Spring JMS như thế nào?
Bạn đánh giá giới hạn khi muốn dùng mô hình reactive trong khi API JMS và JmsTemplate chủ yếu vận hành theo cách blocking ra sao?
Bạn sẽ thiết kế ranh giới giữa domain service và adapter Spring JMS để dễ thay broker hoặc cơ chế tích hợp như thế nào?
Bạn giải thích vì sao Spring JMS không tự quyết định cách broker lưu bền vững và chuyển phát thông điệp ra sao?
Bạn mô tả một đường đi end-to-end từ service method gọi JmsTemplate tới @JmsListener trong service nhận như thế nào?
Bạn phân biệt thành công khi JmsTemplate gửi xong với việc consumer đã xử lý nghiệp vụ thành công ra sao?
Bạn sẽ xác định những trạng thái cần theo dõi để biết một thông điệp đã được gửi nhưng chưa được xử lý như thế nào?
Bạn phân tích vì sao queue depth không đủ để đánh giá tính đúng đắn của toàn bộ luồng xử lý ra sao?
Bạn sẽ quyết định khi nào dùng JMS thay cho cơ chế application event chạy cùng JVM ra sao?
Bạn đánh giá tác động của network partition giữa ứng dụng và JMS broker tới lời gọi gửi nhận như thế nào?
Bạn giải thích vai trò của ConnectionFactory trong việc tạo kết nối Jakarta Messaging cho Spring JMS?
Bạn phân biệt một JMS ConnectionFactory do provider cung cấp với bean ConnectionFactory được cấu hình trong Spring như thế nào?
Bạn sẽ cấu hình ConnectionFactory cho môi trường local, staging và production mà không hardcode credential ra sao?
Bạn mô tả cách cấu hình broker URL và thông tin xác thực để JmsTemplate và listener cùng sử dụng đúng provider như thế nào?
Bạn phân biệt SingleConnectionFactory với một ConnectionFactory native của JMS provider về cách tái sử dụng kết nối ra sao?
Bạn đánh giá khi nào CachingConnectionFactory giúp giảm chi phí tạo JMS Session và MessageProducer như thế nào?
Bạn mô tả vai trò của sessionCacheSize trong CachingConnectionFactory và rủi ro đặt giá trị không phù hợp như thế nào?
Bạn phân tích trường hợp một ứng dụng có nhiều concurrent listeners nhưng session cache quá nhỏ gây tăng chi phí tạo tài nguyên ra sao?
Bạn sẽ phân biệt session cache của Spring với connection pooling do provider triển khai như thế nào?
Bạn giải thích vì sao dùng CachingConnectionFactory cùng một pool của provider cần xem xét tương tác cache và lifecycle ra sao?
Bạn sẽ kiểm tra connection có tự phục hồi sau khi broker bị restart khi dùng ConnectionFactory đã cấu hình như thế nào?
Bạn phân biệt xử lý exception khi tạo JMS connection với lỗi trong quá trình listener xử lý thông điệp ra sao?
Bạn sẽ quản lý tài nguyên và đóng ConnectionFactory khi ApplicationContext shutdown như thế nào?
Bạn xác định cách giới hạn quyền truy cập của tài khoản JMS để chỉ gửi hoặc nhận trên destinations cần thiết ra sao?
Bạn phân tích rủi ro dùng một ConnectionFactory có quyền toàn broker cho mọi module Spring như thế nào?
Bạn sẽ lựa chọn cấu hình SSL/TLS cho kết nối JMS dựa trên cơ chế bảo mật được provider hỗ trợ ra sao?
Bạn đánh giá cách xoay vòng broker credential mà hạn chế downtime khi có nhiều listener containers ra sao?
Bạn xác định khi nào cần cấu hình nhiều ConnectionFactory beans để kết nối các broker khác nhau như thế nào?
Bạn sẽ sử dụng @Qualifier để tránh JmsTemplate nhận nhầm ConnectionFactory trong hệ thống có nhiều brokers ra sao?
Bạn phân tích rủi ro producer và consumer trỏ đến hai brokers khác nhau dù cùng dùng destination name như thế nào?
Bạn sẽ kiểm tra Session được tạo ở chế độ transacted hay acknowledgment mode nào dựa trên cấu hình container ra sao?
Bạn giải thích vai trò của DestinationResolver khi Spring chuyển tên destination thành đối tượng JMS Destination như thế nào?
Bạn phân biệt DynamicDestinationResolver với JndiDestinationResolver trong các môi trường broker khác nhau ra sao?
Bạn sẽ lựa chọn JNDI destination lookup hay tạo destination động theo tên cho một hệ thống có quy định quản trị chặt ra sao?
Bạn phân tích lỗi destination name hợp lệ trong code nhưng không tồn tại trên broker khi auto-create bị vô hiệu như thế nào?
Bạn sẽ thiết kế cấu hình pubSubDomain riêng cho thao tác gửi topic thay vì queue như thế nào?
Bạn phân biệt JMS 1.1-style Connection/Session API với các tiện ích JMSContext trong Jakarta Messaging theo yêu cầu tích hợp Spring ra sao?
Bạn sẽ xác định các phiên bản Spring Framework và provider hỗ trợ package jakarta.jms thay cho javax.jms như thế nào?
Bạn đánh giá rủi ro một thư viện JMS cũ dùng javax.jms được đưa vào ứng dụng Spring phiên bản sử dụng jakarta.jms ra sao?
Bạn sẽ xây dựng smoke test kết nối broker để phân biệt lỗi cấu hình với lỗi định tuyến destination như thế nào?
Bạn giải thích JmsTemplate đơn giản hóa thao tác gửi và nhận JMS so với việc tự quản lý Connection, Session và MessageProducer như thế nào?
Bạn phân biệt JmsTemplate với JmsMessagingTemplate theo mức abstraction và kiểu Spring Message được hỗ trợ ra sao?
Bạn sẽ inject JmsTemplate vào service và giữ tên queue cấu hình ngoài mã nghiệp vụ theo cách nào?
Bạn mô tả cách convertAndSend sử dụng MessageConverter để chuyển một object thành JMS Message như thế nào?
Bạn phân biệt send với convertAndSend trong trường hợp cần tạo message và header tùy chỉnh ra sao?
Bạn sẽ dùng MessageCreator khi cần đặt JMS header hoặc chọn loại message do provider hỗ trợ ra sao?
Bạn giải thích MessagePostProcessor trong JmsTemplate có thể thay đổi message sau conversion và trước khi gửi như thế nào?
Bạn sẽ thiết kế một producer thêm correlation ID và business event type mà không trộn chúng vào payload ra sao?
Bạn phân tích rủi ro MessagePostProcessor sửa nội dung nhạy cảm hoặc loại message ngoài mong muốn như thế nào?
Bạn sẽ lựa chọn setDefaultDestinationName hoặc truyền destination cụ thể vào từng lệnh gửi theo tiêu chí nào?
Bạn phân biệt một JmsTemplate gửi tới queue với JmsTemplate được cấu hình pubSubDomain cho topic ra sao?
Bạn sẽ xác định cách tránh dùng cùng bean JmsTemplate cho các destinations có chính sách delivery khác nhau như thế nào?
Bạn mô tả tác động của deliveryPersistent tới khả năng thông điệp sống sót sau broker restart như thế nào?
Bạn phân biệt deliveryMode PERSISTENT với NON_PERSISTENT và trách nhiệm của broker trong bảo đảm độ bền ra sao?
Bạn sẽ cấu hình message priority có kiểm soát mà không giả định broker luôn xử lý theo thứ tự ưu tiên tuyệt đối như thế nào?
Bạn phân tích rủi ro lạm dụng priority khiến các thông điệp ít ưu tiên bị tồn đọng kéo dài ra sao?
Bạn sẽ chọn time-to-live cho thông điệp công việc không còn giá trị sau thời hạn nhất định như thế nào?
Bạn giải thích vì sao message TTL khác với giới hạn thời gian xử lý một message sau khi listener bắt đầu ra sao?
Bạn sẽ cấu hình explicitQosEnabled khi cần các lựa chọn QoS của JmsTemplate thực sự có hiệu lực như thế nào?
Bạn phân tích ảnh hưởng của delivery delay nếu provider hỗ trợ tới thời điểm message được phát cho consumer ra sao?
Bạn sẽ xử lý exception JMS khi gửi để caller biết yêu cầu có thể chưa được broker nhận như thế nào?
Bạn phân biệt JmsException do Spring chuyển đổi với JMSException gốc của JMS provider khi chẩn đoán lỗi gửi thông điệp như thế nào?
Bạn sẽ thiết kế idempotency cho producer khi gửi lại sau timeout nhưng trạng thái chấp nhận từ broker chưa rõ ra sao?
Bạn phân tích vì sao gửi message thành công không tự đồng nghĩa database transaction nghiệp vụ đã commit như thế nào?
Bạn sẽ lựa chọn transactional outbox hoặc JTA/XA khi cần phối hợp ghi database và gửi JMS theo yêu cầu nhất quán nào?
Bạn sẽ quản lý payload size của thông điệp để tránh sử dụng queue như kho lưu tệp lớn ra sao?
Bạn phân tích chi phí serialize object lớn mỗi lần convertAndSend trong một endpoint lưu lượng cao như thế nào?
Bạn sẽ thiết kế batch producer tránh giữ toàn bộ danh sách message payload trong heap như thế nào?
Bạn phân biệt lời gọi JmsTemplate.receive với receiveSelected khi cần nhận message có selector như thế nào?
Bạn sẽ xác định rủi ro receive không có timeout khiến một thread chờ vô thời hạn như thế nào?
Bạn phân tích tác động của receiveTimeout đặt quá ngắn khiến synchronous consumer thường xuyên trả về null như thế nào?
Bạn sẽ sử dụng receiveAndConvert khi cần nhận object đã được MessageConverter xử lý như thế nào?
Bạn phân biệt synchronous receive từ queue và @JmsListener khi xét chi phí thread và khả năng mở rộng như thế nào?
Bạn sẽ lựa chọn QueueBrowser để kiểm tra thông điệp tồn đọng mà không tiêu thụ chúng trong điều kiện nào?
Bạn phân tích vì sao QueueBrowser không nên được xem là snapshot transactionally consistent của toàn queue như thế nào?
Bạn sẽ thiết kế request-reply bằng JMSReplyTo và JMSCorrelationID để liên kết phản hồi với yêu cầu như thế nào?
Bạn phân biệt reply destination cố định với temporary destination trong mô hình request-reply như thế nào?
Bạn sẽ sử dụng JmsTemplate.sendAndReceive trong kịch bản nào và kiểm soát độ trễ chờ phản hồi ra sao?
Bạn phân tích vì sao request-reply qua JMS có thể gây blocking và timeout giống lời gọi đồng bộ như thế nào?
Bạn sẽ xác định chiến lược timeout và cleanup cho reply consumer nếu service phía nhận không phản hồi ra sao?
Bạn giải thích các loại TextMessage, BytesMessage và MapMessage phù hợp với những kiểu payload nào như thế nào?
Bạn phân biệt ObjectMessage với định dạng JSON khi xét khả năng tương thích, serialization và an toàn deserialization ra sao?
Bạn sẽ lựa chọn MessageConverter cho đối tượng Java có schema tiến hóa theo phiên bản như thế nào?
Bạn mô tả vai trò của SimpleMessageConverter trong các trường hợp payload thông dụng như thế nào?
Bạn phân biệt SimpleMessageConverter với MappingJackson2MessageConverter khi gửi object nghiệp vụ ra sao?
Bạn sẽ cấu hình MappingJackson2MessageConverter để thống nhất JSON payload giữa producer và consumer như thế nào?
Bạn giải thích vì sao type identifier property cần được kiểm soát khi conversion tới nhiều loại Java class như thế nào?
Bạn sẽ quản lý type mapping cho payload JSON mà không để producer phụ thuộc vào tên class Java của consumer như thế nào?
Bạn phân tích rủi ro triển khai phiên bản consumer mới không đọc được JSON do producer cũ gửi như thế nào?
Bạn sẽ thiết kế contract phiên bản message để trường mới được thêm vào mà không làm hỏng consumer cũ ra sao?
Bạn phân biệt schema validation tại listener với lỗi trong quá trình deserialization của MessageConverter như thế nào?
Bạn sẽ quyết định khi nào từ chối message không hợp lệ và khi nào đưa nó vào dead-letter queue để điều tra ra sao?
Bạn giải thích sự khác nhau giữa JMS standard headers và custom message properties như thế nào?
Bạn sẽ dùng JMSCorrelationID để đối chiếu một message với trace hoặc giao dịch nghiệp vụ như thế nào?
Bạn phân biệt JMSMessageID do provider gán với business event ID do ứng dụng sinh như thế nào?
Bạn sẽ sử dụng JMSReplyTo cho request-reply mà không coi nó là địa chỉ đáng tin cậy mặc định ra sao?
Bạn mô tả ý nghĩa của JMSType và khi nào nên dùng custom eventType property thay vì phụ thuộc vào nó như thế nào?
Bạn phân biệt JMSPriority với property priority nghiệp vụ được xác thực trong payload như thế nào?
Bạn phân tích tác động của JMSExpiration tới khả năng message không còn được consumer nhận sau TTL như thế nào?
Bạn sẽ sử dụng JMSRedelivered như một tín hiệu điều tra message đã từng được phát cho consumer như thế nào?
Bạn phân biệt JMSXDeliveryCount với một attempt counter do ứng dụng tự lưu theo tính khả dụng của provider ra sao?
Bạn sẽ thiết kế custom properties để consumer lọc sự kiện theo tenant hoặc loại nghiệp vụ bằng message selector như thế nào?
Bạn giải thích cú pháp selector của JMS có thể lọc message properties mà không cần deserialize toàn bộ payload như thế nào?
Bạn sẽ lựa chọn message selector trong @JmsListener cho một nhóm sự kiện cần xử lý như thế nào?
Bạn phân tích rủi ro selector đánh sai kiểu dữ liệu của property khiến message luôn bị bỏ qua ra sao?
Bạn sẽ bảo đảm selector chỉ được dùng để định tuyến chứ không thay thế phân quyền nghiệp vụ như thế nào?
Bạn phân biệt lọc message tại broker bằng selector với lọc sau khi @JmsListener nhận payload như thế nào?
Bạn sẽ đánh giá chi phí vận hành khi có rất nhiều selectors gắn với cùng một queue như thế nào?
Bạn phân tích nguy cơ thay đổi selector trong lần deploy mới khiến một số message cũ không còn consumer phù hợp như thế nào?
Bạn sẽ kiểm tra header mapper có chuyển đúng dữ liệu giữa Spring MessageHeaders và JMS properties ra sao?
Bạn đánh giá rủi ro đưa user input làm custom header mà không kiểm tra kiểu, độ dài và khả năng truy cập như thế nào?
Bạn sẽ quyết định thời điểm log header metadata mà không ghi nội dung nhạy cảm của message như thế nào?
Bạn giải thích @EnableJms kích hoạt cơ chế phát hiện các phương thức @JmsListener trong Spring như thế nào?
Bạn phân biệt khai báo @JmsListener trên Spring bean với một object được tạo bằng new ngoài ApplicationContext ra sao?
Bạn sẽ dùng @JmsListener(destination=...) để gắn một method xử lý vào queue theo cấu hình như thế nào?
Bạn mô tả cách Spring tạo listener endpoint và listener container từ annotation @JmsListener ra sao?
Bạn phân biệt id của @JmsListener với destination name khi quản trị nhiều endpoints như thế nào?
Bạn sẽ lựa chọn containerFactory trên @JmsListener để áp dụng các chính sách concurrency khác nhau như thế nào?
Bạn giải thích JmsListenerContainerFactory quyết định cách listener container được tạo cho một endpoint như thế nào?
Bạn phân biệt DefaultJmsListenerContainerFactory với DefaultMessageListenerContainer khi cấu hình và vận hành ra sao?
Bạn sẽ đặt tên bean jmsListenerContainerFactory để được dùng làm factory mặc định trong trường hợp nào?
Bạn mô tả cách DefaultJmsListenerContainerFactory nhận ConnectionFactory, message converter và error handler ra sao?
Bạn sẽ cấu hình một factory cho queue và một factory cho topic mà không làm nhầm pubSubDomain như thế nào?
Bạn phân tích vì sao không nên dùng chung cấu hình concurrency cho listener xử lý I/O ngắn và listener xử lý tác vụ dài như thế nào?
Bạn sẽ dùng JmsListenerEndpointRegistry để tra cứu, start hoặc stop các listener containers có id cụ thể ra sao?
Bạn phân biệt dừng một listener container với tắt toàn bộ ApplicationContext trong kế hoạch vận hành ra sao?
Bạn sẽ thiết kế pause hoặc resume consumer khi downstream database bảo trì mà không làm mất message ra sao?
Bạn giải thích vai trò của JmsListenerConfigurer khi cần tùy biến đăng ký các listener endpoints như thế nào?
Bạn sẽ lựa chọn đăng ký SimpleJmsListenerEndpoint programmatically thay vì @JmsListener trong tình huống nào?
Bạn phân tích tác động của việc đăng ký endpoint động khi application đã bắt đầu hoạt động như thế nào?
Bạn mô tả cách Spring chọn argument resolver cho method @JmsListener có tham số payload hoặc header ra sao?
Bạn sẽ viết @JmsListener nhận một DTO đã convert mà không đưa logic parse JSON vào service nghiệp vụ như thế nào?
Bạn phân biệt @Payload và @Header trên tham số method khi binding từ JMS message như thế nào?
Bạn sẽ dùng @Headers để truy cập tập message headers khi cần kiểm tra correlation metadata ra sao?
Bạn phân tích rủi ro dùng tham số jakarta.jms.Message thay vì DTO khi listener ngày càng phụ thuộc provider như thế nào?
Bạn sẽ xác định khi nào listener method cần tham số jakarta.jms.Session để phản hồi hoặc kiểm soát tài nguyên ra sao?
Bạn giải thích MessageConverter được áp dụng ở đâu trước khi listener method nhận payload như thế nào?
Bạn sẽ xử lý lỗi method argument conversion khi payload không khớp DTO mà chưa vào business logic như thế nào?
Bạn phân biệt lỗi validation annotation trên DTO với lỗi logic bên trong @JmsListener như thế nào?
Bạn sẽ thiết kế @JmsListener method ngắn gọn chuyển việc xử lý sang một domain service có thể unit test độc lập ra sao?
Bạn phân tích rủi ro @JmsListener trả về giá trị nhưng không cấu hình reply destination phù hợp như thế nào?
Bạn sẽ dùng @SendTo để chỉ định destination phản hồi cho một listener hỗ trợ request-reply ra sao?
Bạn phân biệt @SendTo tĩnh với cách dùng JMSReplyTo từ request để định tuyến response như thế nào?
Bạn sẽ kiểm tra correlation headers được giữ hoặc tạo phù hợp khi listener tạo response message như thế nào?
Bạn xác định cách xử lý exception khi listener cố gửi reply nhưng reply destination đã hết hạn ra sao?
Bạn mô tả cách @JmsListener(selector=...) kết hợp message selector và consumer phía broker như thế nào?
Bạn sẽ lựa chọn một @JmsListener cho nhiều destinations hay nhiều method riêng tùy ranh giới nghiệp vụ như thế nào?
Bạn phân tích nguy cơ một listener method có nhiều trách nhiệm khiến việc retry và xử lý lỗi không nhất quán ra sao?
Bạn sẽ kiểm tra một @JmsListener không được khởi tạo do thiếu @EnableJms hoặc component scan như thế nào?
Bạn đánh giá khi nào cần dùng endpoint id trong log và monitoring thay vì chỉ dựa trên tên queue ra sao?
Bạn giải thích listener container quản lý JMS Session và MessageConsumer như thế nào trong một ứng dụng Spring?
Bạn phân biệt DefaultMessageListenerContainer và SimpleMessageListenerContainer về chiến lược nhận message và khả năng cấu hình như thế nào?
Bạn sẽ lựa chọn DefaultMessageListenerContainer khi cần điều chỉnh concurrency và phục hồi kết nối theo tiêu chí nào?
Bạn mô tả vai trò của concurrentConsumers và maxConcurrentConsumers khi scale listener trong DefaultMessageListenerContainer ra sao?
Bạn sẽ phân tích giá trị cấu hình concurrency dạng khoảng trên @JmsListener theo số consumer đang hoạt động như thế nào?
Bạn phân biệt tăng số consumer với tăng số thread xử lý trên từng consumer về khả năng song song như thế nào?
Bạn sẽ xác định concurrency tối đa cho một queue theo giới hạn database connection pool và CPU như thế nào?
Bạn phân tích rủi ro tăng concurrency làm mất thứ tự xử lý kỳ vọng của các message thuộc cùng một khóa nghiệp vụ như thế nào?
Bạn sẽ thiết kế xử lý theo khóa nghiệp vụ khi cần tuần tự hóa các message liên quan thay vì phụ thuộc vào concurrency bằng một ra sao?
Bạn đánh giá ảnh hưởng của prefetch hoặc consumer credit do JMS provider cung cấp đến phân phối tải như thế nào?
Bạn sẽ xác định cách tránh một consumer prefetch quá nhiều message rồi bị chậm khiến queue không cân bằng ra sao?
Bạn phân biệt polling receive trong listener container với một synchronous JmsTemplate.receive do service chủ động gọi như thế nào?
Bạn sẽ thiết kế cấu hình receiveTimeout của listener container để cân bằng chi phí polling và phản hồi khi shutdown ra sao?
Bạn phân tích ảnh hưởng của cacheLevel trong DefaultMessageListenerContainer đối với Session và MessageConsumer như thế nào?
Bạn sẽ điều tra vì sao listener container không thể tạo hoặc tái tạo consumers sau khi broker mất kết nối ra sao?
Bạn mô tả cách DefaultMessageListenerContainer hỗ trợ recovery khi broker tạm thời không sẵn sàng như thế nào?
Bạn sẽ cấu hình recoveryInterval hoặc BackOff để giới hạn tốc độ kết nối lại tới broker ra sao?
Bạn phân tích nguy cơ nhiều service instances cùng reconnect gây tải tăng đột biến lên broker sau outage như thế nào?
Bạn sẽ thiết kế cơ chế giảm tải listener khi downstream trả lỗi quá tải thay vì retry tức thì mọi message như thế nào?
Bạn phân biệt error handler của listener container với cơ chế xử lý redelivery tại broker như thế nào?
Bạn sẽ dùng ErrorHandler của Spring container để ghi nhận lỗi listener mà không nuốt lỗi làm sai cơ chế acknowledgment ra sao?
Bạn phân tích tác động của việc bắt mọi exception trong @JmsListener và không ném lại đối với khả năng redelivery như thế nào?
Bạn sẽ phân biệt exception do conversion ở listener adapter và exception do business service khi lập metric lỗi ra sao?
Bạn sẽ xác định cách listener container giải phóng Session và Consumer khi context dừng như thế nào?
Bạn sẽ thiết kế graceful shutdown để ngừng nhận message mới và hoàn tất message đang xử lý ra sao?
Bạn phân tích rủi ro quá trình shutdown vượt timeout rồi tiến trình bị kill trước khi transaction hoàn tất ra sao?
Bạn sẽ kiểm tra listener container vẫn còn chạy sau khi business service bean bị hủy do thứ tự lifecycle như thế nào?
Bạn đánh giá khi nào một listener cần độc lập ConnectionFactory hoặc container factory để tránh ảnh hưởng các consumer khác ra sao?
Bạn giải thích queue với nhiều competing consumers khác topic với nhiều subscriptions khi áp dụng @JmsListener như thế nào?
Bạn phân biệt non-durable topic subscriber và durable subscriber về khả năng nhận thông điệp gửi lúc consumer offline ra sao?
Bạn sẽ xác định khi nào cần durable subscription cho một domain event không được bỏ sót như thế nào?
Bạn mô tả vai trò của clientId và subscription name đối với durable topic subscription theo provider ra sao?
Bạn sẽ cấu hình subscriptionDurable cho một topic listener và kiểm tra danh tính subscription ổn định như thế nào?
Bạn phân tích rủi ro các replica dùng chung hoặc thay đổi clientId khi tạo durable subscriptions không hỗ trợ shared subscription ra sao?
Bạn phân biệt durable subscription với shared durable subscription khi chạy nhiều consumer instances như thế nào?
Bạn sẽ lựa chọn subscriptionShared theo khả năng JMS provider và nhu cầu xử lý đồng thời ra sao?
Bạn giải thích vì sao mỗi độc lập business subscriber cần một subscription identity thay vì cùng nhận từ queue chung ra sao?
Bạn sẽ thiết kế fan-out một sự kiện tới nhiều domain services mà mỗi service vẫn lưu tiến độ riêng như thế nào?
Bạn phân tích hậu quả khi consumer topic được khởi tạo sau khi producer gửi và subscription không durable ra sao?
Bạn sẽ chọn topic cho event broadcast và queue cho xử lý công việc theo các yêu cầu vận hành nào?
Bạn đánh giá khi nào message selector của durable subscription cần được ổn định qua các lần deploy như thế nào?
Bạn sẽ thiết kế versioning topic events để subscriber mới và cũ cùng đọc được trong giai đoạn rolling deployment ra sao?
Bạn phân tích rủi ro xóa một durable subscription khi còn backlog chưa được xử lý như thế nào?
Bạn xác định các thông tin cần lưu trong runbook khi phải thay đổi subscription name hoặc clientId ra sao?
Bạn sẽ kiểm tra đúng số consumers của queue và subscriptions của topic từ metrics broker ra sao?
Bạn phân biệt transaction acknowledgment với AUTO_ACKNOWLEDGE trong JMS listener container như thế nào?
Bạn giải thích ý nghĩa của CLIENT_ACKNOWLEDGE và rủi ro xác nhận bao gồm nhiều message trong cùng Session ra sao?
Bạn sẽ phân tích khi nào DUPS_OK_ACKNOWLEDGE chấp nhận được và ảnh hưởng tới xử lý trùng như thế nào?
Bạn mô tả sessionTransacted=true của Spring JMS container thay đổi cách commit và rollback message processing như thế nào?
Bạn phân biệt local JMS Session transaction với @Transactional của database được quản lý bởi DataSourceTransactionManager ra sao?
Bạn sẽ thiết kế xử lý message và cập nhật database nhất quán khi hai transaction managers không tự phối hợp ra sao?
Bạn giải thích JmsTransactionManager quản lý transaction nội bộ JMS Session theo phạm vi nào như thế nào?
Bạn sẽ lựa chọn JtaTransactionManager khi yêu cầu phối hợp XA transaction giữa JMS và database trong điều kiện nào?
Bạn phân tích chi phí, hạn chế hỗ trợ và rủi ro vận hành XA so với idempotent consumer và outbox như thế nào?
Bạn sẽ xác định khi nào nên dùng sessionTransacted thay vì dựa vào chế độ acknowledge mặc định ra sao?
Bạn phân tích vì sao AUTO_ACKNOWLEDGE có thể tạo ngữ nghĩa redelivery khác với local transacted session của listener container ra sao?
Bạn sẽ thiết kế listener ném exception sau xử lý lỗi để broker kích hoạt rollback hoặc redelivery theo chính sách như thế nào?
Bạn phân biệt lỗi business validation không thể sửa bằng retry với lỗi dependency tạm thời có thể retry như thế nào?
Bạn sẽ xử lý poison message liên tục gây lỗi conversion mà không làm queue bị kẹt vô hạn ra sao?
Bạn giải thích dead-letter queue giúp cô lập các thông điệp không thể xử lý sau số lần redelivery như thế nào?
Bạn phân biệt cơ chế dead-lettering do broker cấu hình với ErrorHandler trong Spring listener container ra sao?
Bạn sẽ xây dựng chính sách backoff giữa các lần redelivery phù hợp với giới hạn của JMS provider ra sao?
Bạn phân tích rủi ro retry dồn dập trên cùng một message làm nghẽn những message hợp lệ phía sau như thế nào?
Bạn sẽ sử dụng JMSXDeliveryCount khi được provider hỗ trợ để quan sát số lượt phát lại như thế nào?
Bạn sẽ xác định khi nào một message nên được chuyển sang dead-letter destination để xử lý thủ công như thế nào?
Bạn đánh giá ảnh hưởng của redelivery đối với thao tác ghi dữ liệu hoặc gọi API không idempotent ra sao?
Bạn sẽ thiết kế idempotent consumer theo business message ID và unique constraint trong database như thế nào?
Bạn phân tích tình huống database commit thành công nhưng JMS Session rollback do mất kết nối và message được phát lại như thế nào?
Bạn sẽ thiết kế transactional inbox để chống trùng và ghi lại trạng thái xử lý message theo cách nào?
Bạn phân biệt exactly-once business effect với at-least-once message delivery khi thiết kế nghiệp vụ như thế nào?
Bạn sẽ xác định điểm ghi dấu xử lý thành công sao cho việc retry không làm tạo thêm side effects như thế nào?
Bạn phân tích rủi ro acknowledgment trước khi dữ liệu nghiệp vụ thực sự được lưu bền vững ra sao?
Bạn sẽ xử lý một message đã đến DLQ sau khi downstream service khôi phục để phát lại có kiểm soát như thế nào?
Bạn phân biệt replay message từ DLQ với khởi chạy lại tất cả messages từ queue gốc như thế nào?
Bạn sẽ thiết kế audit cho thao tác operator redrive DLQ mà không làm lộ payload chứa dữ liệu nhạy cảm ra sao?
Bạn sẽ giám sát số lần redelivery, tỷ lệ rollback và tốc độ tăng DLQ để phát hiện lỗi ứng dụng như thế nào?
Bạn đánh giá cách xử lý thứ tự nghiệp vụ khi một message lỗi bị chuyển DLQ nhưng message sau vẫn được tiêu thụ ra sao?
Bạn sẽ thiết kế correlation ID bảo toàn qua một lần redrive hoặc tạo message mới từ DLQ ra sao?
Bạn phân tích vì sao broker message ID có thể thay đổi khi publish lại và không nên làm khóa idempotency duy nhất ra sao?
Bạn sẽ tổ chức retry ở tầng business service khác retry do broker redelivery để tránh nhân số lần thực thi như thế nào?
Bạn giải thích vì sao một queue có nhiều consumers không bảo đảm thứ tự xử lý hoàn tất của các message như thế nào?
Bạn sẽ xác định khi nào cần giới hạn concurrency bằng một để bảo toàn một phần thứ tự thông điệp như thế nào?
Bạn phân tích vì sao một consumer duy nhất vẫn có thể gặp message redelivery và yêu cầu idempotency ra sao?
Bạn sẽ tổ chức partitioning theo business key nếu provider hỗ trợ message groups để giữ thứ tự từng nhóm như thế nào?
Bạn đánh giá giới hạn của JMSXGroupID hoặc message grouping theo khả năng cụ thể của broker như thế nào?
Bạn sẽ kiểm tra tính tương thích giữa Spring JMS listener factory và message grouping provider-specific như thế nào?
Bạn phân tích tác động của message priority và prefetch đến thứ tự thực tế consumer nhận message như thế nào?
Bạn sẽ xác định khi nào message ordering không nên là một giả định cứng của hợp đồng nghiệp vụ ra sao?
Bạn sẽ thiết kế deduplication window và chính sách retention của bảng processed messages như thế nào?
Bạn phân biệt sự cố consumer xử lý chậm với tình trạng producer gửi nhanh hơn khả năng broker lưu trữ như thế nào?
Bạn sẽ chọn mức concurrency dựa trên tốc độ xử lý, backlog và giới hạn downstream như thế nào?
Bạn phân tích ảnh hưởng của một listener xử lý message dài tới số Session và consumer slots đang bận ra sao?
Bạn sẽ đánh giá khi nào nên chia queue cho loại công việc nhanh và chậm thay vì dùng chung một destination như thế nào?
Bạn sẽ thiết kế bulkhead giới hạn các lời gọi downstream do listener kích hoạt ra sao?
Bạn phân tích rủi ro listener tạo thread mới cho mỗi message và trả về ngay khiến acknowledgment xảy ra quá sớm như thế nào?
Bạn sẽ thiết kế cách xử lý tác vụ dài trong listener để bảo đảm chỉ xác nhận message sau khi công việc bắt buộc hoàn tất như thế nào?
Bạn phân biệt số message đang ở queue với số message đã được broker dispatch nhưng chưa được acknowledge như thế nào?
Bạn sẽ đọc metrics pending, in-flight và consumer count để giải thích queue backlog ra sao?
Bạn phân tích chi phí tạo connection mới cho mỗi lần JmsTemplate.convertAndSend trong một service lưu lượng cao như thế nào?
Bạn sẽ đánh giá cách sử dụng CachingConnectionFactory để giảm connection churn mà không tạo cache chồng chéo ngoài ý muốn ra sao?
Bạn sẽ chọn kích thước session cache và số consumers để không vượt giới hạn resource của broker như thế nào?
Bạn phân tích rủi ro listener container tạo nhiều concurrent consumers nhưng database pool chỉ có ít connection ra sao?
Bạn sẽ giới hạn message size và tốc độ producer để ngăn broker tăng memory hoặc disk usage bất thường ra sao?
Bạn đánh giá chính sách message expiration khi backlog lớn khiến thông điệp hết TTL trước khi được phát ra sao?
Bạn sẽ kiểm soát lưu lượng producer bằng rate limiting hoặc cơ chế từ chối khi broker trở thành nút thắt như thế nào?
Bạn phân biệt timeout khi gửi message với timeout trong business processing do listener thực thi như thế nào?
Bạn sẽ thiết kế health check cho JMS broker mà không tiêu thụ hoặc tạo thông điệp nghiệp vụ giả như thế nào?
Bạn phân tích vì sao liveness của service không nên phụ thuộc cứng vào kết nối broker trong một outage ngắn như thế nào?
Bạn sẽ dùng readiness để xác định khi nào listener có thể nhận message an toàn theo trạng thái downstream như thế nào?
Bạn đánh giá rủi ro listener tự động start khi database chưa migrate schema hoặc dependency chưa sẵn sàng ra sao?
Bạn sẽ cấu hình autoStartup của listener container hoặc đăng ký start có kiểm soát trong trường hợp nào?
Bạn mô tả cách đo độ trễ từ lúc producer gửi message đến lúc @JmsListener bắt đầu xử lý như thế nào?
Bạn phân biệt queue waiting time, processing time và end-to-end latency của một message như thế nào?
Bạn sẽ xây dựng metric cho send success, listener failure và redelivery theo destination mà không dùng message ID làm tag ra sao?
Bạn giải thích Micrometer có thể được dùng như thế nào để đo thời gian xử lý listener và lỗi message conversion?
Bạn sẽ kết hợp Spring Boot Actuator với chỉ số từ JMS provider để xây dựng dashboard queue health như thế nào?
Bạn phân tích rủi ro metric cardinality tăng lớn khi gắn correlation ID hoặc tenant ID vào mọi series như thế nào?
Bạn sẽ ghi log listener ID, destination và business event type mà không log raw credentials hoặc PII ra sao?
Bạn sẽ thiết kế propagation của trace context qua JMS headers để liên hệ producer và consumer spans như thế nào?
Bạn phân biệt trace propagation được instrument tự động với việc tự mang correlation ID trong JMS property như thế nào?
Bạn sẽ xác định ảnh hưởng của retry và redelivery tới số spans được ghi cho cùng một business event như thế nào?
Bạn đánh giá cách tách lỗi broker connection, conversion và business handler trong dashboard như thế nào?
Bạn sẽ xây dựng alert khi DLQ tăng, message age tăng hoặc số active consumers giảm bất thường ra sao?
Bạn phân tích vì sao chỉ theo dõi tổng queue depth có thể bỏ sót những message đã được dispatch nhưng chưa ack ra sao?
Bạn sẽ lập runbook điều tra listener không tiêu thụ message dù queue còn backlog và broker vẫn hoạt động như thế nào?
Bạn xác định cách thu thập log của ConnectionFactory và listener container để tìm lỗi kết nối sau khi broker restart ra sao?
Bạn sẽ tổ chức cấu hình quyền send và consume riêng cho producer và consumer services theo nguyên tắc least privilege ra sao?
Bạn phân tích nguy cơ consumer tự deserialize ObjectMessage từ nguồn không đáng tin cậy mà không có whitelist type ra sao?
Bạn sẽ chọn JSON với schema validation và converter có giới hạn loại dữ liệu để giảm rủi ro deserialization như thế nào?
Bạn đánh giá cách kiểm soát message selector dựa trên input từ tenant mà không cho phép truy cập queue ngoài quyền ra sao?
Bạn sẽ xác định cách ngăn message body chứa secret bị ghi vào DLQ logs hoặc hệ thống giám sát ra sao?
Bạn phân tích cách kiểm soát permission cho temporary reply destinations trong mô hình request-reply như thế nào?
Bạn sẽ thiết kế hợp đồng event type và version để nhiều service Spring JMS triển khai độc lập mà vẫn tương thích ra sao?
Bạn phân biệt unit test cho producer service với integration test sử dụng một JMS provider thật như thế nào?
Bạn sẽ mock JmsTemplate để kiểm chứng queue name và payload mà không khởi động broker bằng cách nào?
Bạn phân tích rủi ro unit test chỉ verify convertAndSend nhưng bỏ qua cấu hình MessageConverter thực tế ra sao?
Bạn sẽ kiểm thử MappingJackson2MessageConverter serialize và deserialize DTO có trường mới hoặc trường bị thiếu như thế nào?
Bạn thiết kế test cho MessagePostProcessor đặt JMSCorrelationID và custom headers đúng như hợp đồng ra sao?
Bạn sẽ xác minh một @JmsListener method nhận đúng payload DTO và @Header values trong integration test như thế nào?
Bạn đánh giá cách sử dụng Testcontainers với ActiveMQ Artemis hoặc provider được chọn để kiểm thử tương tác Spring JMS ra sao?
Bạn sẽ cấu hình destination và credential riêng cho integration tests để không đụng broker production ra sao?
Bạn sẽ kiểm thử queue có hai competing consumers không xử lý cùng message đồng thời trong điều kiện bình thường như thế nào?
Bạn phân tích cách kiểm thử topic có hai subscribers độc lập mà mỗi bên nhận event riêng như thế nào?
Bạn sẽ tạo integration test cho durable subscription nhận thông điệp sau khi consumer tạm offline ra sao?
Bạn sẽ kiểm thử message selector loại bỏ các thông điệp không có property phù hợp như thế nào?
Bạn thiết kế test synchronous receive với receiveTimeout để không làm bộ test treo vô hạn như thế nào?
Bạn sẽ kiểm thử @SendTo và correlation ID khi dùng JmsTemplate.sendAndReceive theo kịch bản nào?
Bạn phân tích cách dùng Awaitility hoặc synchronization có timeout để test listener bất đồng bộ mà không dựa vào Thread.sleep cố định ra sao?
Bạn sẽ kiểm thử sessionTransacted=true khiến message được redeliver khi listener ném exception như thế nào?
Bạn đánh giá cách kiểm thử số lần delivery và chuyển message sang DLQ theo chính sách broker ra sao?
Bạn sẽ kiểm tra listener bắt exception rồi trả thành công có ngăn redelivery ngoài mong muốn ra sao?
Bạn thiết kế test message conversion failure không làm mất message quan trọng trước khi được đưa tới nơi xử lý lỗi ra sao?
Bạn sẽ kiểm tra một consumer idempotent chỉ ghi database một lần khi cùng business event được phát lại như thế nào?
Bạn phân tích cách test database commit rồi JMS rollback để xác minh nghiệp vụ không bị xử lý trùng ra sao?
Bạn sẽ đo throughput của listener theo concurrency=1 và concurrency lớn hơn mà vẫn kiểm tra dữ liệu đúng như thế nào?
Bạn sẽ kiểm thử shutdown khi listener đang xử lý message để xác minh transaction được hoàn tất hoặc rollback an toàn ra sao?
Bạn đánh giá cách mô phỏng broker restart trong integration test để kiểm tra container recovery như thế nào?
Bạn sẽ kiểm tra startup khi broker chưa sẵn sàng rồi phục hồi mà listener không cần restart ứng dụng ra sao?
Bạn sẽ xây dựng test publisher gửi message hết hạn và xác nhận listener không xử lý sau TTL trong điều kiện provider phù hợp như thế nào?
Bạn phân tích cách kiểm thử producer và consumer sử dụng đúng pubSubDomain khi destination cùng tên trên queue và topic ra sao?
Bạn sẽ xác định benchmark latency của JmsTemplate gửi message khi bật persistent delivery và TLS như thế nào?
Bạn sẽ mô phỏng backlog lớn và kiểm tra consumer không làm cạn database connection pool ra sao?
Bạn thiết kế load test với poison message để kiểm tra DLQ và bảo đảm thông điệp hợp lệ vẫn được xử lý như thế nào?
Bạn đánh giá tiêu chí nghiệm thu trước production cho JMS wiring, converter, listener concurrency, retry, security và telemetry như thế nào?
Nếu @JmsListener không được gọi dù queue có message, bạn sẽ kiểm tra @EnableJms, bean scanning, factory và destination như thế nào?
Nếu JmsTemplate gửi thành công nhưng consumer không nhận, bạn sẽ kiểm tra pubSubDomain, destination và selector ra sao?
Nếu producer gửi TextMessage JSON nhưng listener báo conversion error, bạn sẽ kiểm tra MessageConverter và type metadata như thế nào?
Nếu message selector hoạt động trên staging nhưng bỏ qua mọi message ở production, bạn sẽ xác minh tên và kiểu properties như thế nào?
Nếu @JmsListener nhận cùng một đơn hàng hai lần sau broker reconnect, bạn sẽ thiết kế idempotency và kiểm tra redelivery ra sao?
Nếu một consumer bị kẹt xử lý message trong khi queue backlog tăng, bạn sẽ xác định concurrency và giới hạn downstream ra sao?
Nếu tăng concurrentConsumers khiến thứ tự xử lý hóa đơn bị đảo, bạn sẽ điều chỉnh mô hình message grouping hoặc concurrency như thế nào?
Nếu sessionTransacted bị tắt và thông điệp mất sau listener exception, bạn sẽ kiểm tra acknowledgment và transaction semantics ra sao?
Nếu một poison message liên tục bị redeliver và chặn queue, bạn sẽ cấu hình DLQ, backoff và quy trình redrive như thế nào?
Nếu dữ liệu database đã commit nhưng JMS message được phát lại, bạn sẽ xác minh xử lý trùng và sửa transaction boundary ra sao?
Nếu application được nâng cấp sang jakarta.jms nhưng provider jar vẫn dùng javax.jms, bạn sẽ khoanh vùng lỗi tương thích như thế nào?
Nếu broker phục hồi nhưng listener container không tái kết nối, bạn sẽ kiểm tra ConnectionFactory, recoveryInterval và trạng thái container ra sao?
Nếu một durable topic subscriber mất backlog sau khi đổi clientId, bạn sẽ phân tích subscription identity và phương án chuyển đổi ra sao?
Nếu một request-reply JMS call timeout dù business handler đã xử lý, bạn sẽ kiểm tra JMSReplyTo, JMSCorrelationID và reply consumer ra sao?
Nếu shutdown Kubernetes Pod xảy ra giữa một message đang xử lý, bạn sẽ phối hợp lifecycle container và rollback an toàn như thế nào?
Nếu JmsTemplate gửi quá nhiều message khiến broker thiếu disk, bạn sẽ điều chỉnh delivery mode, rate limit và capacity như thế nào?
Nếu một consumer ném exception nhưng ErrorHandler vẫn log mà message không redeliver, bạn sẽ phân biệt vai trò ErrorHandler và acknowledgment ra sao?
Nếu metric queue depth thấp nhưng SLA processing vẫn tệ, bạn sẽ đo thời gian in-flight và xử lý thực tế như thế nào?
Nếu cần triển khai tích hợp Jakarta Messaging trong Spring từ đầu, bạn sẽ cấu hình ConnectionFactory, JmsTemplate, @JmsListener, converter, transaction, retry, bảo mật và kiểm thử ra sao?
