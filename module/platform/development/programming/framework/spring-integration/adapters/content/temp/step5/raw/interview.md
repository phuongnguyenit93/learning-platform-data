Bạn giải thích inbound channel adapter đưa dữ liệu từ hệ thống bên ngoài vào Spring Integration MessageChannel như thế nào?
Bạn phân biệt inbound channel adapter với outbound channel adapter theo hướng di chuyển message và vai trò của endpoint ra sao?
Bạn sẽ quyết định khi nào dùng messaging gateway thay vì channel adapter trong tích hợp với một hệ thống ngoài như thế nào?
Bạn phân biệt inbound gateway và outbound gateway theo hướng request-reply và đối tượng chủ động gửi yêu cầu ra sao?
Bạn mô tả mối liên hệ giữa Message, MessageHeaders, MessageChannel và MessageHandler trong một luồng adapter như thế nào?
Bạn sẽ lựa chọn DirectChannel, ExecutorChannel hoặc QueueChannel ở ranh giới một adapter dựa trên hành vi xử lý nào?
Bạn phân tích vì sao gửi thành công vào MessageChannel không nhất thiết đồng nghĩa dữ liệu đã được hệ thống đích xử lý xong như thế nào?
Bạn sẽ tổ chức luồng từ inbound adapter qua transformer, filter và outbound adapter mà vẫn giữ rõ trách nhiệm nghiệp vụ như thế nào?
Bạn giải thích Spring Integration DSL giúp khai báo luồng adapter và channel khác gì với đăng ký thủ công các endpoint beans như thế nào?
Bạn sẽ lựa chọn IntegrationFlow để ghép các adapter endpoints mà không làm domain service phụ thuộc chi tiết giao thức như thế nào?
Bạn phân biệt IntegrationFlow bean và các MessageChannel beans được tạo tự động trong một cấu hình fluent DSL như thế nào?
Bạn sẽ xác định khi nào đặt tên tường minh cho inputChannel và outputChannel thay vì phụ thuộc channel được tạo ngầm như thế nào?
Bạn phân tích rủi ro nhiều IntegrationFlow dùng trùng tên channel hoặc endpoint bean trong ApplicationContext như thế nào?
Bạn sẽ kiểm tra một inbound adapter đã được đăng ký nhưng chưa phát message do endpoint không start ra sao?
Bạn giải thích vai trò của SmartLifecycle trong việc start và stop các adapter endpoints được Spring quản lý như thế nào?
Bạn phân biệt autoStartup và phase của endpoint khi ứng dụng cần chờ dependencies bên ngoài sẵn sàng như thế nào?
Bạn sẽ tổ chức thứ tự shutdown để inbound adapters ngừng tiếp nhận trước khi outbound adapters và connection resources bị đóng ra sao?
Bạn phân tích nguy cơ một adapter chạy trong lúc schema database hoặc remote service chưa sẵn sàng sau deploy như thế nào?
Bạn sẽ chọn channel adapter thay vì một custom @Scheduled task khi cần chuẩn hóa message flow và xử lý lỗi như thế nào?
Bạn phân biệt event-driven message source với polling message source khi thiết kế inbound integration như thế nào?
Bạn sẽ thiết kế message contract giữa inbound adapter và domain service không phụ thuộc trực tiếp vào DTO của hệ thống ngoài ra sao?
Bạn phân tích vì sao header của broker hoặc remote protocol cần được chuẩn hóa trước khi chuyển tới core business logic như thế nào?
Bạn sẽ bảo toàn business correlation ID khi message đi qua nhiều adapters và transformers theo quy ước nào?
Bạn phân biệt Spring Integration message ID với business event ID dùng để chống xử lý trùng như thế nào?
Bạn sẽ tổ chức errorChannel và discardChannel để không âm thầm bỏ qua dữ liệu từ hệ thống ngoài như thế nào?
Bạn đánh giá khi nào cần wireTap để quan sát message flow nhưng không làm chậm đường xử lý chính như thế nào?
Bạn sẽ dùng IntegrationFlowContext để đăng ký hoặc hủy luồng tích hợp động trong trường hợp nào?
Bạn phân tích rủi ro đăng ký integration flow mới mỗi lần request mà không giải phóng endpoints và connections ra sao?
Bạn sẽ đặt boundary test giữa adapter infrastructure và application service để có thể thay SFTP bằng API mà không sửa domain tests như thế nào?
Bạn giải thích vai trò của MessageSource và MessageProducerSupport trong việc triển khai inbound adapters theo các mẫu khác nhau như thế nào?
Bạn sẽ phân biệt MessageHandler outbound endpoint với gateway có replyChannel khi cần phản hồi tới caller ra sao?
Bạn đánh giá các đặc điểm của synchronous handoff và asynchronous handoff ảnh hưởng cách lỗi truyền ngược lên adapter như thế nào?
Bạn sẽ xác định đâu là đoạn code cần thực thi trong transaction và đâu là đoạn chỉ có retry hoặc eventual consistency ra sao?
Bạn giải thích PollerMetadata quản lý lịch lấy message từ một MessageSource trong Spring Integration như thế nào?
Bạn sẽ chọn fixedDelay hay fixedRate cho poller theo thời gian xử lý trung bình và nguy cơ hai lượt chạy chồng nhau ra sao?
Bạn mô tả cách @Poller được dùng trong cấu hình inbound polling endpoint như thế nào?
Bạn phân biệt cron-based polling với fixed-delay polling khi hệ thống nguồn chỉ cập nhật dữ liệu theo khung giờ như thế nào?
Bạn sẽ chọn maxMessagesPerPoll để cân bằng throughput và công bằng giữa nhiều inbound sources ra sao?
Bạn phân tích rủi ro maxMessagesPerPoll không giới hạn làm một poller giữ thread quá lâu khi nguồn có backlog lớn như thế nào?
Bạn sẽ cấu hình poller TaskExecutor khi cần nhiều tác vụ nhưng vẫn bảo vệ tính thứ tự nghiệp vụ ra sao?
Bạn phân biệt concurrency của poller task với concurrency của MessageHandler ở channel phía sau như thế nào?
Bạn sẽ tính toán connection pool và số API calls khi nhiều pollers cùng tăng concurrency như thế nào?
Bạn giải thích vì sao poller có transaction advice có thể ảnh hưởng ranh giới đọc nguồn và xử lý message như thế nào?
Bạn sẽ xác định khi nào dùng TransactionInterceptor trong poller để giữ trạng thái nguồn nhất quán ra sao?
Bạn phân tích nguy cơ poller commit checkpoint sớm trước khi outbound handler xử lý thành công như thế nào?
Bạn sẽ thiết kế transaction boundary quanh polling JDBC source và message processing trong cùng database theo cách nào?
Bạn phân biệt retry ở poller scheduler với retry ở downstream handler và retry từ hệ thống nguồn ra sao?
Bạn sẽ chọn errorChannel cho poller để phân biệt lỗi không lấy được dữ liệu với lỗi handler theo cách nào?
Bạn mô tả vai trò của ReceiveMessageAdvice hoặc advice chain trong tùy biến polling behavior ra sao?
Bạn phân tích vì sao advice thực thi quanh poll có thể không bao trùm toàn bộ asynchronous downstream processing như thế nào?
Bạn sẽ dùng control bus để start hoặc stop một polling endpoint khi cần bảo trì hệ thống ngoài như thế nào?
Bạn sẽ giám sát thời điểm poll gần nhất, thời gian một lần poll và số lượng records nhận được ra sao?
Bạn phân biệt poll timeout của nguồn với timeout xử lý toàn bộ một batch message như thế nào?
Bạn sẽ quyết định khi nào chuyển từ polling sang webhook-driven inbound gateway để giảm độ trễ như thế nào?
Bạn đánh giá cách ngăn hai ứng dụng replicas cùng poll và xử lý trùng bản ghi từ một nguồn không hỗ trợ locking ra sao?
Bạn sẽ thiết kế distributed coordination hoặc atomic claim record để nhiều pollers không cùng nhận một tác vụ như thế nào?
Bạn phân tích rủi ro lịch poll liên tục khi remote system bị outage làm sinh nhiều lỗi và tải không cần thiết như thế nào?
Bạn sẽ đặt exponential backoff và giới hạn concurrency ở tầng poller hay adapter trong trường hợp nào?
Bạn giải thích GatewayProxyFactoryBean hoặc @MessagingGateway giúp chuyển method calls thành message exchange như thế nào?
Bạn phân biệt @Gateway method với một inbound HTTP gateway tiếp nhận request mạng về nguồn kích hoạt như thế nào?
Bạn sẽ thiết kế @MessagingGateway interface trả domain DTO thay vì Message payload thô như thế nào?
Bạn mô tả tác dụng của defaultRequestChannel và defaultReplyChannel khi cấu hình @MessagingGateway như thế nào?
Bạn phân biệt requestTimeout và replyTimeout của messaging gateway theo giai đoạn gửi và chờ phản hồi ra sao?
Bạn phân tích vì sao replyChannel không có handler hoặc downstream không trả reply có thể làm gateway timeout như thế nào?
Bạn sẽ thiết kế asynchronous gateway return type phù hợp khi không muốn chặn thread caller như thế nào?
Bạn đánh giá khi nào không nên dùng request-reply gateway cho luồng fire-and-forget có xử lý mất nhiều thời gian ra sao?
Bạn giải thích FileReadingMessageSource theo dõi thư mục như thế nào để phát hiện tệp mới và tạo Spring Message?
Bạn phân biệt file inbound adapter đọc tệp từ thư mục với một messaging gateway xử lý request-reply ở ranh giới ứng dụng như thế nào?
Bạn sẽ cấu hình thư mục local, file pattern và filter để inbound adapter không nhận tệp ngoài định dạng được phép như thế nào?
Bạn mô tả vai trò của FileListFilter trong việc xác định tệp đủ điều kiện được đọc như thế nào?
Bạn phân biệt AcceptOnceFileListFilter và persistent accept-once filter khi ứng dụng restart ra sao?
Bạn sẽ lựa chọn CompositeFileListFilter hay ChainFileListFilter khi cần nhiều điều kiện lọc có thứ tự khác nhau như thế nào?
Bạn phân tích rủi ro tệp đang được một process khác ghi dở nhưng đã được inbound adapter phát vào flow như thế nào?
Bạn sẽ thiết kế hợp đồng ghi tệp tạm rồi đổi tên nguyên tử trước khi Spring Integration nhận tệp ra sao?
Bạn phân biệt nhận tệp theo extension với xác minh tệp đã ổn định kích thước trong một khoảng thời gian như thế nào?
Bạn sẽ sử dụng filter theo thời gian sửa đổi khi nguồn ghi tệp lớn chưa hoàn tất theo cơ chế nào?
Bạn phân tích ảnh hưởng của việc dùng filesystem timestamp thiếu chính xác đến filter chống nhận lại tệp như thế nào?
Bạn sẽ thiết kế idempotency theo file identity, checksum hoặc business ID thay vì chỉ filename ra sao?
Bạn mô tả luồng xử lý từ File inbound adapter qua splitter và transformer tới domain service như thế nào?
Bạn sẽ lựa chọn stream file contents thay vì đọc toàn bộ byte array khi file có kích thước lớn như thế nào?
Bạn phân tích rủi ro đọc file toàn bộ vào heap rồi gửi qua QueueChannel trong một hệ thống có backlog như thế nào?
Bạn sẽ thiết kế luồng lỗi chuyển tệp bị parse sai tới thư mục quarantine nhưng vẫn giữ bản gốc để điều tra ra sao?
Bạn đánh giá thời điểm di chuyển hoặc xóa tệp nguồn sau khi tất cả downstream operations thành công như thế nào?
Bạn phân biệt file lock ở hệ điều hành với kiểm soát xử lý trùng giữa nhiều application replicas ra sao?
Bạn sẽ chọn thư mục ingest riêng cho mỗi instance hay dùng coordination khi nhiều pods thấy chung một shared volume như thế nào?
Bạn mô tả vai trò của FileWritingMessageHandler trong một outbound file adapter như thế nào?
Bạn sẽ sử dụng File outbound adapter để ghi kết quả message thành tệp theo naming strategy nào?
Bạn phân biệt ghi mới, append và replace file trong một outbound handler theo yêu cầu business như thế nào?
Bạn sẽ thiết kế temporary file suffix và atomic rename để consumer phía ngoài không đọc tệp dở như thế nào?
Bạn phân tích rủi ro hai messages cùng tạo target filename dẫn tới ghi đè dữ liệu như thế nào?
Bạn sẽ xử lý trường hợp disk hết dung lượng ở bước ghi cuối cùng sau khi database đã commit như thế nào?
Bạn đánh giá khi nào cần file outbound gateway để chuyển, đọc hoặc thao tác tệp có reply thay vì chỉ ghi tệp ra sao?
Bạn sẽ tổ chức output directory theo tenant mà không cho phép path traversal từ message headers không tin cậy như thế nào?
Bạn phân tích rủi ro file path do client cung cấp có thể vượt ra ngoài thư mục được phép như thế nào?
Bạn sẽ chọn cách ghi file và cập nhật audit record để có khả năng retry an toàn khi một bước thất bại như thế nào?
Bạn mô tả cách giám sát số tệp chờ đọc, tốc độ xử lý và thư mục lỗi trong file integration như thế nào?
Bạn sẽ kiểm thử restart giữa lúc file đang được xử lý để bảo đảm filter và recovery không làm mất thông điệp ra sao?
Bạn phân tích ảnh hưởng của OS permissions và mount options đến khả năng tạo file hoặc rename trong container như thế nào?
Bạn sẽ quyết định khi nào xử lý nội dung tệp theo luồng thay vì sao chép toàn bộ tệp để kiểm soát disk space như thế nào?
Bạn giải thích SFTP inbound adapter đưa file từ một server ngoài về Spring Integration flow như thế nào?
Bạn phân biệt SFTP inbound synchronization adapter và SFTP inbound streaming adapter về việc tạo bản sao tệp cục bộ như thế nào?
Bạn sẽ chọn copy file về local trước khi parse hay stream trực tiếp từ remote server theo điều kiện nào?
Bạn mô tả vai trò của SessionFactory trong việc tạo và quản lý phiên kết nối tới SFTP server như thế nào?
Bạn phân biệt DefaultSftpSessionFactory với CachingSessionFactory theo mục tiêu cấu hình và tái sử dụng phiên ra sao?
Bạn sẽ giới hạn session cache và concurrent transfer để không vượt số phiên SFTP mà server cho phép như thế nào?
Bạn phân tích rủi ro dùng caching session lâu sau khi server đổi host key hoặc restart ra sao?
Bạn sẽ quản lý private key, password và known hosts trong Spring SFTP configuration mà không lưu secret trong source như thế nào?
Bạn phân biệt strict host key verification với việc vô hiệu hóa kiểm tra host key theo rủi ro bảo mật như thế nào?
Bạn sẽ thiết kế cơ chế rotation của credentials hoặc host keys mà không làm gián đoạn toàn bộ inbound flows như thế nào?
Bạn mô tả vai trò của remote file filter trong tránh tải những tệp SFTP đã được xử lý như thế nào?
Bạn phân biệt filter theo tên file với persistent remote file list filter khi ứng dụng chạy lại ra sao?
Bạn sẽ dùng shared metadata store hoặc chiến lược phân vùng khi nhiều replicas cùng truy cập một SFTP directory như thế nào?
Bạn phân tích rủi ro một remote file được overwrite cùng tên nhưng filter accept-once cho rằng đã nhận trước đó như thế nào?
Bạn sẽ phối hợp remote filter và local filter để tránh tải và xử lý trùng trong hai giai đoạn khác nhau ra sao?
Bạn mô tả phương án remote temporary suffix rồi rename khi đối tác upload tệp lớn qua SFTP như thế nào?
Bạn sẽ xác định khi nào một tệp remote đã sẵn sàng để tải mà không phụ thuộc chỉ vào timestamp như thế nào?
Bạn phân tích tác động của network disconnect giữa chừng tới bản sao file local chưa hoàn tất ra sao?
Bạn sẽ thiết kế local temporary directory và bước finalize để không phát file chưa tải xong vào downstream flow như thế nào?
Bạn sẽ chọn removeRemoteFiles hay giữ tệp nguồn và lưu checkpoint riêng theo hợp đồng dữ liệu nào?
Bạn đánh giá rủi ro xóa remote file trước khi downstream database transaction hoàn tất như thế nào?
Bạn sẽ lựa chọn SFTP outbound adapter để upload một file local hay outbound gateway để thực hiện thao tác có phản hồi theo tình huống nào?
Bạn mô tả cách remote directory expression và file name generator quyết định đích upload SFTP như thế nào?
Bạn sẽ ngăn remote path traversal khi tên thư mục được tạo từ message headers theo quy tắc nào?
Bạn phân tích nguy cơ hai producers cùng upload một remote filename và ghi đè lẫn nhau như thế nào?
Bạn sẽ dùng temporary remote filename rồi rename khi upload hoàn tất để tạo contract giao nhận tin cậy như thế nào?
Bạn sẽ thiết kế retry có backoff cho lỗi kết nối SFTP tạm thời nhưng không tải lại hoặc ghi đè tệp đã hoàn thành như thế nào?
Bạn đánh giá khi nào idempotency cần dựa trên checksum hoặc manifest thay vì remote filename như thế nào?
Bạn sẽ phân biệt lỗi xác thực SFTP với lỗi permission denied hoặc remote disk full trong metrics ra sao?
Bạn mô tả cách đóng session khi flow stop và bảo đảm stream từ inbound streaming adapter được giải phóng như thế nào?
Bạn sẽ kiểm thử luồng SFTP với server thử nghiệm có giới hạn sessions và hỗ trợ rename như thế nào?
Bạn phân tích các thay đổi cần kiểm tra khi nâng cấp thư viện SFTP client hoặc Spring Integration version ra sao?
Bạn giải thích HTTP inbound gateway kết nối HTTP request tới MessageChannel và nhận reply để trả HTTP response như thế nào?
Bạn phân biệt HTTP inbound gateway với HTTP inbound channel adapter khi endpoint có hoặc không cần reply như thế nào?
Bạn sẽ thiết kế request mapping, supported methods và payload converter cho HTTP inbound gateway theo API contract nào?
Bạn phân tích rủi ro một HTTP inbound gateway đợi reply vô hạn khi downstream flow không phát trả message ra sao?
Bạn sẽ đặt request timeout và reply timeout cho một HTTP gateway theo SLA và độ trễ phụ thuộc ngoài như thế nào?
Bạn mô tả cách HTTP outbound gateway chuyển một Spring Message thành request tới external REST API như thế nào?
Bạn phân biệt HTTP outbound gateway với HTTP outbound channel adapter về hành vi xử lý response như thế nào?
Bạn sẽ quyết định khi nào dùng HTTP outbound gateway thay vì RestClient hoặc WebClient trực tiếp trong một domain service ra sao?
Bạn phân tích vì sao outbound HTTP call bên trong transaction database có thể làm giữ lock và connection quá lâu như thế nào?
Bạn sẽ chọn method, URL expression, query parameters và header mapping trong outbound HTTP adapter theo policy nào?
Bạn mô tả cách HTTP header mapper chọn các headers được phép đưa ra ngoài thay vì chuyển mọi internal metadata ra sao?
Bạn sẽ ngăn SSRF khi target URL hoặc host được tạo từ message payload chưa đáng tin cậy như thế nào?
Bạn phân tích rủi ro dùng URL expression cho phép caller truy cập địa chỉ nội bộ ngoài allowlist ra sao?
Bạn sẽ xác thực request HTTP inbound bằng Spring Security trước khi chuyển message vào integration flow như thế nào?
Bạn sẽ thiết kế xử lý HTTP 4xx khác 5xx để chọn retry hay đưa message vào error channel như thế nào?
Bạn phân biệt HTTP request timeout với connect timeout và thời gian chờ reply từ integration flow ra sao?
Bạn sẽ chọn retry/backoff cho idempotent GET và non-idempotent POST như thế nào?
Bạn phân tích vì sao HTTP success code không tự bảo đảm asynchronous business processing đã hoàn tất như thế nào?
Bạn sẽ sử dụng request-reply correlation để ánh xạ HTTP response tới đúng request trong flow bất đồng bộ ra sao?
Bạn đánh giá khi nào cần trả HTTP 202 Accepted rồi xử lý tiếp qua message broker thay vì giữ connection mở như thế nào?
Bạn sẽ bảo vệ tokens và Authorization headers trong logs của outbound HTTP adapter theo nguyên tắc nào?
Bạn mô tả cách mapping JSON, binary và text content types qua HTTP gateways vào Message payload như thế nào?
Bạn sẽ giới hạn request body size khi inbound HTTP endpoint có khả năng nhận payload lớn như thế nào?
Bạn phân tích ảnh hưởng của retry storm khi một external HTTP API bị lỗi hàng loạt và nhiều Spring instances cùng retry ra sao?
Bạn sẽ thiết kế integration test cho HTTP inbound/outbound adapters bằng stub server và các kịch bản timeout như thế nào?
Bạn sẽ xác định cách quan sát external API latency riêng với thời gian chờ xử lý trong MessageChannel như thế nào?
Bạn giải thích JMS inbound channel adapter chuyển thông điệp từ queue hoặc topic thành Spring Message như thế nào?
Bạn phân biệt polling JMS inbound adapter và message-driven JMS inbound adapter theo cách nhận message và quản lý consumers như thế nào?
Bạn sẽ lựa chọn JMS inbound gateway khi cần request-reply qua JMS thay vì chỉ xử lý thông điệp một chiều như thế nào?
Bạn phân biệt JMS outbound adapter và JMS outbound gateway về việc có chờ reply từ broker consumer như thế nào?
Bạn mô tả cách Spring Integration kết hợp ConnectionFactory, listener container và MessageChannel khi nhận JMS message ra sao?
Bạn sẽ xác định acknowledgment mode và transaction của listener ảnh hưởng thời điểm message được xem là xử lý xong ra sao?
Bạn phân tích rủi ro JMS message được acknowledge trước khi downstream asynchronous handler hoàn thành ra sao?
Bạn sẽ chuẩn hóa JMSCorrelationID, destination và custom properties khi chuyển thành Spring MessageHeaders như thế nào?
Bạn sẽ thiết kế idempotent consumer nếu JMS broker phát lại một message sau mất kết nối như thế nào?
Bạn đánh giá khi nào dùng dead-letter queue cho JMS poison message thay vì retry mãi trong flow như thế nào?
Bạn sẽ tính giới hạn listener concurrency theo downstream database capacity khi queue backlog tăng ra sao?
Bạn phân biệt shared durable topic subscription với queue competing consumers trong cấu hình JMS adapters như thế nào?
Bạn sẽ kiểm thử JMS adapter với broker thật để xác minh redelivery, selector và transaction semantics ra sao?
Bạn giải thích AMQP inbound adapter nhận messages từ broker như RabbitMQ rồi chuyển vào MessageChannel như thế nào?
Bạn phân biệt AMQP inbound gateway với inbound channel adapter theo việc phát response tới requester như thế nào?
Bạn sẽ dùng AMQP outbound adapter cho event one-way và outbound gateway cho request-reply trong tình huống nào?
Bạn mô tả vai trò của listener container và AmqpTemplate trong việc kết nối Spring Integration với AMQP broker như thế nào?
Bạn sẽ quyết định ack và nack một AMQP message khi downstream handler thất bại theo những điều kiện nào?
Bạn phân tích rủi ro asynchronous handoff khiến RabbitMQ message được ack trước khi công việc thực sự hoàn tất như thế nào?
Bạn sẽ chọn prefetch và số concurrent consumers để không đẩy quá nhiều in-flight messages vào ứng dụng ra sao?
Bạn sẽ thiết kế dead-letter exchange, retry queue và poison message quarantine theo chính sách broker nào?
Bạn phân biệt AMQP routing key với MessageChannel name và business event type khi định tuyến như thế nào?
Bạn sẽ xử lý publisher confirm hoặc return từ broker để phân biệt thông điệp được broker chấp nhận với xử lý nghiệp vụ xong ra sao?
Bạn phân tích rủi ro retry publish AMQP sau timeout tạo duplicate messages như thế nào?
Bạn sẽ giữ correlation ID khi AMQP inbound adapter chuyển message qua transformer rồi outbound tới hệ thống khác ra sao?
Bạn đánh giá khi nào nên tách AMQP connection factory cho workloads có QoS và quyền truy cập khác nhau như thế nào?
Bạn sẽ kiểm thử AMQP flow với broker RabbitMQ thực và xác minh dead-letter routing như thế nào?
Bạn giải thích Kafka message-driven channel adapter chuyển Kafka records thành Spring Messages như thế nào?
Bạn phân biệt Kafka inbound channel adapter với Kafka inbound gateway khi cần xử lý request-reply dựa trên Kafka như thế nào?
Bạn sẽ chọn Kafka outbound channel adapter cho publishing stream events theo hợp đồng nào?
Bạn mô tả cách topic, partition, consumer group và key ảnh hưởng việc Kafka adapter phân phối dữ liệu ra sao?
Bạn phân tích tác động của partition ordering khi downstream ExecutorChannel làm nhiều handlers xử lý song song như thế nào?
Bạn sẽ xác định thời điểm commit Kafka offset phù hợp với lúc xử lý downstream hoàn tất như thế nào?
Bạn đánh giá rủi ro offset được commit trước khi kết quả ghi database bền vững như thế nào?
Bạn sẽ thiết kế idempotency khi một record được Kafka consumer nhận lại do rebalance hoặc restart như thế nào?
Bạn phân biệt retry tại Kafka listener container với retry trong integration flow và dead-letter topic như thế nào?
Bạn sẽ quyết định khi nào dùng record-mode và batch-mode consumer theo đặc điểm payload và error handling ra sao?
Bạn mô tả cách Kafka headers và record metadata được ánh xạ vào Spring MessageHeaders như thế nào?
Bạn sẽ quản lý serialization schema và event version để producer và consumer triển khai độc lập như thế nào?
Bạn phân tích rủi ro Kafka consumer poll thread bị chặn quá lâu trong downstream HTTP call như thế nào?
Bạn sẽ đánh giá max.poll.interval.ms, số records mỗi poll và downstream concurrency cùng lúc như thế nào?
Bạn sẽ kiểm thử Kafka adapter trong tình huống rebalance, lỗi deserialize và redelivery theo cách nào?
Bạn phân biệt Kafka producer transaction với database transaction khi cần bảo đảm nhất quán xuyên hai tài nguyên như thế nào?
Bạn giải thích JDBC inbound adapter thực thi truy vấn polling để chuyển các hàng dữ liệu thành Message như thế nào?
Bạn phân biệt database polling adapter với một event-driven CDC connector trong việc phát hiện thay đổi dữ liệu ra sao?
Bạn sẽ cấu hình JDBC inbound poller để chỉ đọc records chưa được xử lý mà không quét toàn bảng mỗi lần như thế nào?
Bạn mô tả cách JdbcPollingChannelAdapter tương tác với DataSource và SQL query theo các bước nào?
Bạn sẽ lựa chọn update-after-read hoặc row claiming strategy để tránh poll lại cùng record như thế nào?
Bạn phân tích rủi ro một poller đọc records nhưng chưa cập nhật trạng thái thì ứng dụng crash như thế nào?
Bạn sẽ thiết kế atomic claim update cho nhiều replicas đồng thời poll cùng một bảng như thế nào?
Bạn đánh giá khi nào dùng SELECT FOR UPDATE SKIP LOCKED tùy khả năng database để phân chia công việc như thế nào?
Bạn sẽ chọn batch size, maxMessagesPerPoll và index sao cho không làm database quá tải như thế nào?
Bạn phân biệt transaction bao quanh poll với transaction bao quanh downstream processing khi có QueueChannel bất đồng bộ như thế nào?
Bạn sẽ thiết kế idempotency theo primary key hoặc business event ID khi bản ghi được đọc lại sau rollback ra sao?
Bạn phân tích ảnh hưởng của isolation level tới việc poll những bản ghi đang được transaction khác tạo như thế nào?
Bạn sẽ đặt checkpoint hoặc watermark theo ID hay timestamp và xử lý trường hợp cập nhật đến muộn như thế nào?
Bạn đánh giá vì sao dùng timestamp watermark có thể bỏ sót record khi clock skew hoặc transaction commit đến muộn như thế nào?
Bạn sẽ xử lý mapping ResultSet rows sang domain DTO mà không để lộ schema database vào business service như thế nào?
Bạn mô tả JDBC outbound adapter dùng message để thực hiện INSERT, UPDATE hoặc DELETE trong một database như thế nào?
Bạn phân biệt JDBC outbound adapter với JDBC outbound gateway khi caller cần lấy generated key hoặc query result ra sao?
Bạn sẽ kiểm soát tham số SQL bằng named parameters để tránh SQL injection từ message payload như thế nào?
Bạn phân tích rủi ro ghép trực tiếp tên bảng hoặc cột từ message headers vào dynamic SQL như thế nào?
Bạn sẽ kiểm tra số hàng bị cập nhật để phát hiện một message không tìm thấy bản ghi đích như thế nào?
Bạn đánh giá khi nào cần TransactionTemplate ở service trước khi đẩy message tới JDBC outbound adapter ra sao?
Bạn sẽ phân tích tác động của retry JDBC update gây ghi trùng hoặc tăng counter nhiều lần như thế nào?
Bạn sẽ thiết kế outbox polling inbound flow kết hợp broker outbound adapter và checkpoint an toàn như thế nào?
Bạn phân biệt database transaction đã commit với xác nhận broker đã nhận message trong luồng outbox như thế nào?
Bạn sẽ xác định cách xử lý schema migration khi SQL của JDBC adapter đổi nhưng còn các instance code cũ chạy như thế nào?
Bạn mô tả cách giám sát số records được poll, backlog và độ trễ xử lý từ database source ra sao?
Bạn sẽ sử dụng Testcontainers database để xác minh locking và transaction của JDBC adapter trong integration test như thế nào?
Bạn phân biệt lỗi tạo connection với lỗi parse message và lỗi nghiệp vụ sau adapter trong việc tổ chức error flow như thế nào?
Bạn sẽ chọn default errorChannel hay endpoint-specific error channel để xử lý lỗi mà không làm trộn các luồng độc lập ra sao?
Bạn mô tả cách ErrorMessage chứa failedMessage và exception hỗ trợ điều tra một thông điệp thất bại như thế nào?
Bạn sẽ thiết kế dead-letter flow riêng cho những message không thể xử lý do schema không hợp lệ như thế nào?
Bạn phân tích nguy cơ retry vô hạn trên poison message khiến một adapter không còn xử lý dữ liệu hợp lệ ra sao?
Bạn sẽ phân biệt retry của gateway với retry tại transport broker để tránh nhân số lần thực thi như thế nào?
Bạn đánh giá khi nào dùng RequestHandlerRetryAdvice với backoff và recoverer cho một outbound handler ra sao?
Bạn sẽ thiết kế circuit breaker hoặc bulkhead khi HTTP/SFTP outbound endpoint bị lỗi dài hạn như thế nào?
Bạn phân tích vì sao việc đưa message qua ExecutorChannel có thể tách ranh giới transaction và làm thay đổi error propagation như thế nào?
Bạn sẽ quyết định khi nào synchronous handoff cần thiết để ACK từ hệ thống nguồn chỉ sau khi xử lý thành công ra sao?
Bạn đánh giá cách dùng message store hoặc persistent queue để tránh mất message khi JVM crash sau khi inbound nhận dữ liệu ra sao?
Bạn sẽ xác định thời điểm cập nhật checkpoint cho file, SFTP, JDBC hoặc Kafka để tránh mất dữ liệu khi process chết như thế nào?
Bạn phân tích rủi ro nhiều adapter endpoints cùng dùng một metadata store không namespacing rõ ràng như thế nào?
Bạn sẽ thiết kế idempotent receiver dùng MetadataStore hoặc database unique constraint theo độ bền cần thiết như thế nào?
Bạn phân biệt simple in-memory metadata store với shared persistent MetadataStore trong hệ thống đa replica ra sao?
Bạn sẽ lựa chọn MessageStore hỗ trợ Group hoặc Aggregator state trong luồng có tệp phân mảnh theo yêu cầu nào?
Bạn phân tích nguy cơ payload quá lớn được giữ trong message store hoặc application heap làm tăng memory ra sao?
Bạn sẽ lựa chọn encryption in transit qua HTTPS, SFTP, AMQPS hoặc TLS broker theo transport nào?
Bạn đánh giá rủi ro tin tưởng file path, remote directory hoặc HTTP URL lấy từ headers chưa xác thực như thế nào?
Bạn sẽ giới hạn quyền tài khoản SFTP, broker và database theo vai trò inbound hoặc outbound endpoint ra sao?
Bạn sẽ cấu hình secret từ môi trường hoặc secret manager thay vì hardcode credentials trong DSL theo cách nào?
Bạn phân tích rủi ro log toàn bộ MessageHeaders khi chúng chứa Authorization token hoặc thông tin tenant nhạy cảm như thế nào?
Bạn sẽ thống nhất trace ID khi luồng message đi qua HTTP inbound, JMS outbound và Kafka consumer như thế nào?
Bạn mô tả cách Micrometer metrics hỗ trợ theo dõi send rate, handler latency và errors của integration endpoints như thế nào?
Bạn sẽ đánh giá khi nào Spring Integration Management hoặc Actuator metrics hữu ích để phát hiện endpoint không hoạt động ra sao?
Bạn sẽ thiết kế metric labels theo endpoint, transport và error type mà không tạo cardinality theo message ID như thế nào?
Bạn sẽ phân biệt queue lag, poll lag, handler processing time và outbound remote latency trên dashboard như thế nào?
Bạn phân tích vì sao chỉ quan sát adapter đã gửi thành công mà không quan sát downstream errors có thể che lỗi nghiệp vụ như thế nào?
Bạn sẽ dùng control bus hoặc lifecycle API để pause adapter khi hệ thống đích quá tải theo kịch bản nào?
Bạn đánh giá cách graceful shutdown giữ nguồn chưa ACK hoặc checkpoint để xử lý lại an toàn như thế nào?
Bạn sẽ xây dựng runbook kiểm tra inbound adapter có running nhưng không có message do source filter không khớp ra sao?
Bạn phân tích cách phân biệt SFTP connection failure, DNS outage và authentication failure trong các metrics ra sao?
Bạn sẽ lựa chọn transactional outbox hoặc saga khi flow kết hợp cập nhật JDBC và phát Kafka/AMQP event như thế nào?
Bạn sẽ xác định khi nào async fan-out không có transaction chung cần compensation hoặc eventual consistency ra sao?
Bạn phân biệt unit test transformer/business handler với integration test adapter sử dụng external resource thật như thế nào?
Bạn sẽ dùng Spring Integration test utilities để đưa message vào channel và xác nhận output mà không bật remote adapter như thế nào?
Bạn sẽ thay thế nguồn message bằng test channel khi unit test domain flow để tránh phụ thuộc vào file/SFTP như thế nào?
Bạn mô tả cách sử dụng MockIntegrationContext để thay endpoint trong integration test khi phiên bản hỗ trợ ra sao?
Bạn sẽ kiểm thử poller chỉ nhận đúng số records theo maxMessagesPerPoll và không xử lý trùng qua nhiều lần poll như thế nào?
Bạn đánh giá cách kiểm thử file inbound filter vẫn hoạt động sau khi restart ApplicationContext ra sao?
Bạn sẽ kiểm thử SFTP inbound streaming adapter đóng stream và session khi downstream xảy ra exception như thế nào?
Bạn sẽ dùng HTTP stub server để kiểm chứng outbound gateway xử lý status 429, 500 và timeout khác nhau như thế nào?
Bạn sẽ kiểm thử JMS transaction hoặc AMQP manual acknowledgment khi downstream handler thất bại ra sao?
Bạn sẽ dùng Testcontainers RabbitMQ, Kafka và database để kiểm thử adapters theo giao thức thật như thế nào?
Bạn sẽ kiểm chứng Kafka offset được commit sau khi xử lý dữ liệu thành công trong một test restart ra sao?
Bạn phân tích vì sao các test dùng Thread.sleep cố định dễ flaky khi integration flow chạy bất đồng bộ như thế nào?
Bạn sẽ thiết kế test dùng await condition có timeout và kiểm tra đúng correlation ID của reply như thế nào?
Bạn sẽ xác minh errorChannel nhận được ErrorMessage kèm failedMessage khi HTTP outbound handler thất bại ra sao?
Bạn đánh giá cách performance test nhiều flows đồng thời để tìm bottleneck ở poller thread pool hoặc MessageChannel ra sao?
Bạn sẽ định nghĩa checklist production về durability, retry, ack, credentials, lifecycle, tracing và schema compatibility cho adapter mới như thế nào?
Nếu SFTP inbound adapter tải lại tệp cũ sau restart, bạn sẽ kiểm tra persistent filter và metadata store như thế nào?
Nếu FileReadingMessageSource đọc tệp đang ghi dở rồi parser báo lỗi, bạn sẽ thay đổi handoff contract và file filter ra sao?
Nếu hai Spring instances cùng poll thư mục shared volume và xử lý trùng file, bạn sẽ thiết kế coordination hoặc idempotency như thế nào?
Nếu outbound file adapter ghi thành công một phần rồi container bị kill, bạn sẽ dùng temporary file và atomic rename ra sao?
Nếu HTTP outbound gateway gọi POST bị timeout nhưng remote service đã xử lý, bạn sẽ kết hợp idempotency và retry như thế nào?
Nếu HTTP inbound gateway không trả response dù downstream handler đã chạy, bạn sẽ truy tìm replyChannel và correlation headers ra sao?
Nếu JMS inbound adapter ACK trước khi async handler lưu database, bạn sẽ điều chỉnh channel boundary và transaction như thế nào?
Nếu AMQP prefetch quá cao làm một consumer giữ nhiều message chưa xử lý, bạn sẽ chỉnh prefetch và concurrency ra sao?
Nếu Kafka records bị xử lý lại sau partition rebalance, bạn sẽ kiểm tra offset commit và idempotent consumer như thế nào?
Nếu Kafka poll loop bị chặn bởi external HTTP call và consumer bị mất partition assignment, bạn sẽ thiết kế lại luồng xử lý ra sao?
Nếu JDBC poller bỏ sót record do timestamp watermark, bạn sẽ thiết kế lại cursor hoặc trạng thái claim như thế nào?
Nếu nhiều JDBC pollers cùng chọn một hàng chưa xử lý, bạn sẽ dùng transaction và atomic row claim ra sao?
Nếu hệ thống có hai outbound adapters cùng retry một event sau lỗi broker, bạn sẽ xác định các điểm tạo trùng như thế nào?
Nếu message đã vào QueueChannel nhưng JVM crash trước khi handler xử lý, bạn sẽ bổ sung persistence và recovery như thế nào?
Nếu errorChannel không nhận exception từ handler chạy trên executor, bạn sẽ kiểm tra error propagation và advice chain ra sao?
Nếu remote SFTP host key thay đổi đột ngột trong production, bạn sẽ điều tra bảo mật và rotation mà không tắt verification như thế nào?
Nếu outbound HTTP target URL lấy từ payload có thể truy cập metadata service nội bộ, bạn sẽ chặn SSRF ra sao?
Nếu các metrics cho biết adapter running nhưng backlog tăng, bạn sẽ so sánh poll rate, handler latency và downstream capacity như thế nào?
Nếu cần xây dựng Spring Integration flow ingest từ SFTP rồi lưu database và phát Kafka event, bạn sẽ tổ chức adapters, poller, idempotency, transaction, outbox và test như thế nào?
Nếu cần mở rộng hệ thống tích hợp file, HTTP, JMS và AMQP lên nhiều replicas, bạn sẽ thiết kế tài nguyên dùng chung, checkpoint, acknowledgment, lifecycle và observability như thế nào?
