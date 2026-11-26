Ứng dụng Spring Boot nhận yêu cầu tạo đơn hàng rồi gọi API thanh toán bằng RestClient; phía đối tác xử lý thành công nhưng phản hồi mất trên mạng khiến hệ thống nguồn không biết có nên gửi lại.
Dịch vụ quản lý kho chuyển sang WebClient để gọi API tồn kho, nhưng một đoạn xử lý đồng bộ vẫn chờ kết quả ngay trên event loop và làm các request khác tăng độ trễ.
Gateway Spring Boot gửi HTTP request đến dịch vụ vận chuyển với header xác thực nhưng token hết hạn giữa batch, khiến nửa số đơn được cập nhật và nửa còn lại bị từ chối.
Một RestClient kết nối đến đối tác chỉ cấu hình thời gian thiết lập kết nối, nên khi phía xa giữ socket mở mà không trả body, hàng trăm thread chờ quá lâu.
Ứng dụng gọi API tra cứu giá có thời gian đáp ứng không ổn định nhưng áp cùng timeout cho thao tác đọc giá và xác nhận thanh toán, làm mất các phản hồi nghiệp vụ quan trọng.
Nhóm tích hợp bật retry cho tất cả HTTP POST tạo hóa đơn khi gặp timeout; một lần client mất phản hồi tạo ra hai hóa đơn mặc dù API đích đã xử lý thành công.
Một WebClient dùng connection pool chung cho truy vấn đơn hàng ngắn và tải báo cáo nhiều phút, khiến các request nhỏ phải chờ kết nối dù hệ thống đích còn năng lực.
Ứng dụng Spring Boot nhận HTTP 429 từ đối tác nhưng client tiếp tục retry ngay lập tức, làm giới hạn tốc độ của đối tác bị chạm liên tục trong giờ cao điểm.
Nhóm chuyển API nội bộ từ JSON sang một schema mới nhưng RestClient vẫn ánh xạ bằng DTO cũ, khiến trường trạng thái bắt buộc bị bỏ qua mà không có cảnh báo.
Một service phân biệt lỗi nghiệp vụ HTTP 409 với lỗi máy chủ HTTP 503 không đúng, khiến thao tác xung đột dữ liệu bị retry như sự cố mạng tạm thời.
Đối tác trả HTTP 200 với body chứa mã lỗi riêng, nhưng lớp tích hợp Spring Boot chỉ dựa vào status code và ghi giao dịch đã hoàn tất dù đối tác chưa thực hiện.
Ứng dụng gọi API dùng ETag để đọc thông tin sản phẩm nhưng cache của HTTP client không xử lý phản hồi 304 phù hợp, làm giao diện báo rằng sản phẩm không tồn tại.
Một hệ thống gọi cùng API qua DNS có nhiều địa chỉ, một node đích ngừng phục vụ khiến lỗi xảy ra theo từng pod nhưng log chỉ ghi hostname chung.
Ứng dụng xác minh webhook từ đối tác trên HTTP endpoint nhưng bước parse JSON thay đổi biểu diễn nội dung trước khi kiểm tra chữ ký, khiến các request hợp lệ thường bị bác bỏ.
Gateway tích hợp theo request-response đợi đồng thời ba dịch vụ để lập báo giá; chỉ một đối tác chậm đã kéo dài thời gian phản hồi của toàn bộ endpoint vượt SLA.
Nhóm dùng WebClient để stream tệp dữ liệu từ nhà cung cấp nhưng consumer gom toàn bộ response vào RAM, khiến JVM hết bộ nhớ khi hai tệp lớn đến cùng lúc.
Một service gửi bearer token qua RestClient tới endpoint chuyển hướng sang host khác, nhưng luồng chuyển hướng chưa được kiểm tra giới hạn chuyển tiếp thông tin xác thực.
Ứng dụng xử lý retry ở cả tầng HTTP client và tầng service, khiến một yêu cầu lỗi được phát ra nhiều lần hơn giới hạn mà đội vận hành tính toán.
API tổng hợp nhận correlation ID từ gateway nhưng không truyền sang outbound HTTP request, khiến trace ở dịch vụ thanh toán không nối được với yêu cầu gốc.
Đội tích hợp dùng HTTP client đồng bộ bên trong @Async mà không giới hạn số tác vụ, khiến thread pool tăng hàng chờ và hệ thống trả lỗi khi đối tác mất kết nối.
Ứng dụng nhận dữ liệu thanh toán rồi lưu vào PostgreSQL qua Spring Data JPA trước khi gọi dịch vụ giao hàng; lỗi gọi HTTP khiến trạng thái giao dịch bị lệch giữa hai hệ thống.
Một transaction Spring Boot mở khi gọi API bên ngoài và giữ kết nối database trong suốt nhiều giây, khiến connection pool hết tài nguyên dưới tải cao.
Nhóm dùng @Transactional trên một phương thức nội bộ tự gọi trong cùng bean, dẫn tới đường xử lý thực tế không có transaction như đã kỳ vọng.
Dịch vụ cập nhật kho và ghi audit log trong hai transaction riêng; khi ghi log thất bại, dữ liệu tồn kho đã thay đổi nhưng không còn bằng chứng thay đổi.
Ứng dụng dùng optimistic locking khi xử lý cập nhật từ hai nguồn tích hợp nhưng không phân loại xung đột phiên bản, làm cả hai luồng retry liên tục và tăng tải database.
Job đồng bộ khách hàng thực hiện batch ghi hàng nghìn dòng trong một transaction dài; một record không hợp lệ khiến toàn bộ lô rollback và giữ khóa bảng quá lâu.
Một hệ thống nhận cùng sự kiện cập nhật đơn hàng từ broker hai lần nhưng entity không có khóa idempotency, khiến số lượng hàng dành riêng bị cộng hai lần.
Nhóm cấu hình read-only datasource cho báo cáo nhưng một luồng Spring Boot tái sử dụng nhầm nó để ghi trạng thái xử lý, khiến lỗi chỉ xuất hiện sau khi lên production.
Dịch vụ sử dụng hai DataSource cho hóa đơn và kho; nhóm phát triển nghĩ rằng @Transactional trên một service tự động đảm bảo commit đồng thời ở cả hai database.
Ứng dụng phát sinh ID giao dịch tại thời điểm ghi SQL nhưng lại publish message trước khi database commit, khiến consumer đọc một giao dịch chưa tồn tại ở nguồn.
Một luồng xử lý dùng Spring Data repository để cập nhật trạng thái đơn nhưng query đọc ở replica có replication lag, làm dữ liệu phản hồi ngay sau khi ghi vẫn là bản cũ.
Nhóm chuyển schema database trong một đợt rolling deployment nhưng phiên bản Spring Boot cũ vẫn chạy, khiến một số pod không đọc được bản ghi do pod mới tạo.
Ứng dụng lấy dữ liệu từ API bên ngoài và dùng upsert theo email người dùng, nhưng email có thể thay đổi; đồng bộ nhiều lần tạo ra các bản ghi khách hàng sai liên kết.
Một batch importer chuyển dữ liệu thời gian từ API thành LocalDateTime mà không giữ múi giờ, khiến hệ thống đối soát báo sai ngày giao dịch giữa các quốc gia.
Nhóm đọc dữ liệu theo từng trang từ REST API rồi ghi vào database, nhưng nguồn thay đổi thứ tự phân trang trong khi job chạy và một số hồ sơ bị bỏ sót.
Dịch vụ tạo hóa đơn ghi database thành công nhưng crash trước khi trả HTTP response; client thử lại và phát sinh bản ghi trùng vì không có mã yêu cầu ổn định.
Ứng dụng tích hợp legacy database có các cột nullable, nhưng mapping DTO yêu cầu giá trị không rỗng và dừng cả luồng khi gặp một bản ghi lịch sử thiếu thông tin.
Nhóm sử dụng connection pool chung cho truy vấn nghiệp vụ và job ETL, khiến batch đồng bộ dữ liệu chiếm hết connection và API thanh toán bị timeout.
Một hệ thống nhận xóa dữ liệu cá nhân từ CMS nhưng job đồng bộ chỉ thực hiện insert và update; người dùng đã yêu cầu xóa vẫn còn trong database tích hợp.
Ứng dụng ghi lịch sử trạng thái giao dịch theo event time nhưng đồng hồ các nguồn không đồng bộ, khiến bản cập nhật cũ ghi đè trạng thái đã được xác nhận mới.
Dịch vụ Spring Boot đặt cache Redis trước truy vấn thông tin sản phẩm, nhưng sau khi cập nhật giá ở database dữ liệu cũ vẫn được trả về trong vài phút.
Nhóm tích hợp cache phản hồi HTTP của nhà cung cấp theo mã sản phẩm nhưng không đưa vùng bán hàng vào cache key, làm khách ở hai thị trường thấy giá sai.
Một service dùng @Cacheable cho truy vấn thông tin khách nhưng cache key chỉ chứa ID nội bộ không có tenant, khiến dữ liệu của doanh nghiệp khác được trả về từ bộ nhớ đệm.
Đội đặt TTL cache rất dài để giảm truy vấn database nhưng không xét thời hạn hiệu lực của hợp đồng, khiến chatbot hỗ trợ sử dụng quy định đã bị thu hồi.
Ứng dụng dùng cache-aside cho trạng thái đơn hàng nhưng hai cập nhật gần nhau xóa cache không đúng thứ tự; bản ghi được nạp lại từ dữ liệu cũ khi replica trễ.
Một hệ thống Spring Boot dùng Redis làm cache chung và mất kết nối tạm thời, khiến toàn bộ API báo 500 dù dữ liệu gốc trong PostgreSQL vẫn còn sẵn.
Nhóm triển khai nhiều instance có local cache riêng mà không đồng bộ invalidation, khiến các khách hàng nhận số dư khả dụng khác nhau tùy pod.
Ứng dụng cache kết quả truy vấn có lỗi từ đối tác mà không phân biệt trạng thái, làm response lỗi tạm thời tiếp tục được phục vụ sau khi đối tác đã hồi phục.
Dịch vụ đọc 10 nghìn bản ghi từ cache khi TTL hết cùng lúc; các request đồng thời cùng tải lại từ database làm connection pool bão hòa.
Một ứng dụng cập nhật database trong transaction nhưng @CacheEvict xảy ra trước khi commit; khi transaction rollback, cache vẫn bị xóa không cần thiết và gây tải đột biến.
Nhóm triển khai @CachePut sau khi ghi dữ liệu nhưng lưu DTO khác với kiểu @Cacheable đọc, khiến lỗi ép kiểu chỉ xuất hiện khi request đi qua cache hit.
Dịch vụ đồng bộ dữ liệu từ hệ thống lõi vào Redis nhưng không giữ version của bản ghi, khiến một sự kiện đến trễ ghi đè thông tin mới.
Ứng dụng lưu token OAuth của đối tác trong cache chia sẻ nhưng không tách khóa theo tài khoản tích hợp, làm một đối tác gửi request bằng token của đối tác khác.
Nhóm dùng Redis làm nơi lưu trạng thái tiến trình đồng bộ nhưng cấu hình eviction như cache thông thường, khiến job dài ngày mất checkpoint và xử lý lại dữ liệu.
Một service ghi cache trước khi ghi database để giảm độ trễ, nhưng lần cập nhật database thất bại và giao diện tiếp tục hiển thị trạng thái chưa từng được lưu.
Đội muốn dùng cache cho bảng danh mục ít thay đổi nhưng dữ liệu chứa quyền xem theo vai trò; câu trả lời từ cache thiếu kiểm tra quyền của người hỏi.
Ứng dụng dùng Redis pub/sub để báo các bản ghi cần invalidation, nhưng khi một pod mất kết nối nó bỏ lỡ sự kiện và tiếp tục phục vụ dữ liệu cũ.
Nhóm quan sát cache hit rate cao nhưng người dùng thường nhận thông tin tồn kho sai; dashboard chưa đo độ cũ của dữ liệu và tỷ lệ invalidation lỗi.
Một cache cluster được chuyển vùng, khóa lưu ở vùng cũ không được di trú; ứng dụng Spring Boot tăng lượng truy vấn nguồn và p99 response tăng mạnh sau triển khai.
Nhóm bật serialization mới cho Redis cache trong bản phát hành nhưng chưa dọn dữ liệu định dạng cũ; các pod mới không đọc được một phần cache tồn.
Ứng dụng phát sự kiện OrderCreated tới RabbitMQ bằng RabbitTemplate ngay sau lưu đơn; broker mất kết nối khiến đơn có trong database nhưng hệ thống giao hàng không nhận lệnh.
Một producer Spring Boot dùng publisher confirm để biết broker nhận message nhưng bộ phận nghiệp vụ lại xem confirm là bằng chứng kho hàng đã xử lý sự kiện.
Dịch vụ đọc event từ @RabbitListener và ghi database nhưng ACK trước commit; khi SQL lỗi, message biến mất khỏi queue mà không có bản ghi đích.
Nhóm listener xử lý thông điệp thanh toán nhận redelivery sau khi ghi DB và trước ACK, khiến cùng lệnh tạo hai giao dịch vì thiếu cơ chế dedup.
Một queue RabbitMQ dùng binding pattern quá rộng cho cả thông báo thử nghiệm và giao dịch thật, khiến consumer nghiệp vụ phải xử lý những loại sự kiện chưa hỗ trợ.
Ứng dụng sử dụng retry vô hạn cho @RabbitListener khi gặp JSON hỏng, làm message độc lặp qua các consumer liên tục và giữ backlog tăng.
Dịch vụ đẩy lỗi vào DLQ sau nhiều lần retry nhưng không giữ message ID và nguyên nhân lỗi, khiến đội trực không biết bản tin nào có thể replay an toàn.
Một service chuyển từ RabbitMQ classic queue sang quorum queue nhưng cấu hình khai báo queue còn thuộc tính cũ, khiến ứng dụng không khởi động được trong production.
Nhóm đặt prefetch lớn cho listener chạy tác vụ gọi HTTP chậm, làm một pod giữ nhiều message chưa ACK trong khi các pod khác không có việc.
Ứng dụng Spring Boot vừa lắng nghe Kafka vừa ghi PostgreSQL; consumer commit offset trước khi transaction DB hoàn thành nên mất dữ liệu sau một lần crash.
Một Kafka consumer xử lý message và thực hiện side effect qua API ngoài; khi rebalance và redelivery xảy ra, đối tác nhận cùng lệnh hai lần.
Nhóm tăng concurrency cho Kafka listener nhưng các sự kiện cùng orderId bị phân vào partition không ổn định theo producer, khiến cập nhật mất thứ tự.
Dịch vụ dùng Kafka topic chung cho nhiều phiên bản event nhưng consumer Spring Boot không kiểm tra schema version, làm một trường mới được diễn giải sai ở bản cũ.
Ứng dụng phát đồng thời message sang Kafka và RabbitMQ rồi đánh dấu giao dịch hoàn tất khi một broker thành công, khiến các hệ thống downstream nhận trạng thái khác nhau.
Nhóm dùng một phương thức @KafkaListener có xử lý blocking lâu trong lúc broker có rebalance, khiến một phần batch được giao lại dù đã tạo tác động nghiệp vụ.
Ứng dụng đồng bộ catalog bằng Kafka compacted topic nhưng không xử lý tombstone; các sản phẩm đã xóa ở nguồn vẫn hiện trong hệ thống đích.
Đội triển khai dead-letter topic cho Kafka mà không lưu nguồn partition và offset tương ứng; khi sửa lỗi, quá trình replay không đảm bảo đúng dữ liệu cần làm lại.
Một HTTP API nhận yêu cầu nhập hàng rồi phát command qua broker nhưng trả kết quả 'hoàn tất' trước khi consumer xử lý, gây kỳ vọng sai về trạng thái tác vụ.
Nhóm chuyển từ gọi HTTP trực tiếp sang xử lý bất đồng bộ qua RabbitMQ nhưng không có trạng thái tác vụ và correlation ID; khách không biết khi nào công việc hoàn thành.
Ứng dụng tích hợp email gửi thông báo qua hàng đợi nhưng listener tự gửi lại khi timeout; nhà cung cấp đã chấp nhận email khiến khách nhận bản sao.
Một broker ngừng hoạt động giữa giờ cao điểm và producer Spring Boot tiếp tục nhận yêu cầu mới nhưng không có nơi lưu bền vững; những tác vụ chưa publish bị mất khi pod restart.
Dịch vụ phát dữ liệu hành vi lên Kafka nhưng payload chứa thông tin cá nhân không được phân loại; nhóm analytics có thể đọc thông tin vượt phạm vi quyền.
Nhóm Spring Boot đặt retry cho mọi lỗi từ broker mà không giới hạn backoff, gây nhiều luồng reconnect cùng lúc và quá tải broker vừa phục hồi.
Ứng dụng dùng Kafka để đồng bộ số dư nhưng key message lấy từ một ID biến đổi giữa các phiên bản, làm cùng tài khoản không còn giữ thứ tự trong một partition.
Đội nhận cảnh báo backlog RabbitMQ tăng nhưng dashboard chỉ theo dõi ready queue mà không tính unacked; nhiều đơn bị kẹt trong listener mà không được phát hiện.
Một ứng dụng xây IntegrationFlow để chuyển thông điệp từ REST endpoint vào DirectChannel, nhưng một handler gọi dịch vụ chậm làm thread HTTP bị giữ quá SLA.
Nhóm đổi từ DirectChannel sang ExecutorChannel để tách xử lý khỏi request, nhưng vẫn dùng giả định rằng exception của handler sẽ quay lại caller đồng bộ.
Ứng dụng đặt QueueChannel làm vùng đệm trước khi ghi dữ liệu, nhưng không có chính sách giới hạn kích thước; khi database lỗi lâu, bộ nhớ của JVM tăng không dừng.
Một IntegrationFlow dùng PublishSubscribeChannel để gửi cùng event tới hai handler độc lập, nhưng nhóm nghiệp vụ tưởng hai handler sẽ thay nhau xử lý để giảm tải.
Dịch vụ sử dụng MessageChannel chung cho các tác vụ có mức bảo mật khác nhau nhưng không kiểm soát loại message, khiến một payload nội bộ được gửi sang handler đối tác.
Nhóm tạo IntegrationFlow bằng Java DSL và khởi tạo một adapter mới sau mỗi lần người dùng kết nối, nhưng không quản lý vòng đời component nên số poller tăng liên tục.
Một Service Activator nhận payload chứa nhiều phiên bản DTO nhưng xác định handler dựa vào kiểu runtime không đúng, khiến một loại sự kiện hợp lệ bị từ chối.
Ứng dụng Spring Integration sử dụng Filter để loại các đơn không hợp lệ nhưng không có cơ chế báo lỗi hay lưu dấu; khách hàng không biết vì sao đơn biến mất.
Nhóm thiết kế Router dựa trên header region nhưng producer mới không gắn header, làm message đi vào default route không dành cho vùng của khách.
Một flow dùng Header Enricher thêm tenantId từ dữ liệu request không được xác minh; downstream tin vào header và ghi thông tin sang vùng dữ liệu sai.
Ứng dụng nối hai luồng qua BridgeHandler, nhưng một channel có executor khác và nhóm vận hành không tính tới thứ tự xử lý hoặc thời điểm transaction kết thúc.
Một Transformer chuyển CSV thành JSON trước khi gửi sang API; một dòng CSV chứa dấu phẩy trong chuỗi khiến trường địa chỉ bị lệch mà không báo lỗi rõ ràng.
Nhóm tích hợp dùng Splitter để phát mỗi dòng hóa đơn thành một message, nhưng khi một dòng thất bại không có thông tin về tập gốc để đối soát.
Một Aggregator chờ đủ các phản hồi của nhà cung cấp, nhưng một nhánh không gửi được event; group lưu mãi khiến bộ nhớ và message store tăng theo thời gian.
Ứng dụng dùng correlation key sai cho Aggregator nên phản hồi của hai yêu cầu cùng khách nhưng khác đơn hàng bị ghép vào một kết quả.
Nhóm tích hợp đặt release strategy cho Aggregator theo số nhánh cố định, nhưng một loại giao dịch chỉ gọi hai đối tác thay vì ba nên không bao giờ phát kết quả.
Một flow dùng Resequencer để sắp theo sequence number nhưng producer có lúc không phát số thứ tự tiếp theo; các message đến sau bị chờ lâu mà không có cảnh báo.
Ứng dụng dùng Scatter-Gather gọi nhiều nhà cung cấp qua message channels, nhưng một timeout downstream làm kết quả tổng hợp mất bối cảnh nhà cung cấp đã thành công.
Dịch vụ tạo Request-Reply gateway với reply channel chung nhưng không giữ correlation ID nhất quán; phản hồi của hai yêu cầu gần nhau bị ghép nhầm.
Nhóm cấu hình Messaging Gateway cho tác vụ chậm nhưng caller HTTP vẫn chờ vô hạn vì không có quy tắc reply timeout phù hợp.
Một integration flow gửi message tới channel không có subscriber sau khi đổi profile Spring, khiến lỗi chỉ xuất hiện khi nhận giao dịch production đầu tiên.
Ứng dụng cấu hình errorChannel chung cho mọi luồng tích hợp nhưng không giữ ID và nguồn message; đội trực không phân biệt được lỗi của hệ thống hóa đơn hay kho.
Nhóm xử lý ErrorMessage bằng cách ghi log và bỏ qua, khiến các command quan trọng mất dấu mà hệ thống giám sát vẫn báo flow chạy bình thường.
Một IntegrationFlow dùng Poller đọc dữ liệu từ queue nội bộ với fixed delay rất ngắn; khi downstream chậm, các lần poll tạo áp lực tài nguyên không cần thiết.
Dịch vụ sử dụng persistent MessageStore cho các nhóm aggregator nhưng không kiểm thử phục hồi sau restart; một phần dữ liệu nhóm đang chờ không còn khớp phiên mới.
Một flow Spring Integration xử lý chuyển đổi tệp với nhiều step bất đồng bộ, nhưng ngữ cảnh trace không được truyền qua MessageHeaders nên khó lần ra chỗ lỗi.
Ứng dụng sử dụng claim-check để lưu payload lớn ngoài flow nhưng vùng lưu tạm bị dọn quá sớm; handler phía sau không thể lấy lại nội dung cần xử lý.
Nhóm dùng SFTP inbound adapter để nhận báo cáo từ đối tác, nhưng tệp đang upload dở đã được poll và parse nên bản ghi cuối bị thiếu.
Một hệ thống đồng bộ file qua SFTP tái tải toàn bộ tệp mỗi lần poll vì không ghi dấu trạng thái; cùng một giao dịch xuất hiện nhiều lần trong database.
Nhóm cấu hình SFTP outbound adapter dùng tên file cố định, khiến hai job chạy đồng thời ghi đè tệp chuyển giao của nhau trên server đối tác.
Một File inbound adapter theo dõi thư mục trao đổi nhưng file filter chỉ xét tên; đối tác thay nội dung giữ nguyên tên nên bản mới không được nhập.
Ứng dụng dùng FTP adapter để truyền dữ liệu nhạy cảm qua mạng bên thứ ba; nhóm bảo mật phát hiện kết nối không đáp ứng yêu cầu bảo vệ nội dung khi truyền.
Service nhận thư điện tử bằng Mail inbound adapter rồi gửi dữ liệu vào message channel, nhưng khi xử lý thất bại và quét lại inbox, cùng email được nhập hai lần.
Một hệ thống gửi email báo cáo từ Spring Integration nhưng nhà cung cấp SMTP chấp nhận message rồi ngắt kết nối; ứng dụng không biết thông báo đã đến hay chưa.
Nhóm dùng JDBC inbound adapter để poll các bản ghi trạng thái NEW, nhưng hai instance cùng đọc một batch trước khi thay trạng thái nên tác vụ được xử lý trùng.
Ứng dụng dùng JDBC outbound adapter để ghi dữ liệu nhưng luồng nghiệp vụ ở phía trên đã coi message hoàn tất trước khi transaction DB commit, làm sai báo cáo kết quả.
Một flow xử lý dữ liệu qua JMS inbound adapter nhưng ack của session và transaction nguồn không được đồng bộ; sau crash xuất hiện những bản tin được xử lý lại.
Nhóm dùng HTTP inbound gateway trong Spring Integration để tiếp nhận webhook đối tác, nhưng handler nghiệp vụ rất lâu khiến đối tác retry trước khi nhận phản hồi.
Ứng dụng dùng HTTP outbound gateway để gọi hệ thống lõi nhưng hệ thống đích trả lỗi ở body với status thành công; message tiếp tục qua channel hoàn tất dù nghiệp vụ thất bại.
Một MQTT inbound adapter đưa dữ liệu cảm biến vào hệ thống Spring Boot, nhưng các bản tin đến trễ không mang version nên trạng thái đo mới bị ghi đè bằng giá trị cũ.
Nhóm gửi thông báo qua MQTT outbound adapter và giả định mọi subscriber đều nhận đúng một lần; sau reconnect một số thiết bị áp dụng cấu hình hai lần.
Ứng dụng polling S3 bucket bằng adapter tự viết nhưng không bảo toàn ID đối tượng đã xử lý; sau khi có nhiều bản cùng tên, dữ liệu mới bị bỏ sót.
Một hệ thống tích hợp nguồn REST và file SFTP vào cùng flow nhưng định dạng ngày giờ khác nhau; các bước xử lý hợp nhất ghi sai ngày hạch toán.
Nhóm dùng webhook inbound adapter để nhận sự kiện chuyển trạng thái, nhưng endpoint public không xác thực nguồn nên bản tin giả vẫn được đưa vào message channel.
Ứng dụng gửi file ra SFTP sau khi ghi database nhưng lần upload mất kết nối khi server đã nhận đủ tệp; thao tác retry tạo hai phiên bản dữ liệu cùng kỳ.
Một adapter đọc tệp lớn rồi tạo message chứa toàn bộ nội dung trong RAM; khi nhiều báo cáo hàng GB đến cùng lúc, JVM hết bộ nhớ trước khi Transformer chạy.
Dịch vụ tích hợp định kỳ polling API và SFTP với nhiều scheduler, nhưng các đợt đồng bộ cùng dữ liệu diễn ra chồng nhau gây xung đột trạng thái.
Nhóm chuyển một flow nội bộ sang event-driven adapter nhưng không điều chỉnh cơ chế xử lý áp lực ngược, khiến adapter tiếp tục nhận dữ liệu nhanh hơn tốc độ database ghi.
Ứng dụng nhận thông điệp từ đối tác qua HTTPS và lưu trên queue, nhưng không kiểm tra chứng chỉ client phù hợp; các tài khoản hợp lệ có thể giả danh nhau.
Một service có cấu hình URL, token và timeout khác nhau cho staging/production nhưng sử dụng chung bean RestClient, khiến traffic production đôi lúc gọi nhầm endpoint thử nghiệm.
Nhóm lưu secret tích hợp trong application.yml đóng gói vào JAR, khiến tài khoản đối tác bị lộ khi bản build được chia sẻ cho nhiều đội.
Ứng dụng xoay vòng credential RabbitMQ nhưng một số listener giữ kết nối cũ và pod mới dùng credential mới, gây lỗi tiêu thụ message không đồng đều sau rollout.
Một hệ thống tích hợp ba nhà cung cấp với cùng tên property cho API key, nhưng cách ưu tiên cấu hình giữa các profile làm khóa của đối tác A được gửi sang đối tác B.
Nhóm cấu hình TLS truststore cho HTTP client nhưng chỉ trên máy local, khiến container production không tin chuỗi chứng chỉ của nhà cung cấp.
Ứng dụng đăng ký converter JSON toàn cục cho cả API HTTP và broker message, nhưng yêu cầu tương thích schema của hai hệ thống khác nhau khiến một bản nâng cấp phá vỡ consumer cũ.
Một service truyền trường amount ở kiểu số thực qua HTTP và message broker, dẫn tới sai số khi downstream đối soát hóa đơn có nhiều loại tiền tệ.
Nhóm đổi tên trường customerId trong DTO tích hợp mà không công bố phiên bản hợp đồng; một hệ thống đích vẫn dùng tên cũ và liên kết nhầm tài khoản.
Ứng dụng tiếp nhận chuỗi enum trạng thái mới của đối tác, nhưng deserializer Java chỉ hỗ trợ các giá trị cũ nên toàn bộ batch bị dừng ở bản ghi đầu tiên.
Nhóm triển khai hợp đồng schema Kafka mới cho sự kiện hóa đơn nhưng không kiểm tra tính tương thích với consumer đang chạy, khiến dữ liệu mới được publish mà không có ai xử lý.
Một đối tác bổ sung trường optional trong JSON nhưng service Spring Boot bật quy tắc reject trường không biết, làm phản hồi hợp lệ bị coi là sai định dạng.
Dịch vụ dùng cả REST API và RabbitMQ cho cùng đối tượng đơn hàng nhưng hai loại message sử dụng các mã trạng thái khác nhau, khiến kết quả hợp nhất không thể đối soát.
Ứng dụng nhận thời gian sự kiện có offset từ API nhưng phát sang broker dưới dạng chuỗi không múi giờ, làm các hệ thống khu vực sắp xếp sự kiện sai thứ tự.
Một service ghi metadata schemaVersion vào header message nhưng khi retry bằng DLQ lại mất header, khiến consumer mới không chọn được bộ chuyển đổi đúng.
Nhóm phân quyền endpoint inbound HTTP nhưng các message từ broker được xử lý bằng tenantId trong payload không kiểm chứng, tạo đường truy cập gián tiếp vào dữ liệu tenant khác.
Một ứng dụng có adapter nhập dữ liệu từ SFTP nội bộ nhưng file chứa ký tự điều khiển không hợp lệ; parser tạo message sai mà không giữ được tệp nguồn để điều tra.
Nhóm xử lý file CSV theo định dạng dấu phân cách cũ trong khi nhà cung cấp chuyển sang tab; một phần dữ liệu địa chỉ bị ánh xạ sai nhưng vẫn qua bước kiểm tra đơn giản.
Ứng dụng dùng cùng DTO nội bộ làm hợp đồng public API; khi refactor entity database, cấu trúc payload gửi cho đối tác vô tình thay đổi theo.
Một nhà cung cấp yêu cầu idempotency key khi gọi API thanh toán nhưng adapter Spring Boot tạo khóa mới trên mỗi retry, khiến yêu cầu lặp không được khử.
Dịch vụ tổng hợp dữ liệu khách từ ba hệ thống nhưng không có khóa định danh toàn cục; một khách xuất hiện thành nhiều hồ sơ khi tên được viết khác nhau.
Nhóm chạy quy trình tạo đơn qua database, HTTP thanh toán và RabbitMQ giao hàng nhưng không có cách xác định trạng thái khi bước hai thất bại sau bước một.
Một hệ thống dùng @Transactional bao quanh luồng gọi REST, Redis và PostgreSQL rồi kỳ vọng ba nguồn cùng rollback khi một adapter trả lỗi.
Ứng dụng ghi đơn hàng và outbox event trong cùng database transaction nhưng job phát message bị crash sau gửi; bản ghi outbox còn NEW khiến event được phát thêm lần nữa.
Nhóm consumer xử lý OrderCreated và lưu ID đã xử lý trong một transaction riêng; khi pod chết giữa cập nhật đơn và lưu ID, redelivery làm tạo phiếu giao hàng trùng.
Dịch vụ phối hợp thanh toán và hoàn tiền bằng sự kiện nhưng không giữ ID quy trình dài hạn; khi một bước lỗi, đội vận hành không ghép được những message của cùng giao dịch.
Ứng dụng gọi ba đối tác và gộp kết quả qua Aggregator nhưng không có deadline nghiệp vụ; một request cũ không đầy đủ giữ tài nguyên nhiều giờ.
Nhóm dùng saga cho quy trình đặt vé nhưng một bước bù hoàn tiền bị lỗi tạm thời; trạng thái giao dịch vẫn được đánh dấu CANCELLED trước khi tác vụ bù thành công.
Một luồng cập nhật tồn kho từ Kafka và HTTP webhook cùng ghi bản ghi sản phẩm; event cũ đến sau làm giá trị mới bị ghi đè vì không có version check.
Ứng dụng tự retry khi Redis mất kết nối trong bước cập nhật trạng thái tác vụ, nhưng API thanh toán đã hoàn tất khiến lần retry tạo giao dịch tài chính mới.
Nhóm phân loại mọi lỗi tích hợp là có thể thử lại; lỗi 400 do payload sai được gửi lại liên tục và giữ tài nguyên của hàng đợi.
Ứng dụng bật retry tại broker, service Spring Boot và HTTP client đồng thời; một tác vụ thất bại ở đối tác tạo số lần gọi lớn hơn nhiều so với chính sách vận hành.
Một hệ thống cần bảo đảm thứ tự thay đổi hồ sơ khách nhưng cập nhật từ hai channel chạy trên các executor khác nhau, khiến trạng thái cuối không phản ánh phiên bản mới nhất.
Nhóm giới hạn message retry trong DLQ nhưng nhân viên vận hành phát lại mọi bản tin sau sửa lỗi; những message từng có side effect một phần được xử lý lần nữa.
Ứng dụng phân biệt lỗi tạm thời và lỗi dữ liệu tại service nhưng errorChannel gom chung mà không lưu mã phân loại, khiến công cụ replay không biết bản tin nào an toàn.
Đội triển khai bulkhead cho HTTP client đối tác chậm nhưng không tách pool connection của luồng batch; các request giao dịch quan trọng vẫn phải chờ tài nguyên.
Một service dùng circuit breaker để giảm lỗi dây chuyền khi nhà cung cấp mất mạng, nhưng bảng trạng thái nghiệp vụ vẫn ghi nhận các request bị từ chối như đã được xử lý.
Nhóm triển khai rate limiter cho API đồng bộ nhưng consumer từ RabbitMQ không bị giới hạn tương ứng, làm cơ sở dữ liệu downstream vẫn quá tải.
Ứng dụng tích hợp giữ thông tin người dùng trong ThreadLocal, nhưng xử lý chuyển từ servlet thread sang ExecutorChannel khiến log và kiểm tra quyền mang sai ngữ cảnh.
Một webhook nhận event từ đối tác nhiều lần trong quá trình retry, nhưng hệ thống nguồn không cung cấp message ID ổn định; service chưa có tiêu chí phát hiện cùng sự kiện.
Nhóm xử lý lệnh từ HTTP và Kafka bằng hai đường code riêng, một đường có kiểm soát idempotency còn đường kia không; tác vụ đi từ Kafka có thể chạy trùng.
Ứng dụng lưu dấu quy trình tích hợp chỉ khi toàn bộ bước thành công, làm những giao dịch thất bại nửa chừng không có checkpoint để phục hồi sau crash.
Dịch vụ Spring Boot ghi ACK message khi một luồng xử lý async còn đang chạy; pod bị shutdown giữa chừng và broker không còn bản tin để phát lại.
Một hệ thống nhận file SFTP sau 23 giờ nhưng lịch đối soát theo UTC đóng sổ trước khi file đến; dữ liệu giao dịch của một ngày bị hạch toán sang ngày kế.
Nhóm triển khai timeout toàn quy trình ngắn hơn thời gian retry hợp lệ của broker; khách bị báo lỗi cuối cùng trong khi tác vụ vẫn chạy và có thể hoàn tất sau đó.
Một service dùng OAuth client credentials để gọi đối tác nhưng cache token không phân biệt scope, khiến thao tác ghi nhận được token chỉ có quyền đọc.
Ứng dụng kết nối tới ba nguồn dữ liệu qua các account dùng chung quyền quản trị; một credential bị lộ cho phép truy cập quá phạm vi của adapter bị ảnh hưởng.
Nhóm tích hợp nhận webhook HTTP qua gateway nhưng không xác minh chữ ký hoặc chống phát lại theo timestamp; bản tin bị thu thập trước đó có thể kích hoạt lại nghiệp vụ.
Đội triển khai policy phân quyền đọc file SFTP theo thư mục nhưng một adapter dùng tài khoản có quyền root, làm tệp của khách hàng khác có thể được nhập nhầm.
Ứng dụng ghi log toàn bộ body HTTP response và payload Kafka để debug, khiến dữ liệu cá nhân từ nhiều hệ thống được lưu lại trong nền tảng log tập trung.
Nhóm chuyển môi trường Spring Boot từ secret tĩnh sang secret manager nhưng connector khởi tạo trước khi secret sẵn sàng; pod không phục hồi kết nối dù secret được cấp sau đó.
Một luồng gửi thông tin nhạy cảm qua RabbitMQ nội bộ nhưng tenant được xác định từ header do bên gửi điền; consumer không xác thực nguồn và lưu dữ liệu sai tenant.
Ứng dụng nhận tài liệu từ file adapter để gọi API OCR bên thứ ba nhưng chưa phân loại tài liệu chứa thông tin cá nhân, tạo rủi ro gửi dữ liệu ra ngoài vùng được phép.
Nhóm xây endpoint điều khiển replay DLQ chỉ dựa trên vai trò vận hành chung; một nhân viên không phụ trách thanh toán có thể phát lại lệnh hoàn tiền.
Ứng dụng thêm trace ID vào message headers nhưng header chứa cả email khách hàng; hệ thống observability lưu và hiển thị định danh nhạy cảm dưới dạng nhãn.
Một API inbound yêu cầu mTLS nhưng outbound HTTP client không xác minh hostname đối tác, khiến kết nối mạng được mã hóa mà danh tính phía xa không được bảo đảm.
Nhóm đồng bộ dữ liệu y tế bằng các IntegrationFlow có khả năng fan-out, nhưng một nhánh gửi đến hệ thống analytics không được phép tiếp nhận thông tin nhạy cảm.
Dịch vụ tích hợp sử dụng feature flag để thay provider thanh toán nhưng config từ staging bị nạp vào pod production, khiến giao dịch thật được gửi sang sandbox.
Ứng dụng cho phép thay đổi routing bằng configuration server nhưng không lưu lịch sử người sửa; sau một sự cố dữ liệu đi sai tuyến, nhóm không thể tìm nguyên nhân.
Đội triển khai adapter quản trị với endpoint HTTP nội bộ nhưng reverse proxy mở nó ra internet, tạo khả năng gọi lại các luồng xử lý batch không có xác thực mạnh.
Một hệ thống phải xóa thông tin khách theo yêu cầu nhưng dữ liệu còn tồn trong Kafka compacted topic, cache Redis và DLQ dù database nguồn đã xóa.
Nhóm chia sẻ một encryption key giữa file adapter và message broker cho nhiều tenant; sự cố lộ khóa của một tenant ảnh hưởng khả năng bảo vệ dữ liệu tenant khác.
Ứng dụng gắn request ID mới ở mỗi bước HTTP, queue và database thay vì truyền correlation ID, khiến sự cố chỉ có thể điều tra bằng thời điểm log gần đúng.
Nhóm theo dõi HTTP status của gateway nhưng không đo thời gian message chờ trong RabbitMQ; khách hàng bị chậm xử lý hàng giờ dù latency API vẫn thấp.
Một IntegrationFlow xử lý hàng nghìn file mỗi ngày nhưng dashboard chỉ có counter tệp nhập; các file bị lỗi parse không xuất hiện trong số liệu hoàn tất.
Đội vận hành bật metric cho số lượng message gửi nhưng không đối chiếu ACK hoặc DLQ, khiến tỷ lệ giao nhận được báo cao hơn khả năng xử lý thực.
Ứng dụng ghi metric theo orderId trong tag để truy vết từng lệnh, làm số lượng series Micrometer/Prometheus tăng nhanh đến mức dashboard mất ổn định.
Nhóm dùng một tên metric cho cả số lần gọi HTTP và số sự kiện Kafka mà không có nhãn nguồn rõ ràng, khiến báo cáo tải giữa hai hệ thống bị gộp sai.
Một service có retry thành công sau vài phút nhưng chỉ đo latency cuối của consumer, không tính thời gian từ khi người dùng gửi lệnh đến lúc tác vụ hoàn tất.
Nhóm xây trace xuyên Spring Integration channels nhưng không chuyển context qua executor, khiến nhiều span bị tách thành những transaction không liên quan.
Ứng dụng giám sát database connection và Redis cache tốt nhưng không theo dõi rate của API đối tác; các đợt lỗi 429 bị nhầm thành chậm truy vấn nội bộ.
Một hệ thống báo health UP khi HTTP API còn sống nhưng SFTP adapter không thể xác thực và không nhận file trong hai ngày; bộ phận hỗ trợ chỉ biết khi khách khiếu nại.
Nhóm xây readiness phụ thuộc Kafka broker ở xa, khiến mọi pod đồng loạt bị loại khỏi tải khi broker tạm gián đoạn dù một số endpoint HTTP độc lập vẫn phục vụ được.
Ứng dụng không log schema version và message ID của lỗi chuyển đổi trong message converter; sau deploy đội trực không biết bản tin nào thuộc hợp đồng cũ.
Đội triển khai nhiều instance job đồng bộ SFTP nhưng không ghi instance ID và checksum nguồn; sau sự cố trùng dữ liệu không xác định được pod nào nhập tệp.
Một service gom response từ ba hệ thống qua Aggregator, nhưng log chỉ lưu kết quả cuối không có trạng thái từng nhánh; khi một nhà cung cấp timeout, khó xác định điểm nghẽn.
Nhóm kiểm thử RestClient bằng mock toàn bộ response 200, nên không phát hiện mapping sai của lỗi 409, 429 hoặc response body chứa mã nghiệp vụ thất bại.
Một bộ integration test dùng PostgreSQL giả lập nhưng production có isolation level khác; các cập nhật cùng orderId bị mất dưới tải dù kiểm thử tuần tự đều PASS.
Đội QA dùng fake cache luôn trả hit, không mô phỏng stale data hoặc Redis disconnect; khi cache production lỗi, API thất bại toàn bộ thay vì thể hiện khả năng suy giảm chức năng.
Nhóm kiểm thử @RabbitListener với một consumer duy nhất nhưng production có nhiều consumer; lỗi cạnh tranh ghi số dư chỉ xuất hiện sau autoscale.
Một bài test Kafka consumer chỉ xác minh payload hợp lệ được xử lý mà không thử redelivery sau khi DB commit nhưng trước offset commit; duplicate side effect lọt lên production.
Ứng dụng kiểm thử một IntegrationFlow bằng DirectChannel đồng bộ nhưng production dùng ExecutorChannel; kết quả test không thể tái hiện thứ tự và xử lý exception thực tế.
Nhóm thử Aggregator với tất cả phản hồi đến đủ, nhưng chưa mô phỏng một nhánh chậm vô hạn; message group tồn và mức sử dụng memory tăng trong môi trường thật.
Một bài test file inbound adapter tạo tệp đã hoàn chỉnh ngay lập tức, nhưng production nhận file qua upload chậm; parser đọc tệp chưa xong và gây thiếu bản ghi.
Đội dùng Testcontainers để chạy RabbitMQ và PostgreSQL nhưng không tái tạo cấu hình DLQ và transaction thật; kịch bản lỗi message độc không được phát hiện ở CI.
Nhóm chỉ đánh giá throughput của Spring Boot integration flow bằng payload nhỏ, nhưng tài liệu PDF production lớn làm cả broker và heap JVM vượt ngân sách.
Một kịch bản QA giả lập lỗi HTTP giữa bước gọi thanh toán và lưu kết quả nhưng chỉ kiểm tra response cuối; sau retry hệ thống có giao dịch trùng mà test không phát hiện.
Ứng dụng chuyển REST API của đối tác sang phiên bản mới nhưng contract test chỉ kiểm tra trường bắt buộc hiện tại; consumer cũ vẫn thất bại với trường enum mới.
Nhóm nâng Spring Boot và Spring Integration trong cùng bản phát hành nhưng không kiểm tra converter, poller và lifecycle adapters trên môi trường staging, làm một luồng nhập liệu ngừng chạy.
Đội kiểm thử failover broker khi queue rỗng nhưng không thử trong lúc có hàng nghìn message unacked, khiến quy trình phục hồi tạo side effect trùng ngoài dự kiến.
Một bài test rollback database khi HTTP gọi đối tác bị timeout nhưng không kiểm tra trạng thái thực tế ở đối tác; cùng lệnh nghiệp vụ có thể đã được thực hiện phía xa.
Nhóm kiểm thử restart pod trong lúc job SFTP xử lý tệp lớn, nhưng không xác nhận file checksum và checkpoint sau khôi phục; bản ghi ở cuối tệp bị thiếu.
Ứng dụng dùng feature flag để chuyển một số tenant từ RabbitMQ sang Kafka, nhưng bài test chỉ kiểm tra tuyến mới và không đo duplicate giữa hai tuyến khi rollout.
Đội QA thử quyền truy cập REST endpoint nhưng bỏ qua payload từ message broker; bản tin có tenantId giả được listener nhận và ghi sang bảng dữ liệu sai phạm vi.
Nhóm triển khai polling adapter theo lịch giờ địa phương nhưng CI chạy UTC; các bài test quanh thời điểm chuyển ngày không phát hiện được dữ liệu bị ghi sai kỳ.
Một dịch vụ có nhiều route tích hợp theo profile nhưng pipeline chỉ chạy profile mặc định; production thiếu bean IntegrationFlow của một adapter quan trọng và không nhận sự kiện.
Đội đo thời gian hoàn tất quy trình dưới tải thấp nhưng không theo dõi backlog và kết nối pool khi đối tác chậm; sau triển khai SLA end-to-end không còn đạt.
Một hệ thống tích hợp thành công trong giai đoạn canary nhưng không giữ trace theo build version; khi mở rộng rollout, tỷ lệ lỗi tăng mà đội trực không xác định được phiên bản gây ra.
Nhóm di trú dữ liệu từ hệ thống cũ sang flow Spring Boot mới nhưng chạy song song hai pipeline nhập liệu một thời gian; mỗi hệ thống tự coi mình là nguồn chuẩn và sinh bản ghi trùng.
Đội vận hành cần khôi phục các message lỗi sau deploy nhưng bảng dedup đã được dọn trước khi replay DLQ; những sự kiện cũ có thể làm thay đổi dữ liệu tài chính lần nữa.
Một ứng dụng tổng hợp nhiều nguồn HTTP, database và broker nhưng không có ID quy trình thống nhất trong API, message và audit log; khi có khiếu nại không thể tái dựng chuỗi xử lý.
Một doanh nghiệp yêu cầu giới hạn thời gian giữ dữ liệu khách trong cache, DLQ và tệp SFTP tạm nhưng mỗi adapter dùng cơ chế dọn khác nhau; dữ liệu cũ tồn tại ngoài chính sách.
Một Spring Boot integration service khởi động với health UP nhưng chưa nối được tới broker và không poll được SFTP; bộ phận vận hành không có tín hiệu phân biệt thành phần lỗi.
Một đợt deploy rolling có cả producer schema cũ và consumer schema mới cùng chạy; các message không tương thích bị gửi vào DLQ trong khi dashboard API vẫn cho thấy giao dịch thành công.
Nhóm phát triển tối ưu việc đồng bộ bằng cách tăng đồng thời prefetch, số poller và số HTTP connection, nhưng downstream database không tăng công suất khiến tổng độ trễ còn tệ hơn.
Ứng dụng cần audit quy trình tạo đơn từ HTTP đến RabbitMQ, PostgreSQL và cache Redis nhưng chỉ có thời điểm của từng hệ thống với clock khác nhau; thứ tự sự kiện khó kiểm chứng.
