Bạn giải thích Enterprise Integration Patterns giúp giảm phụ thuộc giữa các thành phần ứng dụng và tiêu chuẩn hóa luồng thông điệp như thế nào?
Bạn phân biệt message-driven integration với việc các service gọi trực tiếp phương thức của nhau theo coupling, thời gian chờ và xử lý lỗi ra sao?
Bạn mô tả vai trò của Message, MessageChannel và MessageHandler trong kiến trúc Spring Integration như thế nào?
Bạn phân biệt payload và headers trong một Spring Message và quyết định loại metadata nào nên nằm ở mỗi phần ra sao?
Bạn thiết kế một thông điệp nghiệp vụ có business identifier, correlation ID và trace ID mà không sao chép dữ liệu nhạy cảm không cần thiết như thế nào?
Bạn giải thích vì sao message headers không nên được coi là nguồn tin cậy tuyệt đối khi thông điệp đi vào từ hệ thống bên ngoài như thế nào?
Bạn phân biệt inbound channel adapter, outbound channel adapter và gateway theo hướng di chuyển thông điệp và hợp đồng trả lời như thế nào?
Bạn xác định khi nào dùng một messaging gateway thay vì một adapter một chiều để kết nối hệ thống nghiệp vụ ra sao?
Bạn thiết kế luồng gồm ingress, validation, transformation, routing và delivery sao cho mỗi endpoint chỉ đảm nhận một trách nhiệm như thế nào?
Bạn giải thích vai trò của service activator trong IntegrationFlow khi cần gọi xử lý nghiệp vụ không phải một pattern chuyên biệt như thế nào?
Bạn phân biệt point-to-point channel với publish-subscribe channel khi một message có một hoặc nhiều consumer như thế nào?
Bạn quyết định khi nào dùng Java DSL IntegrationFlow thay vì annotations hoặc XML configuration theo quy mô và tính dễ kiểm thử ra sao?
Bạn thiết kế tên channel và endpoint để luồng thông điệp có thể truy vết trong logs và management tools như thế nào?
Bạn mô tả cách Spring Integration liên kết một endpoint với input channel và output channel trong chuỗi xử lý như thế nào?
Bạn giải thích vì sao việc chia một integration flow thành nhiều subflows có thể tăng khả năng tái sử dụng nhưng làm khó quan sát ra sao?
Bạn phân biệt request–reply flow với fire-and-forget flow theo yêu cầu caller nhận kết quả hoặc lỗi như thế nào?
Bạn xác định nơi đặt transaction boundary khi cùng một luồng đi qua nhiều endpoint đồng bộ và bất đồng bộ ra sao?
Bạn đánh giá vì sao một flow chạy trong cùng tiến trình không mặc nhiên có khả năng lưu trữ message bền vững sau khi ứng dụng dừng như thế nào?
Bạn thiết kế cơ chế phiên bản hóa payload giữa producer và consumer để thay đổi schema không làm hỏng các nhánh xử lý cũ như thế nào?
Bạn lựa chọn ranh giới giữa domain events và integration messages để không làm lộ domain object mutable trực tiếp qua các channel ra sao?
Bạn phân biệt DirectChannel với QueueChannel theo cách dispatch, lưu chờ và mối quan hệ giữa thread gửi với thread nhận như thế nào?
Bạn giải thích ExecutorChannel thay đổi thread thực thi và ranh giới transaction của một message flow ra sao?
Bạn xác định khi nào PublishSubscribeChannel phù hợp và cách xử lý một subscriber chạy chậm tác động tới các subscriber khác như thế nào?
Bạn so sánh DirectChannel với ExecutorChannel khi một caller cần nhận exception đồng bộ để rollback thao tác nghiệp vụ như thế nào?
Bạn thiết kế QueueChannel có giới hạn capacity để tránh nhận message vượt tốc độ xử lý mà làm tăng bộ nhớ vô hạn như thế nào?
Bạn phân biệt SubscribableChannel với PollableChannel theo cách endpoint đăng ký nhận hoặc chủ động lấy message như thế nào?
Bạn xác định cấu hình poller gồm fixed delay, maxMessagesPerPoll và task executor ảnh hưởng tới throughput như thế nào?
Bạn phân tích nguyên nhân một QueueChannel đầy khiến sender bị chặn hoặc send không thành công và cách lựa chọn chính sách quá tải ra sao?
Bạn thiết kế QueueChannel với persistent MessageStore và kiểm thử khả năng khôi phục các message đang chờ sau restart như thế nào?
Bạn đánh giá sự khác biệt giữa message store được dùng cho QueueChannel với lưu trữ trạng thái nhóm của Aggregator như thế nào?
Bạn lựa chọn Wire Tap để quan sát một luồng mà không biến logging hoặc audit thành bước bắt buộc của xử lý chính như thế nào?
Bạn giải thích tác động của Wire Tap bất đồng bộ đến thứ tự logs và việc một nhánh quan sát bị lỗi như thế nào?
Bạn thiết kế quy tắc không ghi toàn bộ payload nhạy cảm vào một monitoring channel khi bật Wire Tap ra sao?
Bạn phân biệt channel interceptor với endpoint advice khi cần can thiệp lúc message được gửi/nhận hoặc lúc handler xử lý như thế nào?
Bạn xác định những trường hợp việc đặt retry trên một channel interceptor có thể tạo hành vi khác với retry quanh một message handler ra sao?
Bạn lựa chọn channel topology để tránh vòng lặp gửi message qua nhiều router và channel mà không có điều kiện dừng như thế nào?
Bạn kiểm tra một flow không có consumer đăng ký cho output channel bằng những dữ liệu và lỗi runtime nào?
Bạn đánh giá rủi ro nhiều handler nhận message từ cùng một point-to-point channel nhưng nghiệp vụ lại mong tất cả đều được xử lý như thế nào?
Bạn thiết kế cách giới hạn tốc độ chuyển message từ hàng đợi tới downstream có quota thấp hơn nguồn phát như thế nào?
Bạn mô tả mục đích của Router pattern khi một message phải được đưa tới một hoặc nhiều nhánh theo tiêu chí nghiệp vụ như thế nào?
Bạn phân biệt Router với Filter khi một flow cần chọn nhánh xử lý thay vì chỉ chấp nhận hoặc từ chối message như thế nào?
Bạn lựa chọn PayloadTypeRouter khi loại payload quyết định endpoint đích và đánh giá các hạn chế khi schema phát triển như thế nào?
Bạn thiết kế HeaderValueRouter khi metadata của message xác định destination channel mà không phải phân tích lại payload như thế nào?
Bạn sử dụng RecipientListRouter khi một sự kiện phải đi đến nhiều nhánh độc lập và cần kiểm soát danh sách recipients ra sao?
Bạn quyết định khi nào dùng router theo biểu thức và khi nào dùng class riêng để kiểm tra quy tắc routing phức tạp như thế nào?
Bạn xác định cách cung cấp defaultOutputChannel hoặc xử lý message không khớp bất kỳ route nào theo yêu cầu hệ thống như thế nào?
Bạn thiết kế chính sách cho unknown event type sao cho message không bị bỏ qua âm thầm và có dữ liệu phục vụ điều tra như thế nào?
Bạn phân biệt routing theo giá trị header do hệ thống nội bộ tạo với routing theo header đến từ client không tin cậy ra sao?
Bạn ngăn dữ liệu đầu vào tự chọn arbitrary channel name để truy cập nhánh xử lý không được cấp quyền như thế nào?
Bạn thiết kế một router chuyển đơn hàng theo trạng thái PENDING, PAID hoặc CANCELLED và bảo đảm mỗi trạng thái có hành động phù hợp như thế nào?
Bạn kiểm thử router với tập đầu vào bao gồm null header, giá trị không hợp lệ và một business status mới như thế nào?
Bạn phân tích hậu quả của việc router trả nhiều destinations trong khi các nhánh cùng cập nhật một tài nguyên mutable như thế nào?
Bạn xác định hành vi khi một trong nhiều nhánh của RecipientListRouter thất bại và các nhánh còn lại đã thực thi side effect ra sao?
Bạn quyết định có nên tách routing và transformation thành hai endpoint để dễ quan sát, tái sử dụng và retry độc lập như thế nào?
Bạn phân biệt route tới channel trực tiếp với route tới subflow theo chi phí cấu hình và khả năng cô lập thay đổi như thế nào?
Bạn xây dựng lựa chọn recipient dựa trên quyền hoặc tenant mà không dựa vào tenant ID chưa xác thực trong headers ra sao?
Bạn xác định khi nào routing phải được quyết định lại sau khi message retry vì cấu hình hoặc trạng thái nghiệp vụ đã thay đổi như thế nào?
Bạn thiết kế fallback route có thể giám sát được khi downstream chính đang lỗi nhưng nghiệp vụ vẫn cho phép xử lý thay thế như thế nào?
Bạn phân biệt dynamic router dựa trên bảng cấu hình với router cố định theo rủi ro thay đổi destination trong runtime ra sao?
Bạn kiểm tra việc thêm một nhánh mới không làm thay đổi hành vi routing của các message type cũ bằng phương pháp nào?
Bạn đánh giá nguyên nhân một message bị chuyển nhầm nhánh do dữ liệu header và payload không nhất quán bằng cách truy vết như thế nào?
Bạn giải thích Filter pattern trong Spring Integration bảo vệ các endpoint sau khỏi message không đạt điều kiện như thế nào?
Bạn phân biệt MessageFilter với một validation service trả lỗi cho caller theo ngữ nghĩa loại bỏ message và báo lỗi như thế nào?
Bạn quyết định khi nào cấu hình discardChannel để giữ lại message bị từ chối thay vì bỏ qua chúng ra sao?
Bạn xác định khi nào nên bật throwExceptionOnRejection để caller hoặc cơ chế error handling nhận lỗi từ filter như thế nào?
Bạn thiết kế một filter chặn event thiếu business identifier mà không đưa message sai dữ liệu tới downstream như thế nào?
Bạn phân biệt lọc dựa trên header với lọc dựa trên payload khi đánh giá độ tin cậy và khả năng thay đổi schema ra sao?
Bạn lựa chọn predicate đơn giản hoặc @Filter method riêng khi điều kiện có nhiều quy tắc cần unit test như thế nào?
Bạn phân tích vì sao dùng Filter cho mọi lỗi schema có thể khiến message bị loại bỏ mà không đủ dữ liệu để phục hồi ra sao?
Bạn thiết kế luồng xử lý discard có reason code và correlation ID để có thể đối soát các event không được chấp nhận như thế nào?
Bạn xác định cách xử lý lỗi phát sinh ngay trong phép kiểm tra filter khác gì với kết quả predicate là false như thế nào?
Bạn kiểm thử filter chấp nhận đúng message và không gửi tiếp những message không thỏa điều kiện qua output channel ra sao?
Bạn quyết định nên đặt Filter trước hay sau Transformer khi dữ liệu cần normalize trước mới có thể đánh giá điều kiện như thế nào?
Bạn đánh giá việc gọi database trong predicate của filter ảnh hưởng đến latency và số lượng retry như thế nào?
Bạn phân biệt deduplication bằng idempotent receiver với filter chỉ kiểm tra điều kiện tĩnh của từng message ra sao?
Bạn thiết kế IdempotentReceiverInterceptor với metadata store phù hợp để chặn xử lý trùng khi message được phát lại như thế nào?
Bạn xác định nguy cơ đánh dấu message là đã xử lý trước khi side effect hoàn tất và cách chọn thời điểm cập nhật trạng thái idempotency ra sao?
Bạn kiểm tra một filter dựa trên trạng thái bên ngoài có thể cho kết quả khác sau retry và quyết định liệu hành vi đó có chấp nhận được như thế nào?
Bạn mô tả Transformer pattern chuyển đổi hình dạng message để các thành phần tích hợp không phụ thuộc schema của nhau như thế nào?
Bạn phân biệt Transformer với service activator khi một endpoint cần chuyển đổi dữ liệu thay vì thực thi side effect nghiệp vụ như thế nào?
Bạn thiết kế transformer từ JSON của hệ thống nguồn sang DTO chuẩn hóa và giữ lại metadata cần truy vết ra sao?
Bạn xác định trường hợp nào nên dùng @Transformer method thay vì transformer dùng biểu thức SpEL hoặc DSL như thế nào?
Bạn lựa chọn Content Enricher khi cần bổ sung dữ liệu từ hệ thống khác thay vì viết transformer chứa nhiều lời gọi I/O như thế nào?
Bạn phân biệt HeaderEnricher với PayloadEnricher về trách nhiệm bổ sung dữ liệu và ảnh hưởng tới downstream như thế nào?
Bạn thiết kế bước enrich correlation ID, source system và schema version nhưng không cho phép dữ liệu ngoài ghi đè các header quan trọng ra sao?
Bạn đánh giá rủi ro transformer sửa trực tiếp một object mutable được chia sẻ cho nhiều nhánh của PublishSubscribeChannel như thế nào?
Bạn xây dựng transformer bảo toàn idempotency key qua nhiều phiên bản payload mà không biến đổi ngữ nghĩa của key ra sao?
Bạn phân biệt chuyển đổi content type với chuyển đổi domain model khi phải xử lý chuỗi JSON, byte array và object Java ra sao?
Bạn xử lý event thiếu field mới sau schema evolution trong transformer mà không coi mọi dữ liệu cũ là hỏng như thế nào?
Bạn thiết kế transformer chuyển đổi enum không còn hỗ trợ sang trạng thái lỗi có thể theo dõi thay vì map âm thầm sang giá trị sai như thế nào?
Bạn xác định cách xử lý exception từ Jackson hoặc converter trong transformer khi output channel không được nhận payload nửa hợp lệ như thế nào?
Bạn kiểm thử tính bất biến của input message sau khi transformation và việc giữ nguyên các message headers cần thiết như thế nào?
Bạn phân tích chi phí serialize rồi deserialize liên tiếp giữa nhiều transformer và đề xuất cách giảm copy dữ liệu ra sao?
Bạn đánh giá khi nào Map hoặc GenericMessage payload là lựa chọn tạm thời và khi nào nên dùng schema typed rõ ràng cho các nhánh như thế nào?
Bạn phân biệt một transformer tạo payload mới với một message handler tạo message mới chứa headers khác theo tác động tới correlation như thế nào?
Bạn thiết kế phép biến đổi dữ liệu mà không đưa PII hoặc secrets vào những header được log bởi các endpoint quan sát như thế nào?
Bạn xác định cách đo thời gian xử lý riêng của transformer để biết nghẽn do mapping hay lời gọi làm giàu dữ liệu như thế nào?
Bạn giải thích Splitter pattern chia một message thành nhiều phần xử lý và những trường hợp nghiệp vụ phù hợp như thế nào?
Bạn so sánh dùng Splitter với gửi từng phần tử đầu vào trực tiếp qua channel khi cần biết quan hệ giữa các message con như thế nào?
Bạn mô tả cách Spring Integration bổ sung sequenceNumber, sequenceSize và correlationId cho các message được split theo mặc định như thế nào?
Bạn thiết kế splitter cho một đơn hàng chứa nhiều OrderLine để mỗi dòng được kiểm tra hoặc xử lý độc lập ra sao?
Bạn quyết định khi nào một splitter nên trả Collection, Iterable hoặc Stream và những giới hạn về kích thước dữ liệu như thế nào?
Bạn phân tích nguy cơ split hàng trăm nghìn phần tử khiến channel queue hoặc thread pool downstream quá tải như thế nào?
Bạn chọn kích thước batch khi chia file nhập liệu lớn để cân bằng thời gian xử lý, bộ nhớ và khả năng retry ra sao?
Bạn thiết kế splitter giữ nguyên business key và trace metadata để từng message con có thể được đối soát với nguồn gốc như thế nào?
Bạn phân biệt sequence metadata tự động của splitter với identifier nghiệp vụ của từng phần tử như thế nào?
Bạn xác định khi nào sử dụng applySequence hoặc cấu hình tương đương để các message từ publish-subscribe hoặc split có metadata phục vụ tổng hợp ra sao?
Bạn kiểm thử splitter với đầu vào rỗng, một phần tử, nhiều phần tử và phần tử dữ liệu sai như thế nào?
Bạn thiết kế cách xử lý một phần tử con thất bại mà không mặc nhiên gửi lại toàn bộ parent message nếu điều đó gây side effect trùng như thế nào?
Bạn phân tích sự khác nhau giữa split rồi route và route rồi split khi các loại phần tử cần được xử lý bởi các nhánh khác nhau như thế nào?
Bạn xác định thời điểm nào nên dùng một luồng xử lý tuần tự thay vì splitter song song để giữ thứ tự các thay đổi nghiệp vụ như thế nào?
Bạn quyết định khi nào cần Resequencer để khôi phục thứ tự phần tử sau khi xử lý bất đồng bộ qua nhiều channel như thế nào?
Bạn phân biệt Resequencer với Aggregator khi muốn sắp xếp các message hoặc gộp chúng thành một kết quả chung ra sao?
Bạn thiết kế test xác minh thứ tự và số lượng message con khi một splitter đi qua ExecutorChannel như thế nào?
Bạn đánh giá việc một splitter trả kết quả lazy có thể giữ tài nguyên database hoặc file quá lâu khi downstream xử lý chậm như thế nào?
Bạn xác định cách đặt giới hạn số message con để tránh payload bị lợi dụng gây khuếch đại lưu lượng trong hệ thống như thế nào?
Bạn giải thích Aggregator pattern giúp thu thập các message liên quan thành một kết quả như thế nào?
Bạn phân biệt CorrelationStrategy, ReleaseStrategy và MessageGroupProcessor trong vòng đời một nhóm message như thế nào?
Bạn mô tả cách correlationId được dùng để xác định MessageGroup và những rủi ro nếu nhiều workflow vô tình dùng cùng correlation key như thế nào?
Bạn thiết kế correlation key theo request ID và tenant ID để không gộp nhầm message của các yêu cầu hoặc tenant khác nhau ra sao?
Bạn xác định cách aggregator tận dụng sequenceSize và sequenceNumber khi nhận kết quả từ splitter như thế nào?
Bạn phân biệt release theo đủ sequence size với release theo điều kiện nghiệp vụ hoặc ngưỡng thời gian ra sao?
Bạn thiết kế một Aggregator chỉ trả kết quả khi các bước kiểm tra của mọi OrderLine bắt buộc đã hoàn tất như thế nào?
Bạn lựa chọn ReleaseStrategy riêng khi số lượng message mong đợi không thể biết trước lúc bắt đầu flow như thế nào?
Bạn phân tích vì sao mặc định dựa vào sequence metadata có thể không phù hợp khi splitter tạo message động hoặc một nhánh bị loại bởi Filter ra sao?
Bạn xác định cách aggregator xử lý message đến sai thứ tự và liệu thứ tự đó có quan trọng đối với kết quả cuối như thế nào?
Bạn thiết kế MessageGroupProcessor tạo summary mà vẫn giữ thông tin lỗi của từng phần tử đã được xử lý như thế nào?
Bạn phân biệt gộp các kết quả thành List với tính một aggregate thống kê để hạn chế kích thước output message như thế nào?
Bạn giải thích vai trò của MessageGroupStore trong việc lưu trạng thái các nhóm chờ được release như thế nào?
Bạn lựa chọn in-memory message group store hoặc persistent store theo yêu cầu khôi phục sau restart và quy mô dữ liệu ra sao?
Bạn phân tích nguy cơ Aggregator giữ nhóm chưa đầy đủ vô thời hạn khiến bộ nhớ hoặc database store tăng liên tục như thế nào?
Bạn thiết kế groupTimeout và xử lý nhóm quá hạn để workflow không bị treo nếu một phần kết quả không bao giờ đến như thế nào?
Bạn phân biệt gửi partial result khi hết hạn với từ chối kết quả chưa đủ theo hợp đồng nghiệp vụ như thế nào?
Bạn xác định khi nào discardChannel của aggregator cần lưu message muộn hoặc bị loại để phục vụ điều tra như thế nào?
Bạn thiết kế xử lý message đến muộn sau khi một group đã hoàn tất mà không tạo ra một tổng hợp thứ hai không mong muốn như thế nào?
Bạn phân tích tác động của expireGroupsUponCompletion đối với message trễ và khả năng tái sử dụng correlation key như thế nào?
Bạn xác định cách dọn các group bị bỏ rơi trong persistent MessageGroupStore và theo dõi tốc độ tích tụ của chúng như thế nào?
Bạn thiết kế group timeout khác nhau theo loại workflow nhưng vẫn giữ giới hạn tài nguyên rõ ràng như thế nào?
Bạn giải thích vì sao aggregation có trạng thái cần cơ chế khóa hoặc đồng bộ khi nhiều consumer đồng thời cập nhật cùng một message group như thế nào?
Bạn đánh giá khi nào cần shared message store và lock registry trong deployment nhiều instance thay vì mỗi instance tự giữ nhóm như thế nào?
Bạn xác định rủi ro hai replica nhận các phần của cùng một group nhưng lưu vào hai stores độc lập khiến release không xảy ra ra sao?
Bạn phân tích chính sách xử lý duplicate sequenceNumber khi một message được broker gửi lại và aggregator đã lưu phần trước đó như thế nào?
Bạn thiết kế idempotency trước aggregator để tránh một kết quả con bị tính nhiều lần khi các handler được retry ra sao?
Bạn kiểm thử aggregator với kết quả đến thiếu, trùng, muộn và sai thứ tự để xác minh release và expiration như thế nào?
Bạn đánh giá khả năng crash ngay lúc message group được release nhưng downstream chưa nhận output và cách xác định rủi ro gửi trùng hoặc mất dữ liệu ra sao?
Bạn mô tả cách một flow kết hợp Splitter, Filter và Aggregator mà không để Filter làm group chờ mãi vì sequence size ban đầu như thế nào?
Bạn lựa chọn cách báo lỗi từng phần hay fail toàn bộ workflow khi một trong các kết quả con không thể phục hồi như thế nào?
Bạn giải thích Gateway pattern cung cấp interface đồng bộ cho caller bên ngoài messaging flow như thế nào?
Bạn thiết kế interface @MessagingGateway để application service gửi yêu cầu mà không phụ thuộc trực tiếp vào channel names như thế nào?
Bạn phân biệt @Gateway annotation trên method với cấu hình defaultRequestChannel hoặc defaultReplyChannel ở interface như thế nào?
Bạn xác định cách Spring Integration chuyển arguments của gateway method thành payload và headers của request message ra sao?
Bạn dùng @Header hoặc @Headers trong gateway signature để truyền correlation hoặc tenant context theo chính sách tin cậy nào?
Bạn giải thích vai trò của replyChannel và errorChannel trong luồng request–reply đi qua gateway như thế nào?
Bạn phân biệt requestTimeout và replyTimeout của gateway và ảnh hưởng khi channel nhận hoặc downstream xử lý chậm ra sao?
Bạn thiết kế cách xử lý gateway timeout khi tác vụ downstream có thể vẫn tiếp tục chạy dù caller đã ngừng chờ như thế nào?
Bạn xác định khi nào một gateway trả void, giá trị thường hoặc kiểu trả bất đồng bộ theo nhu cầu caller như thế nào?
Bạn phân tích khả năng deadlock khi gateway chờ reply trên một thread pool mà các task downstream cũng cần sử dụng cùng pool đã đầy như thế nào?
Bạn thiết kế một gateway gọi flow có Router và Aggregator rồi trả kết quả tổng hợp về caller như thế nào?
Bạn kiểm tra điều gì xảy ra khi một nhánh không tạo reply khiến gateway chờ hết timeout mà không có lỗi rõ ràng ra sao?
Bạn phân biệt giao tiếp qua MessagingGateway với HTTP controller dùng request–reply theo thời hạn chờ và ranh giới transaction như thế nào?
Bạn xây dựng test gateway bằng cách gửi request và xác minh reply, exception mapping và correlation headers như thế nào?
Bạn giải thích vì sao retry một toàn bộ gateway call có thể kích hoạt lại những side effect đã hoàn thành ở các nhánh trước như thế nào?
Bạn thiết kế retry policy quanh một message handler có lỗi tạm thời bằng RequestHandlerRetryAdvice như thế nào?
Bạn phân biệt retry đồng bộ trong cùng call stack với retry sau khi message được lưu và phát lại qua queue bền vững như thế nào?
Bạn xác định những loại lỗi mạng hoặc timeout nào có thể retry và những lỗi dữ liệu hoặc validation nào phải được xử lý như lỗi vĩnh viễn ra sao?
Bạn lựa chọn backoff, số lần retry và jitter phù hợp để không khuếch đại quá tải khi downstream đang lỗi diện rộng như thế nào?
Bạn thiết kế Idempotent Receiver để retry một message không tạo thêm đơn hàng hoặc thanh toán khi side effect trước đó đã thành công như thế nào?
Bạn phân tích trường hợp kết quả HTTP downstream bị mất sau khi server đã commit và vì sao retry có thể tạo hành động trùng như thế nào?
Bạn xác định vị trí đặt retry advice trước hay sau Transformer hoặc Aggregator để giới hạn phạm vi lặp lại tác vụ như thế nào?
Bạn phân biệt lỗi được ném trực tiếp qua DirectChannel với ErrorMessage gửi tới errorChannel trong một đường đi bất đồng bộ như thế nào?
Bạn mô tả cấu trúc ErrorMessage và cách lưu original failed message cùng exception để chẩn đoán như thế nào?
Bạn xác định khi nào sử dụng global errorChannel và khi nào cần errorChannel riêng theo flow hoặc gateway như thế nào?
Bạn thiết kế một error flow phân loại lỗi tạm thời, lỗi dữ liệu và lỗi bất ngờ để quyết định retry, quarantine hoặc alert như thế nào?
Bạn phân biệt việc bắt exception rồi bỏ qua với việc gửi ErrorMessage có ngữ cảnh đủ để vận hành xử lý lại như thế nào?
Bạn đánh giá ảnh hưởng của việc error handler cũng phát sinh exception khiến thông điệp lỗi bị mất hoặc gây vòng lặp xử lý như thế nào?
Bạn thiết kế dead-letter hoặc quarantine channel có giới hạn lưu trữ, quyền truy cập và quy trình replay message an toàn như thế nào?
Bạn xác định dữ liệu tối thiểu cần lưu cho một message thất bại gồm event type, correlation ID, attempt count và reason code như thế nào?
Bạn kiểm tra ranh giới rollback của transaction khi một handler thất bại qua DirectChannel so với ExecutorChannel như thế nào?
Bạn quyết định khi nào gửi message lỗi cho monitor mà vẫn ném lại exception để transaction của caller có thể rollback ra sao?
Bạn sử dụng ErrorMessageSendingRecoverer hoặc recovery callback phù hợp để chuyển message hết retry sang tuyến xử lý lỗi như thế nào?
Bạn phân tích chính sách retry và recovery có thể làm mất thứ tự xử lý message theo business key như thế nào?
Bạn xây dựng chính sách replay với kiểm tra schema version và idempotency để không phát lại dữ liệu đã quá hạn nghiệp vụ ra sao?
Bạn mô tả vai trò của IntegrationFlow trong việc nối Router, Filter, Transformer, Splitter, Aggregator và Gateway thành một pipeline như thế nào?
Bạn thiết kế flow theo Java DSL với các tên endpoint rõ ràng để quan sát từng bước và thay đổi độc lập như thế nào?
Bạn xác định cách dùng MessageHistory hoặc correlation headers để lần theo một message đi qua các endpoint và nhánh routing như thế nào?
Bạn phân biệt việc log message ID với business correlation ID khi cần nối nhiều message con sau Splitter như thế nào?
Bạn chọn các metric như message count, handler duration, queue depth và failed message count để xác định bottleneck từng nhánh như thế nào?
Bạn phân tích hiện tượng Aggregator group count tăng liên tục nhưng output count bằng không bằng những dữ liệu nào?
Bạn chẩn đoán một flow nhận request qua Gateway nhưng không có reply bằng cách kiểm tra channel subscriptions, routing và release strategy như thế nào?
Bạn xác định nguyên nhân một message bị Filter loại âm thầm bằng cách kiểm tra discard policy và message history ra sao?
Bạn thiết kế unit test riêng cho Router, Filter hoặc Transformer bằng message payload và headers đại diện mà không phải nạp toàn bộ hệ thống như thế nào?
Bạn kiểm thử IntegrationFlow bằng các input/output test channels và assertion có timeout thay vì phụ thuộc Thread.sleep như thế nào?
Bạn sử dụng Spring Integration testing utilities như MockIntegrationContext khi cần thay endpoint thật bằng test handler theo cách nào?
Bạn kiểm thử một flow với Splitter và Aggregator khi các kết quả con đến bất đồng bộ và có một phần tử thất bại như thế nào?
Bạn mô phỏng retry hết số lần cho phép và xác minh ErrorMessage được chuyển tới đúng error channel mà không tạo duplicate side effect ra sao?
Bạn phân biệt kiểm thử đúng luồng message trong bộ nhớ với integration test thật trên Kafka, RabbitMQ hoặc database message store theo giới hạn nào?
Bạn thiết kế kiểm thử restart worker giữa lúc Aggregator đang giữ partial group để xác minh khả năng khôi phục theo cấu hình persistence như thế nào?
Bạn kiểm tra hành vi toàn flow khi router đổi nhánh theo một header do client tự cung cấp để phát hiện lỗ hổng phân quyền như thế nào?
Bạn lựa chọn cách cô lập state của message group store và metadata store giữa các bài test chạy song song ra sao?
Bạn đánh giá cách cấu hình logging và tracing tránh đưa payload chứa thông tin cá nhân vào log mà vẫn chẩn đoán được các nhánh thông điệp như thế nào?
Bạn thiết kế dashboard theo dõi tỉ lệ split/aggregate hoàn tất, nhóm quá hạn, retry và lỗi theo từng business flow như thế nào?
Bạn đề xuất kiến trúc Spring Integration cho một luồng đơn hàng có Gateway, Filter, Transformer, Router, Splitter, Aggregator, idempotent retry, error channel và kiểm thử end-to-end như thế nào?
