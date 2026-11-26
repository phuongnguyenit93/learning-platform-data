Một dịch vụ bán hàng dùng Spring AMQP RabbitTemplate gửi sự kiện đặt hàng tới direct exchange, nhưng routing key từ bản phát hành mới không khớp binding khiến kho hàng không nhận được thông điệp.
Nhóm tích hợp chuyển từ gửi trực tiếp vào queue sang publish qua topic exchange, nhưng một số sự kiện giao hàng không được listener nhận vì cách đặt routing key giữa hai dịch vụ không thống nhất.
Một ứng dụng gửi thông báo đến nhiều chi nhánh qua fanout exchange, nhưng một nhóm chỉ tạo queue mà không có binding tương ứng nên không nhìn thấy sự kiện mới.
Đội triển khai dùng headers exchange để định tuyến theo loại khách hàng, nhưng producer Spring AMQP gửi sai kiểu dữ liệu của header khiến bản tin đi vào một tập queue ngoài dự kiến.
Một hệ thống phân loại cảnh báo theo cấp độ dùng topic exchange với ký tự đại diện, nhưng binding quá rộng khiến consumer cảnh báo khẩn nhận cả những sự kiện kiểm thử.
Ứng dụng gọi RabbitTemplate với tên exchange rỗng và kỳ vọng routing key được xử lý theo một topic exchange riêng, khiến không có listener nghiệp vụ nào xử lý thông điệp.
Đội phát triển đổi tên exchange khi triển khai phiên bản mới nhưng quên cập nhật cấu hình RabbitTemplate ở một nhóm pod; message được gửi đến topology cũ trong nhiều giờ.
Nhà vận hành thêm một queue dự phòng cho exchange của sự kiện thanh toán, nhưng cùng sự kiện được chuyển đến cả hai queue và hai hệ thống cùng tạo bản ghi giao dịch.
Spring Boot startup tự khai báo exchange và binding cho một service, nhưng môi trường production đã có exchange cùng tên với kiểu khác nên service không hoàn thành khởi tạo.
Một ứng dụng gửi yêu cầu tới nhiều vùng qua recipient routing riêng nhưng chỉ khai báo binding ở vùng đầu tiên; dữ liệu khách được xử lý không đồng nhất theo vùng.
Dịch vụ sản phẩm gửi event cập nhật giá tới exchange theo nhóm SKU, nhưng routing key có ký tự đặc biệt không theo chuẩn nhóm phân cấp và thông báo thiếu một phần danh mục.
Trong hệ thống logistics, RabbitTemplate gửi lệnh giao hàng theo routing key lấy từ mã đối tác, nhưng mã không tồn tại trong bảng binding khiến lệnh biến mất khỏi luồng nghiệp vụ.
Nhóm tích hợp dùng một topic exchange cho cả dữ liệu công khai và nội bộ, nhưng một binding rộng ở queue báo cáo khiến thông điệp nhạy cảm được chuyển đến consumer không phù hợp.
Nhân viên vận hành thêm binding mới vào một queue đang xử lý sự kiện theo quy trình cũ, làm queue nhận thêm loại thông điệp mà handler chưa phân biệt và thống kê sai nghiệp vụ.
Ứng dụng có RabbitTemplate cấu hình exchange mặc định cho dịch vụ A nhưng một đường gọi đổi exchange qua tham số; các message từ đường gọi này bị gửi sang hệ thống B không liên quan.
Nhóm phát triển gửi message sau khi lưu hóa đơn và ghi log 'publish success' ngay lúc RabbitTemplate trả về, nhưng broker ngắt kết nối trong giai đoạn xác nhận nên không rõ message đã được nhận.
Một service sử dụng publisher confirms để theo dõi message gửi thành công, nhưng callback của các publish đồng thời không có correlation data rõ ràng nên không xác định được đơn hàng gặp lỗi.
RabbitMQ chấp nhận publish vào exchange nhưng không có queue nào khớp routing key; hệ thống chỉ dựa vào publisher confirm và ghi nhận rằng sự kiện chắc chắn đã đến consumer.
Đội cấu hình mandatory publish và returned-message callback nhưng log không giữ message ID; khi một thông điệp bị trả lại, nhóm không biết yêu cầu nghiệp vụ nào cần xử lý tiếp.
Nhà vận hành chuyển broker giữa các node khi RabbitTemplate đang gửi hàng trăm message; một số request nhận lỗi kết nối sau khi broker có thể đã chấp nhận dữ liệu.
Một ứng dụng bật publisher confirms trong môi trường thử nghiệm nhưng cấu hình ConnectionFactory production khác, khiến số message không có trạng thái xác nhận tăng đột ngột.
Ứng dụng theo dõi return callback và confirm callback trên cùng publish nhưng không ghi nhận sự khác biệt giữa bản tin không định tuyến được và bản tin không được broker chấp nhận.
Nhóm triển khai gửi nhiều thông điệp trong một vòng lặp rồi đợi confirm từng cái; throughput suy giảm mạnh dù RabbitMQ và network vẫn còn khả năng phục vụ.
Một producer dùng correlation ID trùng cho nhiều lần thử publish từ cùng đơn hàng; khi callback trả về không theo thứ tự, trạng thái gửi của đơn bị cập nhật sai.
RabbitTemplate được dùng trong web request với thời gian chờ xác nhận publish dài; khi broker bận, các request HTTP bị giữ tới lúc gateway timeout và khách gửi lại đơn.
Một ứng dụng gửi message có payload lớn và chờ confirms, nhưng kết nối thường bị đóng sau thời gian chờ vì lưu lượng outbound vượt giới hạn trong giờ cao điểm.
Nhóm theo dõi confirm ACK từ broker như bằng chứng consumer đã xử lý thành công; nhiều khách vẫn không nhận hàng dù dashboard producer hiển thị tất cả sự kiện thành công.
Một exchange RabbitMQ dùng alternate exchange để tiếp nhận message không khớp binding, nhưng hệ thống không quan sát được số lượng bản tin đi đường thay thế và bỏ sót cảnh báo cấu hình.
Ứng dụng bật retry ở RabbitTemplate khi publish lỗi mạng nhưng không có ID ổn định; cùng lệnh tạo phiếu xuất kho được gửi hai lần sau khi mạng phục hồi.
Một batch producer đánh dấu hoàn tất cả lô khi phần lớn confirms đã đến, trong khi các message còn lại chưa có phản hồi và dữ liệu giữa hai hệ thống bị lệch.
Ứng dụng xử lý yêu cầu qua @RabbitListener nhưng tên queue trong annotation thuộc môi trường thử nghiệm, khiến production không có message nào kích hoạt handler.
Một listener Spring AMQP dùng container có nhiều consumer nhưng phần xử lý phụ thuộc biến trạng thái dùng chung không an toàn; dưới tải, kết quả đơn hàng bị ghi sai chéo nhau.
@RabbitListener nhận JSON đơn hàng nhưng phương thức Java khai báo tham số không phù hợp với kiểu payload sau conversion; hệ thống chuyển lỗi liên tục thay vì xử lý bản tin.
Nhóm viết nhiều @RabbitHandler cho các loại message trong một class nhưng header type của producer không đủ rõ; listener không chọn được handler cho một loại sự kiện mới.
Ứng dụng dùng listener xử lý đơn hàng trên thread consumer và gọi API bên ngoài đồng bộ trong nhiều giây; queue depth tăng nhanh dù broker không quá tải.
Đội vận hành tăng concurrent consumers của listener container để giảm backlog, nhưng database nghiệp vụ đạt giới hạn kết nối và thời gian hoàn tất đơn tăng thêm.
Một listener tạo nhiều tác vụ bất đồng bộ rồi trả về trước khi các tác vụ hoàn tất; broker coi message đã được xử lý trong khi một số tác vụ vẫn còn có thể thất bại.
Ứng dụng nhận message thanh toán theo đơn hàng nhưng listener chạy song song; các sự kiện cập nhật cùng orderId được ghi ra database không theo thứ tự phát sinh.
Listener container được cấu hình tự khởi động và kết nối RabbitMQ trước khi schema nghiệp vụ sẵn sàng, khiến message được xử lý lỗi liên tục ngay sau khi pod khởi chạy.
Ứng dụng tắt một nhóm listener để bảo trì nhưng cấu hình động không áp dụng đồng đều cho các pod; một phần message vẫn được tiêu thụ trong cửa sổ dừng dịch vụ.
Một service có hai @RabbitListener cùng lắng nghe cùng một queue nhưng nhóm sản phẩm nghĩ cả hai sẽ nhận mọi sự kiện; một nửa bản tin không đi qua bước kiểm toán mong đợi.
Container của listener được cấu hình prefetch quá lớn, làm một consumer giữ hàng trăm message chưa xử lý trong khi các consumer khác nhàn rỗi.
Nhóm triển khai listener có thời gian xử lý rất khác nhau theo loại đơn, nhưng queue dùng chung và cách phân phối hiện tại khiến yêu cầu nhỏ bị giữ lâu phía sau bản tin nặng.
@RabbitListener sử dụng chế độ acknowledge tự động, nhưng handler bắt exception rồi chỉ ghi log; message được coi đã xử lý thành công dù thay đổi nghiệp vụ chưa được ghi.
Nhóm dùng manual acknowledgement trong @RabbitListener nhưng một nhánh trả về sớm không ACK; số message unacked tăng tới mức broker không phân phối tiếp như kỳ vọng.
Trong một listener manual ACK, message được xác nhận trước khi transaction database hoàn tất; sau khi database lỗi, broker không còn bản tin để thử xử lý lại.
Một listener manual ACK bị ngắt kết nối ngay sau lúc ghi database nhưng trước khi gửi xác nhận; cùng message được broker phân phối lại và đơn bị trừ tồn kho hai lần.
Đội tích hợp gọi basicNack với requeue trên message chứa dữ liệu không thể giải mã; cùng bản tin bị chuyển qua các consumer liên tục và CPU tăng.
Ứng dụng chuyển từ auto ACK sang manual ACK nhưng một nhánh xử lý lỗi vẫn giữ logic cũ; cảnh báo duplicate và số unacked message tăng không đồng đều.
Một listener gửi basicReject khi hệ thống kho đang bảo trì tạm thời, nhưng lựa chọn cờ requeue hiện tại làm các lệnh quan trọng bị loại khỏi luồng xử lý.
Nhóm phát triển gọi ACK không đúng delivery tag sau khi handler xử lý bất đồng bộ; channel bị đóng và nhiều message chưa xác nhận được phân phối lại.
Container xử lý nhiều message trên một channel, nhưng một nhánh dùng multiple ACK không xét các delivery tag đang chờ; một số bản tin chưa hoàn tất bị xác nhận sớm.
Một consumer mất kết nối mạng trong lúc xử lý batch đơn hàng; khi kết nối trở lại các message chưa ACK được giao cho những instance khác và xuất hiện side effect trùng.
Nhóm bật acknowledge mode NONE cho listener thống kê quan trọng; khi process bị dừng đột ngột, một phần dữ liệu chưa xử lý bị xem như đã giao xong.
Listener Spring AMQP nhận nhiều message không có khóa định danh nghiệp vụ ổn định; khi có redelivery, ứng dụng không thể phân biệt yêu cầu mới với bản sao được giao lại.
Một ứng dụng hỗ trợ đa ngôn ngữ xử lý message trên hàng đợi chung; khi một consumer xử lý quá chậm, trạng thái unacked tăng nhưng công cụ giám sát chỉ theo dõi ready queue.
Ứng dụng Spring AMQP ném exception cho lỗi tạm thời khi gọi nhà cung cấp, nhưng retry xảy ra quá nhanh và làm dịch vụ đích tiếp tục bị quá tải.
Nhóm cấu hình Spring Retry cho @RabbitListener với số lần thử giới hạn, nhưng khi vượt ngưỡng một message độc bị trả về queue gốc và tạo vòng lặp không kết thúc.
Trong hệ thống gửi email, một lỗi JSON cố định được retry giống lỗi timeout; broker tiếp tục phân phối lại message hỏng và các email bình thường bị chậm.
Một listener xử lý lỗi tạm thời nhưng chính sách backoff không có jitter; nhiều pod Spring AMQP cùng thử lại ở một thời điểm và tạo đỉnh tải định kỳ.
Ứng dụng dùng stateful retry cho thao tác nghiệp vụ nhưng không có định danh message nhất quán qua redelivery; bộ đếm retry bị đặt lại và không dừng đúng ngưỡng.
Nhóm thêm RetryInterceptor vào listener container nhưng lỗi xảy ra trước khi handler được gọi trong bước chuyển đổi payload; một số bản tin không đi theo chính sách retry dự kiến.
Một listener ném AmqpRejectAndDontRequeueException cho dữ liệu không hợp lệ nhưng queue chưa có cấu hình dead-letter; message bị loại mà đội vận hành không có nơi điều tra.
Đội dùng dead-letter exchange cho message quá hạn nhưng queue dead-letter bị thiếu binding; RabbitMQ không chuyển được bản tin hỏng đến kho điều tra mà nhóm nghĩ đã được lưu.
Một dịch vụ gửi message vào dead-letter queue sau nhiều lần retry nhưng không ghi nguồn lỗi và ID nghiệp vụ; nhân viên trực không biết dữ liệu nào có thể được phát lại an toàn.
Đội hỗ trợ replay message từ DLQ vào queue chính sau khi sửa lỗi code, nhưng bản tin đã có tác dụng một phần ở hệ thống đích và thao tác được thực hiện hai lần.
Một queue có TTL ngắn dùng để trì hoãn retry, nhưng thông điệp chờ lâu hơn mong đợi vì queue ưu tiên xử lý các message khác; thời điểm retry thực tế không phù hợp SLA.
Hệ thống kết hợp nhiều queue retry theo mốc thời gian nhưng routing key quay về exchange chính bị cấu hình sai; message hết hạn không trở lại được listener nghiệp vụ.
Nhóm vận hành dùng policy dead-letter cho queue chính nhưng một đợt thay đổi hạ tầng ghi đè cấu hình khai báo của ứng dụng; tỷ lệ message bị loại tăng mà không rõ điểm đến.
Một listener tự ghi lỗi vào queue điều tra và sau đó vẫn ném exception; cùng message được đưa vào DLQ thủ công và DLQ của broker, khiến bộ phận hỗ trợ thấy hai bản.
Ứng dụng áp retry vô hạn cho lỗi thiếu quyền truy cập exchange; sau khi cấu hình tài khoản thay đổi, các message vẫn kẹt vì lỗi này không thể được phục hồi bằng retry nghiệp vụ.
Nhà vận hành theo dõi số message trong DLQ nhưng không phân biệt lỗi cố định với lỗi phụ thuộc hệ thống bên ngoài; backlog DLQ tăng và mất ưu tiên xử lý.
Một queue dead-letter dùng chung cho hàng chục nghiệp vụ không giữ đầy đủ header nguồn; khi một message lạ được nhận, ứng dụng không xác định được schema phù hợp để kiểm tra.
Nhóm tạo một worker đọc DLQ và tự chuyển tất cả message về queue chính theo lịch; các lỗi không thể xử lý lặp lại vô hạn qua vòng dead-letter.
Ứng dụng dùng TTL theo từng message để trì hoãn kiểm tra đơn hàng, nhưng khi message hết hạn một số tác vụ cần đảm bảo thứ tự lại được xử lý đảo trước sau.
Một consumer từ DLQ ghi log toàn bộ payload lỗi nhằm debug, nhưng message chứa dữ liệu cá nhân khiến log tập trung trở thành nguồn rò rỉ ngoài chính sách.
Một listener chuyển message không khớp phiên bản schema sang DLQ, nhưng sau deploy mới không có quy trình phân loại và replay; các sự kiện quan trọng nằm lại nhiều ngày.
Một service ghi đơn hàng vào PostgreSQL rồi publish OrderCreated qua RabbitTemplate; khi RabbitMQ lỗi ngay sau DB commit, khách thấy đơn mới nhưng các hệ thống downstream không nhận sự kiện.
Nhóm triển khai RabbitTransactionManager cho thao tác publish và tưởng nó cũng rollback được transaction SQL của dịch vụ kho; sau sự cố, dữ liệu DB và broker không còn nhất quán.
Một listener xử lý thanh toán trong local transaction database và ACK message ở thời điểm riêng; tiến trình bị dừng giữa hai thao tác khiến side effect được thực hiện lại.
Ứng dụng chuyển kênh RabbitMQ sang chế độ transaction để bảo toàn message, nhưng thông lượng publish giảm và thời gian phản hồi HTTP vượt ngân sách đã cam kết.
Đội phát triển dùng Spring AMQP để cập nhật tồn kho và gửi sự kiện tiếp theo trong cùng handler, nhưng việc gửi thành công rồi database rollback để lại sự kiện mô tả trạng thái không tồn tại.
Một hệ thống dựa vào publisher confirm làm dấu hiệu transaction nghiệp vụ hoàn thành, nhưng sau khi broker nhận message, consumer ghi database thất bại và không có trạng thái bù.
Nhóm triển khai outbox để tránh mất sự kiện sau khi lưu đơn, nhưng job phát bản ghi outbox bị crash sau publish và trước khi đánh dấu đã phát, khiến một event được gửi lại.
Một consumer ghi event ID vào bảng dedup sau khi cập nhật số dư thay vì cùng transaction; khi pod chết giữa hai thao tác, message redelivery tiếp tục trừ tiền lần nữa.
Ứng dụng gắn message ID mới cho mỗi lần thử RabbitTemplate, khiến consumer không nhận biết các bản sao của cùng lệnh nghiệp vụ và tạo nhiều phiếu thanh toán.
Một listener xử lý cùng orderId từ hai queue có nguồn khác nhau; hai transaction cùng cập nhật trạng thái đơn, gây lost update dù từng queue riêng lẻ không có lỗi.
Đội dùng optimistic locking ở database nhưng exception xung đột bị retry không giới hạn ở listener; một đơn hàng luôn kẹt giữa các consumer cạnh tranh.
Ứng dụng phát event InventoryReserved và PaymentCompleted gần nhau nhưng consumer hợp nhất trạng thái theo thứ tự nhận; khi một message đến trễ, đơn hàng bị đánh dấu sai.
Một nhóm phát hành lệnh hoàn tiền bằng RabbitTemplate mà không có khóa idempotency, khi client mất HTTP response đã gửi lại lệnh và tạo hai giao dịch bù.
Ứng dụng xử lý message theo nhóm và ghi ACK toàn bộ batch nhưng một record giữa batch thất bại nghiệp vụ; các record phía sau bị xem hoàn tất khi chưa được cập nhật.
Một listener xử lý lệnh gửi hàng và cập nhật trạng thái ngoài hệ thống đối tác, nhưng API đối tác timeout sau khi đã thực hiện; redelivery làm lệnh gửi hàng trùng.
Nhóm triển khai transaction cho channel RabbitMQ khi xử lý nhiều message nhưng chưa tính đến trường hợp consumer mất kết nối đúng lúc broker xác nhận commit.
Ứng dụng coi thứ tự message trong một queue là thứ tự xử lý cuối cùng; khi nhiều @RabbitListener consumer và retry cùng hoạt động, sự kiện sau hoàn tất trước sự kiện trước.
Một hệ thống đòi hỏi thứ tự sự kiện theo accountId nhưng producer gửi tất cả vào queue chung có nhiều consumer; số dư cuối kỳ khác nhau khi replay cùng tập sự kiện.
Nhóm triển khai single active consumer để bảo toàn thứ tự một queue, nhưng khi chuyển node failover vẫn xuất hiện message redelivery và xử lý trùng tại biên.
Service sản xuất báo cáo chờ tất cả các message trong một chuỗi hoàn tất, nhưng không có correlation ID cho từng đợt; kết quả của hai đợt chạy bị trộn vào nhau.
Một consumer xử lý dữ liệu giao hàng dựa vào thứ tự của eventTime trong payload, nhưng đồng hồ giữa các nhà vận chuyển không đồng bộ và bản ghi mới bị ghi đè.
Một nền tảng trao đổi message dùng contentType JSON nhưng RabbitTemplate được cấu hình converter mặc định theo kiểu khác; listener Java không đọc được payload vừa publish.
Ứng dụng dùng Jackson JSON message converter cho các DTO Java, nhưng producer bổ sung trường không được consumer cũ dự kiến; một nhóm listener từ chối message ngay sau deploy.
Nhóm cập nhật cấu trúc JSON từ kiểu số sang chuỗi ở trường customerId; Spring AMQP nhận payload nhưng dữ liệu được ánh xạ sai và liên kết đơn hàng thất bại.
Một hệ thống gửi object Java trực tiếp giữa các service bằng serialization không được kiểm soát; sau khi nâng phiên bản class, consumer cũ không giải mã được bản tin.
Ứng dụng nhận message có type header từ bên ngoài nhưng không giới hạn các kiểu đối tượng được phép deserialize; nhóm bảo mật phát hiện nguy cơ xử lý dữ liệu không tin cậy.
Nhóm nâng cấp Jackson converter nhưng các message lưu từ trước vẫn nằm trong queue với type metadata cũ; listener mới không còn giải mã được bản tin tồn.
Một listener dùng cùng DTO cho hai loại sự kiện có ý nghĩa khác nhau, khiến một trường tùy chọn bị coi nhầm là trạng thái hoàn tất giao dịch.
Nhóm triển khai @RabbitListener có tham số nhận cả payload và header nhưng một partner bỏ header nghiệp vụ bắt buộc; message bị xử lý với giá trị mặc định sai.
Ứng dụng gửi correlation ID trong header với tên khác giữa hai phiên bản producer; consumer request-reply không ghép được phản hồi với request ban đầu.
Một đội gửi thời gian xử lý dưới dạng chuỗi không có múi giờ trong JSON, khiến các message từ nhiều khu vực được sắp thứ tự sai khi listener tổng hợp dữ liệu.
Message chứa file đính kèm lớn được nhúng nguyên trong payload RabbitMQ; khi nhiều worker nhận đồng thời, bộ nhớ broker và thời gian xử lý mạng tăng đột biến.
Nhóm dùng compression cho payload JSON dung lượng lớn nhưng một listener chưa hỗ trợ format mới; message chỉ lỗi khi dữ liệu vượt ngưỡng kích thước bật nén.
Ứng dụng thêm metadata tenantId vào header nhưng không kiểm soát nội dung từ producer bên thứ ba; một listener có thể xử lý thông điệp dưới tenant sai.
Nhóm lưu binary payload từ thiết bị vào RabbitMQ rồi convert thành chuỗi với encoding không thống nhất; một số bản tin chứa tiếng Việt bị lỗi ký tự và mất mã phân loại.
Đội vận hành phát hiện message có schema lỗi trong queue tồn tại lâu; các bản phát hành mới của listener đọc lại dữ liệu cũ và gây lỗi khác so với khi publish ban đầu.
Ứng dụng dùng RabbitTemplate.convertAndSend cho event phiên bản mới nhưng không gắn schema version, khiến nhiều consumer không biết định dạng nào phù hợp để xử lý.
Spring Boot khai báo queue durable trong cấu hình nhưng khi triển khai lên cluster đã có queue cùng tên với thuộc tính khác, dịch vụ thất bại lúc RabbitAdmin xác minh topology.
Một môi trường dùng queue auto-delete cho tác vụ quan trọng; khi toàn bộ consumer tạm ngắt kết nối, queue biến mất và các message tiếp theo không có điểm nhận.
Đội vận hành chuyển queue classic sang quorum nhưng ứng dụng vẫn khai báo thuộc tính x-queue-type cũ; việc khởi động service gây lỗi bất tương thích với queue sẵn có.
Một hệ thống dùng exclusive queue để nhận phản hồi của một instance, nhưng autoscaling tạo thêm pod với cấu hình tên queue cố định khiến các pod cạnh tranh quyền sở hữu.
Nhóm tạo queue tên ngẫu nhiên cho request-reply ở mỗi lần khởi động nhưng chưa theo dõi tài nguyên; sau các lần crash, nhiều queue không còn consumer vẫn tồn tại.
Ứng dụng dùng direct reply-to với RabbitTemplate cho các request nhanh nhưng service đích xử lý lâu hơn timeout; caller không còn chờ khi phản hồi muộn xuất hiện.
Nhóm đặt TTL rất ngắn cho queue lệnh giao nhận trong khi đối tác thường bảo trì lâu; message bị dead-letter trước khi consumer kịp trở lại làm việc.
Đội cấu hình giới hạn độ dài queue để bảo vệ broker nhưng chưa nhận diện message bị loại khi hàng đợi đầy; tỷ lệ đơn hàng không được xử lý tăng trong giờ cao điểm.
Một nhóm gửi message có priority khác nhau vào queue hỗ trợ độ ưu tiên, nhưng cấu hình mức priority và prefetch của consumer khiến đơn khẩn cấp vẫn bị chậm sau hàng trăm đơn thường.
Đội triển khai queue cho phản hồi RPC không có thời hạn sử dụng rõ ràng; các request timeout từ lâu vẫn để lại message không còn caller nhận.
Nhóm vận hành áp policy dead-letter trên RabbitMQ nhưng cấu hình topology trong Spring Boot bị lệch giữa staging và production; cùng lỗi có điểm đến khác nhau.
Một queue dùng làm kho lệnh xử lý lại và nhận nhiều phiên bản schema trong nhiều tuần; sau nâng cấp consumer, một phần message tồn không còn tương thích.
Đội nghiệp vụ tăng số lượng binding cho cùng một queue để nhận thêm sự kiện, nhưng không đánh giá ảnh hưởng của các loại payload mới tới @RabbitListener đang chạy.
Ứng dụng tự tạo queue qua RabbitAdmin ở runtime theo từng khách hàng nhưng không dọn khi hợp đồng kết thúc; số lượng queue tăng và làm cụm RabbitMQ khó vận hành.
Nhóm bảo trì thay tên queue chính trong một lần deploy, trong khi bản cũ vẫn chứa message chưa tiêu thụ; dashboard mới báo không có backlog nhưng đơn hàng cũ còn bị kẹt.
Một consumer chạy trên queue quorum có redelivery liên tục do lỗi cố định; hệ thống không quan sát được khi giới hạn giao lại làm message bị xử lý theo chính sách ngoài dự kiến.
Ứng dụng khởi tạo nhiều RabbitTemplate với connection factory khác nhau cho từng đối tác; số connection và channel tăng mạnh theo số tenant dù lưu lượng thực tế nhỏ.
Nhóm đặt channel cache quá thấp trong CachingConnectionFactory khi gửi message đồng thời; các thread web chờ tạo channel và độ trễ publish tăng.
Đội tăng số connection đến RabbitMQ để giải quyết timeout nhưng broker đạt ngưỡng file descriptor và từ chối kết nối mới trong giờ cao điểm.
Một listener giữ prefetch lớn để tăng throughput nhưng phải xử lý payload rất nặng; số unacked message và mức sử dụng RAM consumer tăng liên tục.
Ứng dụng Spring AMQP có một queue nhận cả message rất nhanh và message gọi API bên ngoài chậm; các request nhẹ phải chờ lâu dù CPU thấp.
Nhóm bật batch listener để tăng thông lượng nhưng ghi nhận sự cố lỗi giữa batch; khó xác định phạm vi message phải phát lại mà không tạo side effect trùng.
Đội triển khai hàng chục pod @RabbitListener cùng lúc; database downstream không đáp ứng số giao dịch đồng thời và nhiều message quay lại queue do timeout.
Một hệ thống tăng prefetch và concurrency đồng thời sau khi có backlog, nhưng mức sử dụng CPU consumer đạt trần và tỷ lệ ACK thành công không cải thiện.
Ứng dụng producer đẩy message nhanh hơn tốc độ listener tiêu thụ trong nhiều giờ; queue depth tăng đều và chi phí lưu trữ broker vượt dự tính.
Trong sự cố mạng, broker kích hoạt connection.blocked vì tài nguyên thấp nhưng producer RabbitTemplate không ghi nhận trạng thái này; request gửi message bị chờ bất thường.
Đội cấu hình heartbeat RabbitMQ quá ngắn cho kết nối qua mạng WAN không ổn định; mỗi đợt jitter tạo hàng loạt reconnect và duplicate delivery.
Ứng dụng dùng CachingConnectionFactory với cấu hình recovery chưa đồng nhất giữa môi trường; sau khi broker khởi động lại, một nhóm producer phục hồi còn listener khác không tiêu thụ.
Nhà vận hành rolling upgrade cụm RabbitMQ trong khi có nhiều message đang xử lý; các pod liên tục reconnect và số giao dịch bị xử lý lại tăng.
Đội Spring Boot không dừng listener một cách có kiểm soát khi nhận tín hiệu shutdown; message đang ghi database bị gián đoạn và phải redeliver sau deploy.
Application pod được báo healthy chỉ vì HTTP endpoint hoạt động, trong khi connection đến RabbitMQ đã hỏng; backlog queue tăng nhưng load balancer vẫn tiếp tục gửi yêu cầu mới.
Một ứng dụng muốn xử lý 100 nghìn thông điệp mỗi phút nhưng chỉ đo tốc độ publish, không đo số ACK, backlog và latency của listener; kết quả benchmark đánh giá sai năng lực.
Đội vận hành sử dụng cùng một tài khoản RabbitMQ cho tất cả Spring AMQP service; khi một credential bị lộ, nhiều queue nghiệp vụ không liên quan cũng có nguy cơ bị truy cập.
Một hệ thống cấu hình vhost tách các môi trường nhưng producer production vẫn trỏ tới vhost thử nghiệm; các listener hợp lệ không nhận được event mới.
Ứng dụng @RabbitListener dùng account chỉ có quyền đọc queue nhưng RabbitAdmin còn cố khai báo topology; service thất bại ở bước khởi động dù queue đã tồn tại.
Đội bảo mật xoay mật khẩu RabbitMQ giữa giờ làm việc; một số pod giữ connection lâu và một số reconnect với credential cũ, làm kết nối hoạt động không đồng đều.
Nhóm triển khai TLS cho RabbitMQ nhưng một số Spring AMQP client vẫn dùng cổng không mã hóa; sau khi broker tắt đường truyền thường, nhiều listener bị mất kết nối.
Ứng dụng Spring AMQP qua mTLS sử dụng chứng chỉ client sắp hết hạn; khi nhiều pod khởi động sau deploy, chúng không thể đăng nhập dù config queue và exchange không đổi.
Đội vận hành ghi đầy đủ RabbitMQ message headers và payload khi debug lỗi retry; các message chứa token truy cập và thông tin cá nhân bị lộ trong log tập trung.
Nhóm giới hạn quyền publish theo exchange nhưng một service vẫn có quyền bind queue ngoài phạm vi của nó; cấu hình routing có thể làm lộ sự kiện nhạy cảm.
Ứng dụng nhận message từ bên thứ ba qua RabbitMQ mà không kiểm tra quyền tenant trong payload; một bản tin được chuyển hợp lệ vẫn thay đổi dữ liệu của doanh nghiệp khác.
Nhóm lưu correlation ID bằng mã định danh khách hàng thực vào label metrics cho mọi message; hệ thống giám sát sinh lượng lớn chuỗi dữ liệu và lưu dấu thông tin nhạy cảm.
Đội hỗ trợ cho phép nhân viên replay DLQ qua công cụ nội bộ nhưng chưa giới hạn quyền và audit; sau một thao tác nhầm, nhiều giao dịch cũ được thực hiện lại.
Ứng dụng xử lý sự kiện giá cả chứa dữ liệu bí mật và lưu payload thô trong queue chung; các nhóm consumer không liên quan có thể đọc nội dung khi được cấp quyền broker quá rộng.
Một nhóm lưu username/password RabbitMQ trực tiếp trong cấu hình ứng dụng được đóng gói; sau khi repository bị chia sẻ cho đối tác, quy trình khắc phục ảnh hưởng nhiều service.
Đội triển khai RabbitMQ ở hai data center nhưng không đánh giá độ trễ, failover và cách xác nhận message; khi mất một vùng, ứng dụng không biết publish nào đã thành công.
Nhóm muốn quan sát hành trình đơn hàng từ HTTP request đến RabbitTemplate và @RabbitListener nhưng trace context không được truyền trong message header; log giữa hai service không liên hệ được.
Ứng dụng chỉ đo queue ready mà bỏ qua unacked, consumer count, redelivery và số message vào DLQ; dashboard xanh trong khi công việc bị treo lâu.
Đội vận hành sử dụng message ID làm nhãn metrics riêng cho từng sự kiện; số lượng time series tăng nhanh gây quá tải hệ thống quan sát trong giờ cao điểm.
Một hệ thống đo độ trễ xử lý message từ lúc listener bắt đầu chứ không tính thời gian chờ trong queue; khách gặp chậm nhiều giờ nhưng báo cáo latency vẫn thấp.
Nhóm triển khai logging ở RabbitTemplate và @RabbitListener nhưng không giữ correlation ID xuyên retry; khi một đơn được xử lý nhiều lần, rất khó xác định lần nào tạo side effect.
Ứng dụng bật debug log cho toàn bộ AMQP connection và listener khi có lỗi, khiến khối lượng log tăng cao mà vẫn thiếu số liệu về queue lag và tỷ lệ retry.
Một doanh nghiệp muốn cảnh báo sớm khi DLQ tăng liên tục nhưng chỉ cấu hình cảnh báo theo CPU broker; các sự kiện bị lỗi tích lũy nhiều ngày mà không ai nhận thấy.
Đội kiểm thử Spring AMQP bằng mock RabbitTemplate trả thành công cho mọi lần gửi; hệ thống không phát hiện lỗi routing key không khớp binding hoặc message bị broker trả lại.
Bài thử @RabbitListener chạy với một message hợp lệ nhưng không kiểm tra lỗi chuyển đổi JSON và redelivery; sau deploy một bản tin sai schema khiến consumer kẹt lặp.
Nhóm tích hợp test xử lý đơn hàng bằng RabbitMQ cục bộ có một consumer, nhưng production bật nhiều consumer; lỗi tranh chấp trạng thái xuất hiện sau khi lên tải thật.
Một bài test dừng consumer sau khi commit database nhưng trước ACK, tuy nhiên không xác minh dữ liệu dedup; khi broker redeliver, số dư bị cập nhật hai lần.
Đội QA chỉ kiểm tra publish/consume trong điều kiện mạng ổn định; khi đứt kết nối đúng lúc publisher confirm, RabbitTemplate retry tạo các message trùng.
Một bài test dùng broker RabbitMQ chạy qua Testcontainers nhưng không mô phỏng queue chính bị đầy và publisher bị blocked; ứng dụng phản hồi timeout theo cách chưa được kiểm chứng.
Nhóm kiểm thử thay exchange type trong cấu hình ứng dụng giữa hai lần chạy nhưng không khởi tạo topology sạch; test pass trên máy cũ và fail ở pipeline CI.
Đội triển khai message converter mới nhưng bộ kiểm thử không đưa message lịch sử vào queue; sau nâng cấp, nhiều bản tin tồn bị từ chối và chuyển vào DLQ.
Nhóm vận hành chạy diễn tập failover bằng cách khởi động lại broker khi queue rỗng, nhưng sự cố thực xảy ra khi hàng nghìn message unacked đang được xử lý.
Một bộ test đánh dấu thành công khi thông điệp đã đến queue, nhưng không xác minh listener xử lý tác động nghiệp vụ và ACK đúng; khách hàng vẫn gặp đơn hàng bị treo.
Đội triển khai Spring AMQP theo profile nhưng tests chỉ chạy một profile mặc định; production dùng cấu hình prefetch, retry và DLX khác làm hành vi sai lệch đáng kể.
Một hệ thống có SLA giao nhận trong vài phút nhưng không kiểm thử độ trễ tích lũy qua broker, retry, DLQ và replay; công cụ vận hành chỉ phát hiện khi khách khiếu nại.
Nhóm phát triển đặt ngưỡng throughput trên số message mỗi giây, không xét kích thước payload và tốc độ database; bài test đạt tải nhưng production tràn bộ nhớ khi message lớn.
Đội triển khai phiên bản consumer mới song song bản cũ trong rolling deployment nhưng chỉ test cùng một schema mới; một số message từ producer cũ làm handler mới lỗi và bị retry.
Nhóm kiểm toán muốn theo dõi toàn bộ vòng đời lệnh bồi hoàn qua RabbitTemplate, broker, listener và DLQ nhưng chưa lưu được đường đi, thời điểm và trạng thái xử lý của mỗi message.
Ứng dụng có nhiều @RabbitListener với error handler tùy biến, nhưng một handler nuốt exception không báo metrics; tỷ lệ xử lý thành công hiển thị cao dù event bị bỏ qua.
Một cluster RabbitMQ có nhiều queue tồn đọng từ phiên bản ứng dụng cũ, nhưng nhóm deploy chỉ quan sát queue mới và không có cảnh báo cho backlog không còn consumer.
