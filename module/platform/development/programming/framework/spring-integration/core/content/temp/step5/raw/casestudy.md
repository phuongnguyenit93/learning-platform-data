Một dịch vụ tiếp nhận đơn hàng tạo Spring Integration Message có payload là entity JPA mutable, khiến worker phía sau đọc trạng thái đã bị luồng HTTP chỉnh sửa sau lúc gửi thông điệp.
Nhóm xây Message<String> cho thông báo khách nhưng đặt email người nhận trong payload thay vì header, khiến endpoint lọc theo metadata không thể chọn đúng đích gửi.
Ứng dụng chuyển object đơn hàng thành Message qua MessageBuilder nhưng chỉ sao chép payload và bỏ headers, khiến correlationId cần cho bước đối soát bị mất giữa luồng.
Đội dùng MessageHeaders để chứa customerId làm số nhưng một adapter bên ngoài gửi cùng header dưới dạng String, khiến router phía sau gặp lỗi chuyển kiểu chỉ với request từ đối tác.
Một service phát sinh requestId mới ở mỗi bước transformer thay vì giữ header gốc, khiến trace của cùng giao dịch bị phân mảnh khi đi qua nhiều endpoint.
Nhóm đưa access token vào header của Message để gọi đối tác nhưng wire tap ghi toàn bộ headers, khiến thông tin xác thực xuất hiện trong kho log tập trung.
Ứng dụng đặt mã tenant vào một custom header do client kiểm soát mà không đối chiếu danh tính đã xác thực, khiến luồng cập nhật có thể ghi vào vùng dữ liệu của tenant khác.
Đội kỳ vọng có thể sửa trực tiếp MessageHeaders của thông điệp đã phát để gắn trạng thái xử lý, khiến một thao tác quản trị gặp lỗi vì cấu trúc header không mutable như thiết kế.
Một service tạo Message từ dữ liệu CSV nhưng header timestamp được hiểu là thời gian tạo bản ghi ở hệ thống nguồn, khiến báo cáo độ trễ bị sai vì timestamp là lúc tạo thông điệp.
Nhóm sử dụng cùng tên header cho mã kho và mã vùng tại hai integration flows, khiến service activator đọc nhầm nghĩa của header khi hai luồng được nối qua channel chung.
Ứng dụng đưa object lớn vào message header để tiện transform, khiến chi phí chuyển đổi và ghi log tăng mạnh khi phải gửi thông điệp qua broker.
Đội truyền một object custom trong header của Message giữa hai module nhưng component serialization không hiểu kiểu đó, khiến flow chỉ lỗi khi adapter chuyển sang kênh phân tán.
Một service nhận Message không có header replyChannel từ adapter bên ngoài nhưng bước request-reply phía sau kỳ vọng header này luôn tồn tại, khiến phản hồi không tìm được đường về.
Nhóm tái sử dụng cùng correlation ID cho tất cả đơn trong một batch mà không có định danh lô rõ, khiến aggregator gộp những thông điệp của các giao dịch khác nhau.
Ứng dụng gắn header contentType báo JSON nhưng payload thực là byte array đã nén, khiến transformer cố decode sai định dạng khi xử lý dữ liệu nhận từ đối tác.
Đội dùng MessageBuilder.copyHeadersIfAbsent để thêm metadata mặc định, nhưng incoming message có một giá trị cũ không còn hợp lệ nên mặc định mới không được áp dụng.
Một service dùng header sequenceNumber từ splitter để theo dõi thứ tự nhưng một bước custom transformer thay thế toàn bộ headers, khiến downstream resequencer không còn metadata chuỗi.
Nhóm định nghĩa một header boolean isPriority nhưng adapter đầu vào gửi chuỗi "false", khiến filter dùng so sánh kiểu dữ liệu và quyết định tuyến ưu tiên sai.
Ứng dụng dùng header để truyền toàn bộ thông tin khách hàng qua nhiều service, khiến các luồng không cần dữ liệu cá nhân vẫn có thể đọc nó từ message history.
Đội tạo Message payload chứa dữ liệu mã hóa nhưng thiếu metadata về phiên bản schema, khiến một flow mới không biết cách giải mã những thông điệp còn tồn từ phiên bản cũ.
Một dịch vụ chọn DirectChannel cho các bước tính giá nhưng service activator phía sau gọi HTTP đối tác chậm, khiến thread tiếp nhận API bị giữ suốt thời gian chờ.
Nhóm thay DirectChannel bằng ExecutorChannel để giảm latency nhưng tầng điều khiển vẫn giả định handler hoàn tất trước khi method gửi trả kết quả, khiến API trả thành công quá sớm.
Ứng dụng đẩy thông điệp vào QueueChannel mà không có poller tiêu thụ, khiến hàng đợi tăng dần và flow ngừng xử lý dù producer vẫn gửi thành công.
Đội đặt capacity của QueueChannel quá nhỏ cho một luồng nhập kho nhưng không quan sát thời gian chờ send, khiến những request HTTP bị kẹt khi đợt nhập hàng tăng đột ngột.
Một service chuyển từ QueueChannel trong bộ nhớ sang hệ thống nhắn tin bền nhưng vẫn kỳ vọng các message đang ở queue cũ được khôi phục sau restart, khiến nhiều đơn bị mất.
Nhóm sử dụng PublishSubscribeChannel để gửi một sự kiện cho audit và billing, nhưng một subscriber throw exception khiến đường xử lý còn lại không nhận thông điệp như kỳ vọng.
Ứng dụng bật Executor cho PublishSubscribeChannel nhưng log audit được ghi bất đồng bộ, khiến API kết thúc trước khi chứng từ theo dõi giao dịch đã được lưu.
Đội dùng PublishSubscribeChannel cho tín hiệu cần xử lý đúng một lần, khiến cùng message được gửi tới nhiều subscribers và tạo tác động nghiệp vụ lặp.
Một service gắn hai service activators vào DirectChannel và tưởng cả hai đều nhận mọi message, khiến chỉ một handler được chọn theo cơ chế dispatch của channel.
Nhóm dùng RoundRobin dispatch với nhiều handlers nhưng các handlers có chức năng khác nhau, khiến cùng loại đơn hàng được xử lý bởi logic không tương đương.
Ứng dụng có một PriorityChannel phục vụ hồ sơ ưu tiên nhưng message thiếu priority header nên khách VIP và thường không được xếp hàng theo chính sách.
Đội dùng PriorityChannel cho lệnh khẩn nhưng một lượng lớn message ưu tiên liên tục khiến nhóm hồ sơ thông thường bị chờ không giới hạn.
Một service chọn RendezvousChannel để đồng bộ producer và consumer, nhưng consumer đôi lúc không sẵn sàng khiến send bị timeout và workflow bị tắc.
Nhóm muốn bảo đảm thứ tự per-customer nhưng dùng ExecutorChannel chạy nhiều threads, khiến hai message thay đổi trạng thái tài khoản hoàn tất sai thứ tự.
Ứng dụng dùng channel đồng bộ giữa nhiều bước có transaction, rồi bổ sung ExecutorChannel ở giữa mà không kiểm tra tác động đến transaction context, khiến rollback không bao phủ bước sau.
Đội gửi object mutable qua ExecutorChannel cho nhiều luồng xử lý nhưng không đóng băng payload, khiến consumer đọc object đã bị producer thay đổi.
Một service đặt interceptor ghi log trên inputChannel nhưng messages được gửi qua một channel khác do router chọn, khiến một nhóm giao dịch không có audit trail.
Nhóm triển khai ChannelInterceptor thay đổi headers trước khi gửi nhưng không nhận diện message có source system đáng tin, khiến metadata quan trọng của đối tác bị ghi đè.
Ứng dụng dùng ChannelInterceptor để kiểm tra quota theo từng send, nhưng một message đi qua nhiều internal channels bị tính phí nhiều lần.
Đội dùng logging channel interceptor để in đầy đủ payload nhạy cảm trước khi dữ liệu được masking ở transformer, khiến log vận hành lưu số tài khoản khách.
Một service cài interceptor xác thực trên một channel public nhưng gateway nội bộ có thể gửi trực tiếp đến downstream channel, khiến một luồng có thể đi vòng kiểm tra quyền.
Nhóm dùng QueueChannel để tách tốc độ producer và consumer nhưng không đo độ dài hàng đợi, khiến hệ thống chỉ phát hiện backlog khi thời gian trả đơn đã vượt SLA.
Ứng dụng cấu hình poller chạy nhiều task trên queue mà một handler không idempotent, khiến những lần retry sau timeout có thể xử lý cùng giao dịch hơn một lần.
Đội dùng poller với fixed delay quá ngắn cho một nguồn luôn trả rỗng, khiến CPU và database chịu hàng nghìn lần polling không cần thiết trong giờ thấp điểm.
Một service đặt maxMessagesPerPoll nhỏ cho luồng đồng bộ dữ liệu lớn, khiến backlog không được giải phóng trước thời gian chốt báo cáo dù handler còn khả năng xử lý.
Nhóm cấu hình trigger poller theo giờ địa phương nhưng dịch vụ chạy ở vùng timezone khác, khiến các lần đồng bộ đêm diễn ra ngoài lịch đã công bố.
Ứng dụng bật nhiều concurrent pollers cho cùng một nguồn dữ liệu nhưng nguồn không có cơ chế claim/lock, khiến một số bản ghi được lấy và xử lý trùng.
Đội đặt task executor trong poller nhưng không giới hạn backlog công việc, khiến những đợt tăng tải tạo lượng tác vụ chờ lớn dù source polling có vẻ ổn định.
Một service dùng PollableChannel nhưng handler trong IntegrationFlow chỉ nhận message khi có poller, khiến thay đổi cấu hình làm flow ngừng mà không có lỗi lúc startup.
Nhóm chuyển luồng thông báo từ PollableChannel sang SubscribableChannel nhưng vẫn giữ cấu hình poller không còn phù hợp, khiến tiến trình triển khai mới có hành vi khác bản cũ.
Ứng dụng thêm một channel adapter lấy dữ liệu từ thư mục file nhưng một file đang được ghi dở đã được phát message, khiến transformer nhận nội dung chưa hoàn tất.
Đội dùng inbound channel adapter đọc thư mục chung nhưng không có tiêu chí đánh dấu file đã xử lý, khiến file cũ tiếp tục được gửi lại sau khi ứng dụng restart.
Một service dùng outbound channel adapter để gửi email rồi mong phản hồi đồng bộ qua replyChannel, khiến caller chờ một kết quả mà endpoint một chiều không tạo ra.
Nhóm nối inbound endpoint của đối tác tới direct channel nhưng downstream gateway yêu cầu response, khiến luồng chỉ lỗi khi adapter gửi message không có reply metadata.
Ứng dụng nhận message từ HTTP inbound gateway và gọi ba bước async, nhưng request timeout của HTTP đến trước khi bước cuối trả reply, khiến caller retry một giao dịch đang chạy.
Đội dùng MessagingGateway để trừ tồn kho nhưng method trả void nên client coi lệnh đã hoàn tất dù các handler về sau còn có thể thất bại.
Một service dùng @MessagingGateway interface với defaultRequestChannel sai tên, khiến ứng dụng biên dịch nhưng mỗi lời gọi runtime báo không có channel phù hợp.
Nhóm đổi tên requestChannel trong DSL mà không cập nhật gateway proxy, khiến chỉ những endpoints qua gateway cũ không gửi được message sau deploy.
Ứng dụng dùng gateway với replyTimeout ngắn hơn thời gian aggregator chờ đầy đủ các phần, khiến client nhận timeout dù kết quả tổng hợp vẫn được tạo sau đó.
Đội đặt requestTimeout thấp cho gateway gửi vào QueueChannel đầy, khiến một số lệnh thất bại lúc send nhưng UI ghi nhận thành lỗi downstream không rõ nguyên nhân.
Một service dùng hai gateways cùng gửi vào một channel chung nhưng các message không mang loại nghiệp vụ, khiến router phía sau không phân biệt yêu cầu thanh toán và tra cứu.
Nhóm gọi gateway trả Future nhưng tầng controller không quan sát exceptional completion, khiến lỗi downstream bị bỏ lỡ sau khi HTTP response đã hoàn tất.
Ứng dụng dùng gateway proxy trong batch nhưng một nhánh gọi trực tiếp downstream handler để tối ưu, khiến interceptor và quy tắc xác thực của flow không được thực thi.
Đội xử lý request-reply với nhiều replies tới cùng replyChannel, khiến một caller chỉ đợi một response còn những replies còn lại không có nơi tiêu thụ.
Một service đẩy request vào PublishSubscribeChannel và yêu cầu một reply đơn, nhưng nhiều subscribers trả kết quả làm gateway không xác định phản hồi nào đại diện nghiệp vụ.
Nhóm dùng temporary replyChannel trong một quá trình async dài, khiến consumer gửi trả sau khi người gọi timeout và không còn receiver cho thông điệp phản hồi.
Ứng dụng muốn truyền correlation ID từ HTTP request qua gateway nhưng không map request header cần thiết, khiến sự kiện downstream không thể đối chiếu yêu cầu ban đầu.
Đội tạo HTTP inbound gateway cho file lớn nhưng cả payload được nạp vào memory trước khi đẩy sang channel, khiến một khách upload khiến JVM gần cạn heap.
Một service gọi outbound gateway tới một API đối tác nhưng exception được biến thành ErrorMessage ở flow phụ và caller không được thông báo thất bại như hợp đồng.
Nhóm sử dụng generic gateway method với payload Object nhưng adapter nhận DTO theo type cụ thể, khiến một kiểu input mới chỉ gây lỗi chuyển đổi khi qua bước routing.
Ứng dụng cần gọi hai hệ thống trong cùng luồng tích hợp nhưng một remote gateway trả response không đúng định dạng, khiến message bị dừng ở transformation mà caller chỉ thấy timeout.
Đội dùng service activator cho lệnh có phản hồi nhưng handler trả null khi không tìm thấy dữ liệu, khiến gateway không nhận reply và chờ đến thời hạn hết.
Một service khai báo @ServiceActivator với inputChannel dùng chung cho nhiều payload types, nhưng method signature chỉ hỗ trợ một loại và gặp lỗi dispatch khi dữ liệu mới xuất hiện.
Nhóm đặt @Transformer trên method và dùng service activator khác cùng inputChannel, khiến thông điệp được một trong hai handler xử lý thay vì đi qua cả hai theo thứ tự.
Ứng dụng đặt outputChannel của endpoint sai tên, khiến transformer tạo dữ liệu đúng nhưng message không tới bước gửi đi mà flow dừng ở cấu hình kênh.
Đội có một poller endpoint theo lịch nhưng bean chưa được autoStartup bật trong profile mới, khiến kênh nhận có dữ liệu mà adapter không bắt đầu lấy.
Một service bị dừng endpoint để bảo trì nhưng upstream gateway vẫn gửi request vào DirectChannel, khiến caller nhận lỗi thiếu subscriber thay vì thông báo bảo trì có kiểm soát.
Nhóm tái khởi động endpoint khi deployment chưa khôi phục đủ connection pool, khiến những message được giao vào handler và thất bại hàng loạt lúc đầu startup.
Ứng dụng dùng Control Bus để bật/tắt một integration endpoint nhưng lệnh quản trị có thể được gửi từ cùng channel với client bình thường, khiến phân quyền thao tác vận hành không rõ.
Đội cấu hình một Service Activator gọi thư viện JDBC blocking ngay trên channel đồng bộ nhận từ WebFlux, khiến event loop bị giữ lâu khi database chậm.
Một service sử dụng endpoint gọi bên ngoài theo API version cũ nhưng thông điệp mới đã đổi field payload, khiến chỉ các bản ghi từ đối tác cập nhật trước bị lỗi.
Nhóm thêm gateway có AOP advice để đo thời gian nhưng một đường gửi trực tiếp tới channel bypass gateway, khiến latency dashboard bỏ sót phần xử lý thực tế.
Ứng dụng khai báo IntegrationFlow qua Java DSL nhưng một bean IntegrationFlow bị điều kiện profile loại bỏ, khiến gateway vẫn khởi tạo mà không có consumer tương ứng.
Đội xây hai IntegrationFlow bắt đầu từ cùng MessageChannel rồi kỳ vọng chúng xử lý nối tiếp, khiến message được phân phối theo semantics của channel thay vì theo thứ tự thiết kế.
Một service thay đổi thứ tự các bước .filter và .transform trong Java DSL, khiến điều kiện lọc kiểm tra nhầm kiểu payload sau lần refactor.
Nhóm dùng DSL để nối handler với gateway nhưng thiếu channel trung gian cần xử lý lỗi bất đồng bộ, khiến exception đi theo đường khác mong đợi sau khi đổi executor.
Ứng dụng cấu hình các IntegrationFlows động theo tenant nhưng không gỡ đăng ký flow khi tenant rời hệ thống, khiến endpoint và thread tăng dần theo thời gian.
Đội dùng IntegrationFlowContext để thêm flow lúc runtime nhưng hai lần deploy cấu hình cùng flow ID, khiến tên bean/endpoint bị xung đột khi đăng ký.
Một service tạo động IntegrationFlow cho từng đối tác nhưng không chặn số lượng đối tác chưa xác thực, khiến một user có thể tạo quá nhiều endpoint đang chạy.
Nhóm dùng DSL với nhiều transform liên tiếp nhưng thiếu tên định danh ổn định cho endpoint, khiến script vận hành không tìm được handler sau nâng cấp ứng dụng.
Ứng dụng chuyển XML Integration config cũ sang Java DSL nhưng tên channels của các module khác vẫn giữ nguyên, khiến một số gateway gửi tới channel chưa tồn tại.
Đội thêm một flow cho thông báo sự kiện bằng Java DSL nhưng dùng DirectChannel chung với luồng lệnh, khiến sự kiện đi nhầm vào consumer xử lý nghiệp vụ khác.
Một service dùng bridge để nối hai channels nhưng vô tình tạo vòng lặp routing khi một flow còn gửi trở lại kênh nguồn, khiến message được chuyển mãi tới khi cạn tài nguyên.
Nhóm tạo integration flow có điểm rẽ sai đường rồi dùng wireTap để quan sát, nhưng wireTap được cấu hình nhận payload nhạy cảm ngoài phạm vi audit cho phép.
Ứng dụng cấu hình wireTap tới channel đồng bộ với handler log chậm, khiến bước giám sát làm tăng latency của toàn bộ luồng thanh toán.
Đội dùng wireTap tới channel bất đồng bộ không giới hạn capacity, khiến khi dịch vụ logging mất kết nối hàng đợi giám sát tăng quá ngân sách bộ nhớ.
Một service kết hợp subflow DSL cho router nhưng một nhánh không có output channel hay terminal handler, khiến các message thuộc nhánh đó không còn đi tiếp như thiết kế.
Nhóm tái sử dụng cùng endpoint ID trong nhiều subflow DSL, khiến startup báo bean definition collision chỉ trên profile bật đủ các luồng.
Ứng dụng chuyển cùng cấu hình Java DSL giữa local và production nhưng profile production thêm channel interceptor không tương thích kiểu payload, khiến lỗi chỉ xuất hiện trên môi trường thật.
Đội cần theo dõi start/stop một số endpoint riêng nhưng IntegrationFlowContext registration tạo ID tự động, khiến thao tác vận hành nhắm nhầm flow sau restart.
Một service dùng transformer đổi JSON string thành ProductDTO nhưng một đối tác bổ sung field không tương thích, khiến toàn bộ luồng từ đối tác bị chặn ở bước parse.
Nhóm sử dụng Object-to-String transformer cho message chứa secret rồi đưa vào audit channel, khiến thông tin nhạy cảm được serialize thành văn bản rõ trong log.
Ứng dụng dùng payload type transformer để chuyển byte array thành String nhưng message không khai báo charset, khiến tên khách hàng có dấu tiếng Việt bị sai sau decode.
Đội thay JSON-to-Object transformer bằng converter khác nhưng header contentType vẫn là định dạng cũ, khiến outbound adapter gửi payload với metadata sai.
Một service chuyển entity Order sang OrderEvent nhưng transformer không sao chép correlationId và sequence headers, khiến aggregator không nối được các kết quả con.
Nhóm dùng transformer thay đổi trường amount từ BigDecimal sang double trong message, khiến tổng tiền được tính ở aggregator lệch giá trị nguồn sau nhiều lần cộng.
Ứng dụng nhận payload dạng Map từ file đối tác nhưng transformer giả định field số lượng luôn là Integer, khiến các bản ghi có chuỗi số bị lỗi ClassCastException.
Đội dựng ContentEnricher để tra cứu thông tin khách từ service ngoài nhưng endpoint tra cứu bị chậm, khiến mỗi message giữ luồng xử lý chính lâu hơn SLA.
Một service dùng header enricher để gắn region từ request nhưng override region đã xác thực trước đó, khiến router đẩy dữ liệu sang vùng lưu trữ không phù hợp.
Nhóm bổ sung metadata phân loại trong một enrich step nhưng business handler phía sau dùng bản payload trước làm nguồn ra, khiến các giá trị mới không được phản ánh ở API.
Ứng dụng gọi service lookup trong transformer cho từng dòng CSV nhưng file lớn có hàng chục nghìn dòng, khiến quá trình nhập tạo nhiều request lặp không cần thiết.
Đội chuyển Message<PdfDocument> sang byte array trong transformer nhưng không giải phóng stream/file resource, khiến pool file descriptors tăng mỗi lần tạo báo cáo.
Một service xử lý đồng thời các message trong transformer dùng object serializer không thread-safe, khiến payload của hai đơn bị trộn dưới tải cao.
Nhóm dùng transform để loại thông tin thẻ thanh toán khỏi payload nhưng những field nhạy cảm còn ở header trước đó, khiến dữ liệu vẫn đi qua logging channel.
Ứng dụng có transformer lấy tỷ giá theo tenant nhưng header tenantId bị mất ở bước trước, khiến giá được tính theo cấu hình mặc định dù request thuộc vùng khác.
Đội dùng transformer cập nhật trực tiếp mutable object từ upstream rồi gửi cùng object tới nhánh audit, khiến audit nhìn thấy trạng thái sau thay đổi thay vì bản gốc.
Một service áp transformer để chuẩn hóa mã sản phẩm nhưng một adapter khác đã chuẩn hóa trước, khiến một số mã bị biến đổi hai lần và không tìm thấy trong database.
Nhóm xử lý dữ liệu legacy XML qua transformer nhưng một message thiếu namespace, khiến dữ liệu được parse sai dù bước routing phía trước vẫn chấp nhận.
Ứng dụng chuyển đổi số tiền từ chuỗi theo locale nhưng transformer chạy trên JVM khác cấu hình ngôn ngữ, khiến cùng input tạo giá trị khác giữa các instance.
Đội lấy payload chứa list hàng hóa rồi transformer tạo một message mới chỉ giữ list, khiến replyChannel cần cho gateway không còn theo tới bước cuối.
Một service có custom transformer ném exception khi trường optional null, khiến message vào errorChannel thay vì đi tiếp dù nghiệp vụ cho phép giá trị thiếu.
Nhóm dùng transformer cho dữ liệu đơn hàng trước filter bảo mật nhưng xử lý quá nhiều dữ liệu nhạy cảm từ message cuối cùng sẽ bị từ chối, khiến chi phí và rủi ro tăng.
Ứng dụng dùng HeaderValueRouter để phân luồng theo priority nhưng giá trị header tới dưới dạng enum ở nội bộ và String từ HTTP, khiến tuyến không ổn định theo nguồn gửi.
Đội cấu hình PayloadTypeRouter trên message có payload là Map từ hai nghiệp vụ khác nhau, khiến mọi message đi cùng tuyến dù cấu trúc dữ liệu khác nhau.
Một service dùng ExpressionEvaluatingRouter dựa trên vùng giao hàng nhưng biểu thức gặp null khi địa chỉ chưa nhập, khiến flow báo lỗi thay vì quyết định tuyến phù hợp.
Nhóm định tuyến theo mã quốc gia từ payload mà chưa kiểm tra tenant quyền truy cập, khiến message từ tenant A có thể đi vào endpoint vùng riêng của tenant B.
Ứng dụng định nghĩa defaultOutputChannel cho router nhưng một loại message không khớp tuyến đã được đặt vào kênh mặc định chứa nghiệp vụ cập nhật, khiến dữ liệu xử lý nhầm.
Đội cấu hình Router map status từ "NEW" sang channel xử lý nhưng đối tác đổi status thành "new", khiến lô đơn mới đi vào kênh không có subscriber.
Một service dùng RecipientListRouter để gửi thông báo tới billing và audit nhưng hai recipients có side effect, khiến thông điệp bị xử lý lại khi một nhánh thất bại.
Nhóm dùng recipient list để phát sự kiện tới ba hệ thống nhưng một recipient không hoạt động, khiến nhóm hiểu nhầm rằng tất cả nhánh đã nhận khi send chỉ thành công ở một số đích.
Ứng dụng dùng router để chọn endpoint theo số tiền nhưng thời điểm lấy tỷ giá diễn ra sau bước routing, khiến các đơn quốc tế bị phân nhóm ưu tiên sai.
Đội thêm nhánh router mới cho đối tác nhưng channel chưa được khởi tạo trong một profile, khiến chỉ message của đối tác đó thất bại khi production chạy.
Một service gắn @Router trên method trả danh sách đích nhưng code trả channel name cũ sau refactor, khiến routing động không tìm được channel.
Nhóm dùng router chọn thị trường theo custom header nhưng header do nhiều nguồn ghi có định dạng khác nhau, khiến cùng khách bị phân về hai hệ thống khác.
Ứng dụng dùng router để tách read và write theo transaction state nhưng message mất header trạng thái khi đi qua QueueChannel, khiến nhánh viết bị chọn không phù hợp.
Đội xây router ưu tiên với điều kiện nhiều nhánh chồng nhau nhưng không thống nhất thứ tự kiểm tra, khiến message giá trị biên đi sai kênh trong lúc khuyến mãi.
Một service gửi cảnh báo tới hai recipients trong RecipientListRouter nhưng một endpoint chậm làm toàn flow đồng bộ kéo dài, khiến SLA của nhánh cảnh báo nhanh bị ảnh hưởng.
Nhóm tách luồng theo loại event bằng router nhưng payload chứa enum mới chưa được bổ sung mapping, khiến thông báo của phiên bản mới bị loại trong rolling upgrade.
Ứng dụng định tuyến message có header retryCount vượt ngưỡng sang kênh lỗi nhưng một handler đặt lại count về 0, khiến message lỗi lặp vô hạn.
Đội dùng Spring Integration filter cho order hợp lệ nhưng lựa chọn bỏ message không có discardChannel, khiến khách không biết đơn bị từ chối ở đâu.
Một service dùng @Filter để bỏ dữ liệu sai định dạng nhưng không bật throwExceptionOnRejection trong luồng request-reply, khiến gateway chỉ thấy timeout thay vì lý do không đạt điều kiện.
Nhóm dùng filter kiểm tra số tiền dương trước transformer locale, khiến chuỗi "0,5" hợp lệ ở một khu vực bị loại vì chưa được convert.
Ứng dụng dùng filter bỏ message đã xử lý nhưng bộ kiểm tra chỉ dựa vào ID từ đối tác không ổn định, khiến hai giao dịch khác nhau bị coi là trùng.
Đội dùng discardChannel để gửi đơn bị từ chối cho bộ phận hỗ trợ nhưng channel đó không có consumer trong profile mới, khiến lỗi kinh doanh không được lưu để tra cứu.
Một service đặt filter trước điểm kiểm tra quyền tenant, khiến dữ liệu không đáng tin cậy được ghi ở nhánh discard với nguyên token và thông tin khách.
Nhóm dùng MessageFilter trên trạng thái shipment nhưng một thay đổi schema thêm trạng thái HOLD, khiến các lô bị loại mà hệ thống dashboard chỉ đếm message qua filter.
Ứng dụng lọc theo một header optional nhưng header không có trên thông điệp từ batch legacy, khiến số lượng bản ghi nhập thành công giảm sau rollout.
Đội dùng filter chống spam cho nhiều tenant chung một state map, khiến một tenant gửi nhiều thông báo làm tenant khác bị lọc quá mức.
Một service dùng filter kiểm tra giờ hoạt động dựa trên timezone của JVM, khiến thông điệp từ thị trường khác bị từ chối ngoài giờ đúng của địa phương.
Nhóm gắn filter với hành vi throwExceptionOnRejection ở kênh công khai nhưng phía caller không phân biệt lỗi validation với sự cố hạ tầng, khiến request bị retry sai.
Ứng dụng có filter giới hạn mức tải nhưng không ghi log số message bị loại theo nhánh, khiến sản lượng sự kiện giảm mà không ai xác định nguyên nhân.
Đội định đẩy message không đạt filter vào hàng chờ kiểm duyệt nhưng discardChannel chỉ là DirectChannel chưa có handler, khiến message bị bỏ mà không được lưu.
Một service muốn chặn payload chứa tài liệu nhạy cảm nhưng filter chỉ xem field trong payload, khiến bản ghi bị lộ qua custom header chưa được kiểm tra.
Nhóm triển khai splitter để tách Order thành OrderLine messages nhưng không giữ correlationId và sequenceSize, khiến aggregator phía sau không biết các dòng thuộc đơn nào.
Ứng dụng splitter tạo một Flux các phần tử bất đồng bộ nhưng handler gom nhóm dùng giả định sequenceNumber luôn tăng theo thứ tự đến, khiến kết quả cuối trộn thứ tự dòng.
Đội tách file CSV thành hàng nghìn messages rồi lưu vào QueueChannel trong bộ nhớ, khiến một file lớn làm hàng đợi đầy trước khi poller xử lý kịp.
Một service split danh sách bao gồm phần tử rỗng nhưng aggregator chỉ chờ số dòng hợp lệ, khiến group không bao giờ đủ sequenceSize đã được phát từ splitter.
Nhóm tách một đơn thành nhiều bước xử lý và dùng cùng correlationId của request thay vì orderId, khiến hai đơn tạo trong cùng HTTP request bị gộp.
Ứng dụng đặt release strategy của aggregator theo số message nhận nhưng một sự kiện retry tới hai lần, khiến group được release trước khi đủ các phần khác nhau.
Đội có aggregator chờ đủ năm kết quả từ hệ thống ngoài nhưng một nguồn không bao giờ trả lời, khiến MessageGroupStore giữ hàng nghìn group không hoàn tất.
Một service muốn release group khi nhận marker cuối nhưng marker có thể đến trước một số phần từ kênh chậm, khiến báo cáo thiếu dữ liệu dù aggregator đã gửi kết quả.
Nhóm dùng timeout của aggregator ngắn hơn SLA hệ thống đối tác, khiến các thông điệp đến muộn bị xem như nhóm mới và không thể đối soát với kết quả trước.
Ứng dụng cấu hình expireGroupsUponCompletion không phù hợp khi có late replies, khiến cùng correlationId được tái sử dụng gây lỗi group hoặc release lại dữ liệu cũ.
Đội giữ completed groups trong memory để chống reply muộn nhưng không đặt chính sách dọn dẹp phù hợp, khiến MessageGroupStore tăng dung lượng theo ngày.
Một service có aggregator mặc định chỉ tồn tại trong bộ nhớ nhưng yêu cầu khôi phục job sau restart, khiến các nhóm tổng hợp chưa đủ phần bị mất khi pod thay thế.
Nhóm chuyển MessageGroupStore từ memory sang database nhưng thiếu ràng buộc transaction giữa nhận message và lưu group, khiến một bản ghi được xử lý nhưng trạng thái group chưa được persist.
Ứng dụng có MessageGroupStore dùng chung cho nhiều flow nhưng các nhóm từ hai nghiệp vụ trùng correlation key, khiến một số thông điệp bị ghép sai sau khi tập trung hạ tầng.
Đội bật group timeout cho aggregator nhưng timeout handler dùng cùng executor đang quá tải, khiến việc giải phóng group quá hạn chậm hơn rất nhiều so với cấu hình.
Một service dùng aggregator xuất danh sách payload nhưng downstream cần dữ liệu theo sequenceNumber, khiến thứ tự tổng hợp thay đổi giữa hai lần chạy khi phần tử đến lệch.
Nhóm gửi các phần kết quả tới aggregator qua nhiều channels có khả năng duplicate delivery, khiến số lượng message trong group lớn hơn số phần thực tế cần ghép.
Ứng dụng cần nhận partial results khi một nguồn chậm nhưng aggregation flow chỉ có tiêu chí đủ toàn bộ, khiến cả báo cáo không xuất hiện trước deadline caller.
Đội thay cấu hình groupTimeout trong bản release mới khi còn các nhóm cũ chưa kết thúc, khiến các đơn đang xử lý theo chính sách thời gian không đồng nhất.
Một service sử dụng aggregator để tổng hợp trạng thái giao hàng nhưng một phần kết quả chứa thông tin nhạy cảm của khách và được lưu lâu trong group store không mã hóa.
Nhóm cần hủy nhóm tổng hợp khi người dùng rút yêu cầu, nhưng cancellation chỉ dừng gateway chờ mà MessageGroupStore vẫn giữ các phần cho tới khi timeout.
Ứng dụng có splitter gửi ra message không có replyChannel sau một bước transformer tùy biến, khiến aggregator tạo kết quả nhưng gateway ban đầu không nhận phản hồi.
Đội sử dụng resequencer cho sự kiện tồn kho có sequenceNumber nhưng upstream gửi trùng số thứ tự sau failover, khiến luồng bị kẹt chờ phần không thể xác định.
Một service dùng resequencer để phục hồi thứ tự thông điệp nhưng một phần tử bị mất hoàn toàn, khiến các phần sau vẫn chờ và backlog tăng.
Nhóm tách flow thành splitter-aggregator rồi cho một nhánh lọc bỏ message không hợp lệ, khiến tổng hợp không có chiến lược xử lý phần bị loại.
Ứng dụng triển khai scatter-gather để hỏi nhiều dịch vụ báo giá nhưng một recipient không trả reply, khiến scatter-gather bị timeout dù các kết quả khác đã đủ cho nghiệp vụ.
Đội dùng publish-subscribe trong scatter-gather để gọi đồng thời nhiều nhà cung cấp nhưng cùng một response có thể đến hai lần khi retry, khiến kết quả báo giá tổng hợp bị trùng.
Một service triển khai barrier để chờ phê duyệt từ quản trị viên nhưng tín hiệu kích hoạt không bao giờ đến cho các đơn đã bị hủy, khiến nhiều message chờ vô hạn.
Nhóm dùng delayer để gửi thông báo sau thời gian chờ nhưng message bị thay đổi trạng thái trong thời gian trì hoãn, khiến người dùng nhận nhắc nhở không còn đúng.
Ứng dụng có delayer lưu message trong bộ nhớ nhưng phải bảo đảm gửi thông báo sau restart, khiến lịch nhắc bị mất khi pod đang giữ message bị thay thế.
Đội dùng resequencer theo header sequenceNumber nhưng hai bộ phận dùng cùng correlationId cho các loại event khác nhau, khiến một event bị giữ đợi thứ tự không thuộc loại đó.
Một service triển khai Claim Check để giảm kích thước message nhưng một bước lưu claim key chưa hoàn tất trước khi gửi message tiếp, khiến consumer không tìm được payload gốc.
Nhóm giữ payload trong MessageStore của Claim Check mà không có TTL hoặc dọn dẹp, khiến dữ liệu khách hàng còn lưu lâu sau khi workflow đã kết thúc.
Ứng dụng dùng Claim Check với storage key được truyền sang tenant khác mà không kiểm tra quyền, khiến một consumer có thể lấy payload nhạy cảm từ công việc của khách khác.
Đội định dùng message store chung cho delayer, aggregator và claim check nhưng không có namespace khóa rõ ràng, khiến vận hành khó phân biệt dữ liệu tồn của từng flow.
Một service cấu hình global errorChannel cho lỗi xử lý nhưng nhiều thành phần đều subscribe qua DirectChannel, khiến chỉ một error handler được chọn và đội giám sát bỏ lỡ lỗi.
Nhóm mong exception phát sinh trong ExecutorChannel đi ngược tới gateway HTTP như luồng đồng bộ, khiến caller nhận thành công dù handler bất đồng bộ đã thất bại.
Ứng dụng dùng custom errorChannel nhưng một endpoint không gắn error channel đó, khiến lỗi của endpoint đi vào đường xử lý mặc định thay vì workflow bù trừ.
Đội xử lý ErrorMessage chỉ bằng exception message mà không xem failedMessage, khiến đội hỗ trợ không đối chiếu được đơn hàng nào đã gây lỗi.
Một service ghi toàn bộ ErrorMessage vào log gồm payload hóa đơn chưa được che dữ liệu, khiến kho giám sát lưu thông tin cá nhân vượt phạm vi cho phép.
Nhóm định cho tất cả lỗi vào kênh retry nhưng một lỗi schema không thể tự sửa bị retry vô hạn, khiến message lỗi chiếm thread và băng thông.
Ứng dụng đặt RequestHandlerRetryAdvice cho outbound gateway ghi đơn nhưng không có idempotency key, khiến timeout sau khi đối tác đã lưu dẫn tới thao tác được lặp lại.
Đội bật retry advice ở service activator nhưng chỉ ghi nhận attempts trong ThreadLocal, khiến việc chuyển sang ExecutorChannel làm số lần retry bị tính sai.
Một service dùng RecoveryCallback để gửi message lỗi vào DLQ sau retry nhưng downstream cần lưu metadata lần thử, khiến operator không biết bản ghi đã thất bại bao nhiêu lần.
Nhóm cấu hình exponential backoff retry nhưng tác vụ blocking trong DirectChannel vẫn giữ thread HTTP trong suốt thời gian chờ, khiến pool phục vụ request bị cạn.
Ứng dụng nhận lỗi DB deadlock và retry toàn bộ một flow gồm email và ghi dữ liệu, khiến khách nhận nhiều email khi chỉ một transaction cuối cùng commit.
Đội chỉ đặt errorChannel cho inbound gateway nhưng nguồn là poller adapter, khiến lỗi đọc từ datasource không được đưa về đúng kênh cảnh báo.
Một service phân loại lỗi bằng MessagingException nhưng nested cause khác nhau giữa hai adapter, khiến cùng nguyên nhân hạ tầng bị gắn mức ưu tiên khác trên dashboard.
Nhóm dùng error handler mặc định chỉ log và swallow exception nhưng poller coi message đã xử lý xong, khiến dữ liệu lỗi không có cơ chế phục hồi.
Ứng dụng chuyển Message sang errorChannel sau lỗi nhưng quên gắn correlationId nghiệp vụ, khiến tác vụ bù trừ không biết message thuộc order nào.
Đội cần cảnh báo tức thời khi routing thất bại nhưng errorChannel nhận message bất đồng bộ có backlog lớn, khiến bộ phận trực nhận cảnh báo sau SLA.
Một service gửi ErrorMessage tới cùng PublishSubscribeChannel với event bình thường nhưng monitor không phân biệt error payload, khiến sai sót được thống kê như sự kiện thành công.
Nhóm có flow ghi database rồi phát file ra storage nhưng lỗi bước cuối chỉ được retry riêng, khiến bản ghi đã commit bị gửi lại file từ đầu và tạo dữ liệu trùng.
Ứng dụng dùng Transactional Poller cho dữ liệu nguồn nhưng ServiceActivator gọi HTTP đối tác bên ngoài transaction, khiến rollback SQL không phục hồi side effect đã phát sinh.
Đội gắn @Transactional vào gateway method nhưng chèn ExecutorChannel ở giữa, khiến transaction Spring không được mang sang thread xử lý phía sau.
Một service poll database lấy bản ghi mới rồi cập nhật trạng thái đã nhận, nhưng không có atomic claim khi chạy hai instance, khiến cùng bản ghi được gửi hai lần.
Nhóm xử lý message ở một flow có nhiều bước ghi dữ liệu nhưng một bước dùng datasource khác, khiến rollback chỉ áp dụng một phần khi có lỗi cuối.
Ứng dụng dùng IntegrationFlow gửi message vào QueueChannel trong bộ nhớ rồi commit transaction ghi đơn, khiến pod restart trước lúc consumer chạy làm mất thông điệp.
Đội phát sự kiện sau commit bằng flow riêng nhưng event có thể gửi lỗi khi database đã commit, khiến bản ghi nguồn mới không tới hệ thống downstream.
Một service dùng idempotent receiver trên inbound adapter nhưng metadata store không chia sẻ giữa nhiều pods, khiến cùng message bị xử lý một lần trên từng pod.
Nhóm cấu hình IdempotentReceiverInterceptor theo file name nhưng đối tác tái sử dụng file name cho các phiên bản mới, khiến dữ liệu hợp lệ bị coi là đã xử lý.
Ứng dụng dùng MetadataStore để đánh dấu event đã đọc trước khi bước gửi email hoàn tất, khiến lần retry không xử lý lại message sau khi email gửi thất bại.
Đội dùng RedisMetadataStore cho khóa idempotency nhưng Redis bị eviction do thiếu bộ nhớ, khiến message cũ có thể được xử lý lại khi nguồn phát lại.
Một service định dùng JdbcMetadataStore để tránh duplicate giữa các instance nhưng schema không có unique constraint thích hợp, khiến hai worker cùng ghi claim trong đợt tải cao.
Nhóm đặt TTL của idempotency key ngắn hơn thời gian broker redelivery, khiến event trùng được chấp nhận sau khi khóa hết hạn.
Ứng dụng xử lý batch ghi nhiều message nhưng transactional boundary được đặt ở từng phần riêng, khiến một lỗi giữa batch không thể rollback các phần đã hoàn tất.
Đội chuyển database của MessageGroupStore nhưng không di chuyển nhóm đang xử lý, khiến aggregator sau release quên những kết quả đã nhận trước đó.
Một service dùng synchronous DirectChannel với @Transactional nhưng một custom error handler nuốt exception, khiến database commit dù downstream xử lý đã thất bại.
Nhóm có inbound poller lặp lại thao tác đọc bản ghi sau timeout nhưng chưa xác định liệu message đã đến adapter outbound hay chưa, khiến đối tác nhận hai lệnh trùng.
Ứng dụng dùng delivery timeout rất ngắn để giảm chờ channel nhưng producer coi send=false là thành công, khiến một số thông điệp không được giao vào flow.
Đội dùng MessageChannel.send trực tiếp từ scheduled job nhưng bỏ qua giá trị trả về và exception, khiến bộ giám sát báo job thành công dù kênh không nhận message.
Một service tích hợp adapter tới hệ thống chỉ hỗ trợ at-least-once nhưng nhóm kỳ vọng exactly-once, khiến duplicate delivery sau restart làm lệch tổng doanh thu.
Nhóm bổ sung cơ chế retry cho một chuỗi ghi đơn mà không lưu idempotency ở nguồn, khiến một message có thể tạo hai bản ghi sau mất mạng ở bước trả kết quả.
Ứng dụng giữ partial aggregation results trong persistent MessageStore nhưng logic release strategy không xét nhóm đã từng hoàn tất, khiến sự kiện muộn bị gộp sai.
Đội sử dụng cùng database cho state của poller và nghiệp vụ nhưng transaction manager khác nhau, khiến checkpoint tiến độ không nhất quán với dữ liệu đã commit.
Một service có chức năng tái phát các message lỗi nhưng payload chứa schema từ phiên bản trước, khiến transformer mới không thể xử lý lại mà vẫn được đưa vào retry queue.
Nhóm thêm outbox ở luồng tạo đơn nhưng dispatcher Spring Integration dùng poller không kiểm soát ownership khi scale nhiều pod, khiến một event outbox được phát nhiều lần.
Ứng dụng có flow thanh toán dùng ErrorMessage để kích hoạt bù trừ nhưng errorMessage bị gửi trễ sau khi caller đã retry, khiến bù trừ của lần thử cũ ảnh hưởng lệnh mới.
Đội xử lý sự kiện khách bằng Splitter và Aggregator rồi cập nhật bảng tổng hợp, nhưng các message con có thể bị retry và gây double counting nếu release không kiểm tra duplicate.
Một service tích hợp file inbound và FTP outbound nhưng không xác nhận file được gửi xong trước khi đánh dấu metadata nguồn, khiến sự cố mạng làm mất bản cần chuyển.
Nhóm mở một MessagingGateway quản trị để gửi lệnh reset hệ thống nhưng không có xác thực riêng, khiến người dùng của ứng dụng có thể gửi Message tới channel vận hành.
Ứng dụng sử dụng header tenantId để router chọn database đích nhưng inbound channel adapter không xác thực danh tính nguồn, khiến dữ liệu bị chuyển sang schema sai tenant.
Đội đặt endpoint quản lý flow trên cùng inputChannel với thông điệp nghiệp vụ và không có filter quyền, khiến một message được tạo thủ công có thể bật tắt integration endpoints.
Một service ghi metadata xác thực vào MessageHeaders để chuyển qua nhiều bước nhưng audit logging interceptor vẫn ghi header nguyên vẹn, khiến token dịch vụ lọt vào log.
Nhóm dùng shared PublishSubscribeChannel cho các event của nhiều tenant nhưng một subscriber theo dõi tổng thể không lọc lại quyền, khiến thông tin khách khác xuất hiện trên dashboard.
Ứng dụng cho client gửi tên outputChannel như một phần payload và router dùng thẳng, khiến một bên ngoài có thể định tuyến message tới endpoint nội bộ không được công khai.
Đội nhận file từ đối tác có tên file chứa đường dẫn tương đối rồi dùng header đó làm tên tệp ghi ra, khiến thao tác xuất file có nguy cơ vượt khỏi thư mục được cấp phép.
Một service kiểm tra MIME type trong transformer nhưng lại tin contentType header do client tự khai, khiến payload độc hại có thể được xử lý theo bộ chuyển đổi không phù hợp.
Nhóm gửi dữ liệu cá nhân qua QueueChannel có thể bị chụp heap dump khi sự cố, khiến vòng đời giữ message trong bộ nhớ cần được đánh giá theo quy định lưu trữ.
Ứng dụng tạo metadata store cho idempotency chứa email khách làm khóa, khiến thông tin nhận dạng có thể nằm lâu trong Redis sau khi workflow hoàn tất.
Đội dùng router theo khu vực từ header chưa được kiểm chứng, khiến một đơn bắt buộc lưu ở EU có thể đi vào service lưu trữ thuộc region khác.
Một service có ServiceActivator gọi REST đối tác với API key giữ trong payload, khiến WireTap và errorChannel có thể sao chép secret sang các luồng quan sát.
Nhóm phân quyền các gateway HTTP nhưng không phân quyền internal MessageChannel, khiến một batch job có thể gửi trực tiếp message cập nhật giá mà không đi qua kiểm tra chính sách.
Ứng dụng dùng message history để tra vết giao dịch nhưng việc ghi lịch sử các endpoint chứa payload nhạy cảm làm bộ nhớ và log vượt ngân sách bảo mật.
Đội thêm Java DSL flow mới để route sự kiện khách VIP nhưng chưa có dashboard theo nhánh, khiến những message rơi vào defaultOutputChannel không được nhìn thấy.
Một service chỉ đo số message tới inputChannel mà không đo số message ra outputChannel, khiến một filter bỏ gần hết sự kiện mà hệ thống vẫn báo lưu lượng xử lý bình thường.
Nhóm dùng Micrometer để đo latency endpoint nhưng flow có QueueChannel giữa các bước, khiến chỉ số xử lý handler không phản ánh thời gian message chờ trong queue.
Ứng dụng tổng hợp message count của nhiều endpoints nhưng một message đi qua tám bước bị đếm tám lần, khiến báo cáo số đơn giao dịch tăng gấp nhiều lần thực tế.
Đội quan sát aggregator chỉ qua số output messages mà không theo dõi nhóm đang chờ, khiến một nguồn upstream mất tín hiệu làm backlog tích tụ không có cảnh báo.
Một service log từng payload ở wireTap khi chuyển file lớn, khiến CPU, disk và thời gian xử lý tăng mạnh dù business handler không thay đổi.
Nhóm gắn traceId ở HTTP gateway nhưng khi chuyển sang poller tạo Message mới không mang header, khiến distributed tracing bị đứt ở chặng xử lý nền.
Ứng dụng dùng channel interceptor để đo thời gian gửi nhưng không ghi số send timeout và send=false, khiến mất message khi queue đầy không hiện trên dashboard.
Đội bật actuator/management view cho Integration endpoints nhưng hai flows có tên tự sinh sau deploy, khiến runbook không tìm được endpoint cần dừng.
Một service cần điều tra deadlock nhưng logging của DirectChannel chỉ ghi tên handler, khiến không xác định được request nào đang chờ external API.
Nhóm định theo dõi retry attempts trong RequestHandlerRetryAdvice nhưng metric chỉ đếm lỗi cuối, khiến áp lực lên đối tác tăng mà biểu đồ thành công vẫn bình thường.
Ứng dụng chạy nhiều pollers nhưng không đo thời gian từ khi message xuất hiện tại nguồn tới lúc được claim, khiến SLA nhập dữ liệu bị vượt mà endpoint latency vẫn thấp.
Đội đo queue backlog bằng một gauge tùy biến nhưng MessageStore backend bị lag, khiến dashboard hiển thị số thấp hơn thực tế khi hệ thống nhiều pods cùng đọc.
Một service tách flow thành router và nhiều subflows nhưng log của một nhánh không có correlationId, khiến khi một đơn sai tuyến khó tái dựng toàn bộ đường đi.
Nhóm giữ MessageHistory cho mọi event với nhiều metadata chi tiết, khiến header size và log volume tăng khi một message đi qua hàng chục endpoints.
Ứng dụng chỉ cấu hình cảnh báo lỗi trong global errorChannel nhưng một số filter discard messages mà không phát error, khiến số đơn bị bỏ không kích hoạt cảnh báo.
Đội muốn phân biệt thông điệp đã được accepted và hoàn tất nghiệp vụ, nhưng chỉ ghi thành công khi MessageChannel.send trả true, khiến tỷ lệ thành công bị báo quá cao.
Một service đo tổng thời gian processing từ lúc Message được tạo nhưng clock của các node upstream lệch, khiến phần latency bị tính âm sau khi phân phối nhiều vùng.
Nhóm bổ sung Circuit Breaker advice vào một endpoint nhưng dashboard chỉ theo dõi lỗi handler, khiến số message bị chặn khi breaker mở không được phản ánh đầy đủ.
Ứng dụng dùng Integration Management metrics nhưng các dynamic flows đăng ký sau startup không được instrument giống flows tĩnh, khiến dashboard mất thông tin về tenant mới.
Đội chạy unit test trực tiếp transformer method bằng dữ liệu hợp lệ nhưng chưa gửi Message thật, khiến lỗi mất correlationId và replyChannel không được phát hiện.
Một service dùng @SpringIntegrationTest cho flow đồng bộ nhưng integration test không bật poller của QueueChannel, khiến các bước bất đồng bộ không thực sự được chạy.
Nhóm kiểm thử MessagingGateway bằng mock trả DTO nhưng không khởi tạo IntegrationFlow, khiến lỗi tên channel và timeout chỉ xuất hiện ở production.
Ứng dụng test DirectChannel với một subscriber nhưng production có hai handlers, khiến dispatch giữa handlers khác kỳ vọng không được kiểm chứng ở CI.
Đội kiểm thử filter chỉ assert message hợp lệ đi tiếp, không gửi message bị loại hay kiểm tra discardChannel, khiến workflow cảnh báo khi input sai không được đánh giá.
Một service dùng test payload cho splitter gồm ba phần tử đúng định dạng nhưng không thử phần tử null, khiến aggregator chờ mãi khi thực tế một phần bị loại.
Nhóm chạy aggregator test với các message đến đúng sequenceNumber nhưng không thử trễ, duplicate và thiếu một phần, khiến group timeout/release sai không được phát hiện.
Ứng dụng kiểm thử ErrorMessage bằng exception chung nhưng không kiểm tra failedMessage headers, khiến logic bù trừ thiếu thông tin orderId khi xảy ra lỗi thật.
Đội dùng MockIntegration cho outbound endpoint nhưng chỉ kiểm tra số lời gọi, khiến việc giữ metadata tenant và correlationId khi gửi ra ngoài không được xác minh.
Một service test gateway với default replyTimeout dài và nguồn luôn nhanh, khiến trường hợp một downstream treo làm caller hết deadline chưa được mô phỏng.
Nhóm thử QueueChannel với vài message nhưng không thử send timeout khi capacity đầy, khiến producer coi gửi thành công ngay cả lúc quá tải.
Ứng dụng chạy integration tests bằng in-memory MessageGroupStore nhưng production dùng JDBC, khiến lỗi persistence/transaction khi restart không được kiểm chứng.
Đội mock MetadataStore trong test idempotent receiver nhưng không chạy hai worker song song trên cùng khóa, khiến race ghi claim xuất hiện sau autoscaling.
Một service test RequestHandlerRetryAdvice với lỗi xảy ra trước khi gửi nhưng chưa thử timeout sau side effect, khiến tác vụ tạo đơn bị thực hiện lặp trong production.
Nhóm chạy test Java DSL flow với tất cả beans trong một profile, nhưng production chỉ bật vài adapters, khiến lúc deploy có channel không được đăng ký và router thất bại.
Ứng dụng test router với mã quốc gia phổ biến nhưng không thử giá trị không khớp mapping, khiến defaultOutputChannel đưa dữ liệu sai thị trường không được phát hiện.
Đội chạy thử dynamic IntegrationFlowContext registration một lần nhưng không đăng ký và hủy flow liên tiếp, khiến rò rỉ bean hoặc endpoint không được thấy trong test.
Một service kiểm thử Control Bus với tài khoản quản trị nhưng không thử user thường, khiến các lệnh stop/start endpoint có thể được gửi từ nguồn không đủ quyền.
Nhóm test nghiệp vụ trên DirectChannel đồng bộ nhưng production có ExecutorChannel và chuyển thread, khiến các giả định về ThreadLocal và transaction không được kiểm chứng.
Ứng dụng kiểm thử PublishSubscribeChannel với hai handlers luôn thành công nhưng chưa mô phỏng một subscriber lỗi, khiến hành vi giao dịch của các nhánh khi failure không rõ.
Đội test timeout aggregator khi mọi message đủ trước hạn nhưng không dùng clock kiểm soát để thử late replies, khiến completed group policy chưa được xác minh.
Một service kiểm thử transformer với DTO nhỏ nhưng production có payload XML vài MB, khiến memory, encoding và parser lỗi chỉ khi nhập hồ sơ lớn.
Nhóm mô phỏng inbound file adapter bằng file đã ghi hoàn tất nhưng không thử file còn đang được upload, khiến dữ liệu dở bị gửi vào flow trong production.
Ứng dụng test message handling trên một Spring context nhưng production có nhiều instance dùng chung metadata store, khiến duplicate processing sau failover không được kiểm tra.
Đội thử errorChannel chỉ với exception từ service activator nhưng không thử lỗi trước gateway hoặc trong poller, khiến một số đường lỗi không có cảnh báo khi triển khai.
Một service có contract test chỉ kiểm tra payload ra ngoài nhưng không assert header schemaVersion, khiến đối tác không parse được message của bản phát hành mới.
Nhóm dùng test static IntegrationFlowContext nhưng không xác minh dynamic flow IDs giữa hai lần restart, khiến công cụ vận hành trỏ sai endpoint sau rollout.
Ứng dụng cần kiểm tra bù trừ khi outbound adapter lỗi nhưng test chỉ assert exception được phát, khiến dữ liệu đã ghi ở upstream chưa được khôi phục theo nghiệp vụ.
Đội muốn chứng minh mỗi đơn chỉ được xử lý một lần dù nguồn có thể redeliver, nhưng bộ test chưa tái phát cùng Message sau restart và khi chạy đồng thời nhiều pod.
Một doanh nghiệp cần truy vết từ khi đơn được nhận qua gateway tới lúc gửi outbound, nhưng dashboard hiện chỉ có HTTP 200 và không ghi tình trạng aggregator, errorChannel hoặc retry.
