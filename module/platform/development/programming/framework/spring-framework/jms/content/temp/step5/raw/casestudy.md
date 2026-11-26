Một hệ thống đặt hàng nâng cấp sang Spring Framework dùng Jakarta Messaging, nhưng driver JMS còn phụ thuộc API javax.jms cũ khiến ConnectionFactory không tạo được khi chạy.
Một ứng dụng gửi hóa đơn dùng Spring JMS với broker bên ngoài, nhưng cấu hình broker URL trỏ localhost trong container khiến mọi lệnh gửi chỉ lỗi ở Kubernetes.
Một nhóm vận hành thay chứng chỉ TLS của JMS broker, nhưng truststore trong các Pod Spring chưa được cập nhật nên kết nối mới thất bại sau đợt xoay khóa.
Một dịch vụ dùng credential broker chung cho cả gửi và nhận, nhưng tài khoản chỉ có quyền publish nên @JmsListener báo lỗi khi đăng ký consumer ở queue.
Một ứng dụng tích hợp hai JMS broker cho hai đối tác, nhưng JmsTemplate lấy nhầm ConnectionFactory khiến thông điệp thanh toán được gửi sang môi trường thử nghiệm.
Một nhóm cấu hình ConnectionFactory bằng bean của provider và đồng thời định nghĩa factory wrapper khác, khiến một listener và JmsTemplate sử dụng hai tập connection settings.
Một hệ thống đặt nhiều ứng dụng Spring trên cùng broker nhưng tất cả dùng client ID giống nhau, khiến những kết nối cần danh tính JMS riêng gặp lỗi khi chạy song song.
Một dịch vụ dùng CachingConnectionFactory để giảm chi phí tạo session, nhưng nhóm thay đổi cách dùng consumer khiến tài nguyên cache tăng và khó xác định session đang giữ.
Một ứng dụng giữ JMS Session trong singleton service rồi dùng từ nhiều thread, khiến các thao tác gửi đồng thời có lỗi không ổn định vì Session không được thiết kế để chia sẻ tùy ý.
Một nhóm tạo Connection và Session JMS thủ công song song với JmsTemplate, nhưng khi endpoint lỗi chúng không được đóng đầy đủ và số connection trên broker tăng dần.
Một hệ thống triển khai mười replica Spring Boot cùng mỗi replica mở pool kết nối lớn, khiến broker vượt hạn mức connection dù lưu lượng message chưa tăng đáng kể.
Một ứng dụng có broker failover qua nhiều node, nhưng connection string chỉ trỏ một node cũ khiến producer dừng gửi khi node đó được bảo trì.
Một nhóm kỳ vọng Spring tự tạo queue trên mọi JMS provider khi gọi JmsTemplate với tên mới, khiến ứng dụng chỉ chạy ở broker có chính sách tự tạo destination.
Một hệ thống phân biệt các môi trường bằng tiền tố destination, nhưng deployment production thiếu prefix khiến thông điệp thử nghiệm đi vào queue nghiệp vụ thật.
Một dịch vụ triển khai cấu hình quyền tối thiểu cho broker nhưng còn lệnh tạo destination động, khiến producer kết nối thành công mà bước gửi báo lỗi authorization.
Một ứng dụng cấu hình CachingConnectionFactory cho client gửi request-reply, nhưng sau khi thay đổi đường reply queue cache consumer giữ các resource không còn phù hợp.
Một nhóm dùng Pooled ConnectionFactory của provider cùng lớp cache Spring mà không rà soát giới hạn session, khiến số tài nguyên thực tế khác với cấu hình pool được công bố.
Một hệ thống gặp gián đoạn mạng ngắn khi broker đổi leader, nhưng logic bắt lỗi ở producer coi mọi JMSException như dữ liệu đầu vào không hợp lệ và không có tín hiệu khôi phục.
Một ứng dụng chạy trong mạng phân vùng nhưng metric chỉ ghi số kết nối TCP mở, khiến đội trực không nhận ra các lần tạo JMS Session mới đang thất bại.
Một dịch vụ cần nhận thông điệp từ một broker được quản lý nhưng version thư viện client không tương thích giao thức và chỉ lỗi khi listener container bắt đầu kết nối.
Một nhóm bật cơ chế reconnect của provider nhưng cũng có retry ở tầng ứng dụng, khiến sự cố kết nối ngắn làm nhiều lệnh gửi trùng được phát ra ngoài dự kiến.
Một hệ thống phát triển dùng embedded broker không xác thực, nhưng môi trường production yêu cầu username/password và producer không thể tạo Session khi triển khai.
Một dịch vụ dùng chung ConnectionFactory cho tác vụ ngắn và listener dài hạn, nhưng khi shutdown job đóng trực tiếp shared connection khiến listener ngừng nhận message.
Một ứng dụng có nhiều listener container ở các context khác nhau nhưng cấu hình cùng một tên bean ConnectionFactory, khiến việc debug không xác định được container nối broker nào.
Một nhóm cố giảm độ trễ bằng việc tạo JMS connection mới cho từng đơn hàng, khiến broker quá tải bởi handshake khi traffic tăng đột biến.
Một hệ thống cần truyền thông báo đặt hàng một lần đến một worker, nhưng producer dùng topic khiến mọi subscriber cùng nhận và đơn được xử lý nhiều lần.
Một ứng dụng có hai worker cùng đọc queue thanh toán, nhưng team tưởng mỗi worker sẽ nhận bản sao nên dashboard của worker thứ hai bị thiếu thông điệp.
Một dịch vụ phát sự kiện thay đổi sản phẩm qua topic, nhưng một consumer chỉ khởi động sau khi sự kiện đã gửi và không nhận được lịch sử như nhóm sản phẩm kỳ vọng.
Một hệ thống cần mỗi microservice nhận thông báo cập nhật đơn riêng, nhưng cả ba service lại cùng đăng ký consumer vào một queue khiến chỉ một bên xử lý mỗi message.
Một nhóm chuyển producer từ queue sang topic nhưng quên sửa cấu hình pubSubDomain của JmsTemplate, khiến message vẫn được gửi theo ngữ nghĩa point-to-point.
Một ứng dụng đăng ký @JmsListener vào tên destination mà producer dùng topic, nhưng listener container factory vẫn ở queue mode nên consumer không nhận sự kiện.
Một dịch vụ sử dụng DestinationResolver tùy biến để định tuyến theo tenant, nhưng resolver ở phía sender và listener ánh xạ cùng tên logic sang destination thực khác nhau.
Một hệ thống có nhiều queue đặt tên theo vùng địa lý, nhưng producer lấy vùng từ cấu hình cố định nên tất cả đơn của chi nhánh mới đều được gửi tới vùng cũ.
Một nhóm cấp quyền đọc topic cho analytics nhưng không có subscription hoạt động, khiến dashboard vẫn không có sự kiện mặc dù producer báo gửi thành công.
Một ứng dụng tạo temporary queue cho request-reply, nhưng kết nối chứa queue đã bị đóng trước khi response quay về khiến bên gọi liên tục hết thời gian chờ.
Một dịch vụ thay đổi tên destination khi rollout phiên bản mới, nhưng consumer cũ tiếp tục chờ queue trước đó nên backlog được tách thành hai nơi.
Một hệ thống dùng topic để phát dữ liệu stock realtime, nhưng một consumer xử lý chậm làm nhóm tưởng mọi consumer khác cũng phải đợi giống cơ chế queue chung.
Một ứng dụng muốn lưu offline event của một subscriber trên topic, nhưng chỉ tạo non-durable subscription nên các thông điệp trong lúc service tắt không được nhận lại.
Một nhóm tạo durable topic subscription với tên không ổn định theo từng Pod, khiến broker giữ nhiều subscription cũ và dữ liệu tồn đọng tăng sau mỗi lần triển khai.
Một dịch vụ có durable subscription nhưng client ID đổi theo lần restart, khiến listener không tiếp tục nhận tồn đọng từ danh tính thuê bao trước.
Một hệ thống tăng số Pod cho một durable topic subscription, nhưng nhiều instance dùng cùng định danh subscription không phù hợp mô hình chia sẻ nên consumer không khởi tạo được.
Một ứng dụng dùng shared durable subscription để mở rộng consumer, nhưng đội sản phẩm vẫn kỳ vọng mỗi replica nhận đầy đủ một bản sao của từng sự kiện.
Một nhóm chuyển từ durable topic sang queue để dễ vận hành, nhưng hệ thống báo cáo cần nhiều nhóm nhận đủ event và dữ liệu bắt đầu phân tán giữa worker.
Một dịch vụ xóa subscription khỏi broker khi deploy lại, khiến những sự kiện còn tồn đọng trong durable subscription không còn đường được xử lý.
Một hệ thống có topic cho cảnh báo khẩn nhưng một consumer sử dụng selector khác với producer, khiến một số cảnh báo không bao giờ tới bộ phận vận hành.
Một ứng dụng đặt tên topic và queue giống nhau trong hai namespace của provider, nhưng tool kiểm tra chỉ ghi tên ngắn nên đội trực đọc nhầm backlog của destination.
Một nhóm di chuyển message sang queue mới trong giờ cao điểm, nhưng producer và consumer được nâng cấp lệch thời gian nên tồn đọng cũ không giảm.
Một dịch vụ gửi lệnh tạo đơn qua queue và sự kiện đơn đã tạo qua topic, nhưng consumer downstream nhầm hai luồng nên ghi nhận trạng thái nghiệp vụ hai lần.
Một hệ thống ưu tiên thứ tự xử lý cho cùng khách hàng, nhưng nhiều consumer cùng nhận từ queue nên những đơn độc lập không còn hoàn tất theo đúng thứ tự enqueue.
Một ứng dụng sử dụng tính năng message group đặc thù của broker, nhưng sau đổi provider thứ tự xử lý từng nhóm khách không được bảo đảm như trước.
Một nhóm gửi nhiều thông điệp cập nhật tồn kho có khóa sản phẩm, nhưng consumer xử lý song song và message mới được áp trước cập nhật cũ khiến số tồn bị lệch.
Một hệ thống phát sự kiện topic chứa URL chi tiết sản phẩm, nhưng một subscriber không có quyền gọi URL đó và không thể hoàn tất xử lý dù message hợp lệ.
Một dịch vụ gửi message từ REST endpoint bằng JmsTemplate.convertAndSend, nhưng request nhận HTTP thành công khi broker chấp nhận message chứ chưa biết consumer đã xử lý.
Một nhóm sử dụng JmsTemplate.send để tạo TextMessage thủ công, nhưng bộ nhận mong MapMessage nên xử lý lỗi sau khi listener đọc message.
Một ứng dụng dùng convertAndSend với đối tượng OrderRequest, nhưng MessageConverter mặc định không hỗ trợ kiểu payload đó và việc gửi thất bại ở producer.
Một dịch vụ dùng hai bean JmsTemplate với cấu hình destination mặc định khác nhau, nhưng class gửi không chỉ định bean cần dùng nên lệnh phát thông điệp đi nhầm hàng đợi.
Một nhóm gọi JmsTemplate mà không đặt defaultDestination trong code path không truyền tên queue, khiến chỉ nhánh gửi lệnh nội bộ ném exception khi chạy.
Một hệ thống dùng JmsTemplate.receiveAndConvert để polling queue, nhưng nhiều HTTP request đồng thời cùng chờ nên thread phục vụ API bị giữ lâu khi queue trống.
Một ứng dụng giảm receiveTimeout xuống quá ngắn trên consumer polling, khiến dịch vụ liên tục nhận kết quả rỗng và ghi cảnh báo giả rằng broker mất message.
Một nhóm đặt receiveTimeout rất dài trong job xử lý một lần, khiến công việc không thể kết thúc đúng deadline khi không có thông điệp mới.
Một dịch vụ chuyển từ receive polling sang @JmsListener nhưng còn một job đọc trực tiếp cùng queue, khiến hai consumer cạnh tranh và tỷ lệ message mỗi luồng thay đổi.
Một ứng dụng dùng JmsTemplate để gửi và nhận thông điệp liên tiếp, nhưng kỳ vọng câu lệnh gửi tự động đợi phản hồi nghiệp vụ dù không có request-reply protocol.
Một nhóm dùng sendAndReceive cho yêu cầu tra cứu từ hệ thống khác, nhưng consumer trả về một destination khác với JMSReplyTo khiến lời gọi hết thời gian chờ.
Một hệ thống tạo JMSCorrelationID cho request, nhưng service trả lời gắn correlation ID không tương ứng làm response được ghép nhầm với lời gọi khác.
Một ứng dụng dùng request-reply qua temporary queue, nhưng thời gian xử lý thực tế dài hơn timeout của caller nên response đến sau khi client đã ngừng chờ.
Một dịch vụ có nhiều yêu cầu cùng chờ một reply queue, nhưng consumer ghép response bằng thứ tự nhận thay vì correlation ID khiến dữ liệu hai khách bị đổi chỗ.
Một nhóm triển khai RPC kiểu JMS qua broker nhưng mỗi request giữ một HTTP thread chờ trả lời, khiến API cạn thread khi bên xử lý chậm.
Một hệ thống gửi thông điệp với delivery delay được broker hỗ trợ, nhưng khi đổi JMS provider một số message được phát ngay làm workflow chạy trước thời điểm hợp lệ.
Một ứng dụng cần message tồn tại đủ lâu trong queue, nhưng JmsTemplate có timeToLive quá ngắn khiến backlog giờ cao điểm hết hạn trước khi consumer bắt đầu đọc.
Một nhóm cấu hình priority cao cho sự kiện báo lỗi, nhưng broker và consumer không có chính sách tương ứng nên thứ tự thực tế khác suy luận từ JMSPriority.
Một dịch vụ gửi dữ liệu nghiệp vụ quan trọng với chế độ non-persistent, khiến sau broker restart một phần message chưa xử lý không còn trên queue.
Một hệ thống chuyển JmsTemplate sang send quality-of-service tùy chỉnh, nhưng các thuộc tính TTL/priority do nhóm đặt không được áp dụng trên mọi đường gửi như dự kiến.
Một ứng dụng gửi file metadata lớn qua TextMessage, nhưng kích thước message vượt giới hạn broker nên producer thất bại trong khi các message nhỏ vẫn thành công.
Một nhóm bật message compression ở provider nhưng consumer khác chưa có cấu hình tương thích, khiến một số payload gửi thành công nhưng không thể chuyển đổi ở đầu nhận.
Một hệ thống chuyển từ gửi bằng convertAndSend sang send nhưng quên gắn property tenantId trong MessagePostProcessor, khiến bộ lọc listener bỏ qua thông điệp.
Một dịch vụ đặt header JMSCorrelationID trong MessagePostProcessor, nhưng một bước trung gian tạo message mới mà không sao chép metadata nên trace bị đứt.
Một ứng dụng gửi các sự kiện khác nhau qua một topic nhưng chỉ đặt JMSType không nhất quán, khiến consumer không xác định được loại sự kiện từ header.
Một nhóm dùng property businessStatus với kiểu boolean ở producer, nhưng selector JMS ở listener so sánh với chuỗi và không nhận thông điệp theo điều kiện mong muốn.
Một hệ thống đưa mã phiên người dùng vào property JMS và gửi từ nhiều bản service, nhưng cách chuẩn hóa tên property khác nhau khiến selector không khớp ở một số message.
Một ứng dụng dùng message selector để lọc queue theo nội dung JSON body, nhưng selector chỉ truy cập metadata/property nên sự kiện không được chọn theo kỳ vọng.
Một nhóm cấu hình selector với giá trị status chưa có ở các message lịch sử, khiến listener không nhận tồn đọng cũ dù queue vẫn còn hàng nghìn message.
Một dịch vụ dùng selector theo khu vực trên một queue chung, nhưng một khu vực chưa có listener phù hợp khiến message của khu vực đó tích tụ lâu ngày.
Một hệ thống thay giá trị property priorityLevel từ số sang chuỗi, nhưng selector cũ vẫn so sánh số nên số lượng message được nhận giảm đột ngột.
Một ứng dụng đặt selector trên topic subscription sau khi đã tạo durable subscription, nhưng thay đổi điều kiện filter không được phản ánh như nhóm triển khai dự kiến.
Một nhóm dùng SQL-like selector chứa tên property có ký tự không hợp lệ theo JMS, khiến listener container không thể tạo consumer ở production.
Một dịch vụ ghi property eventType vào JMS message nhưng không kiểm tra chiều hoa thường của chuỗi, khiến bộ phận thống kê chỉ nhận một phần loại event.
Một hệ thống khai báo selector cố định theo tenant ở @JmsListener, nhưng cùng container factory được dùng cho nhiều tenant nên consumer không nhận thông điệp của tenant mới.
Một nhóm đưa thông tin nhạy cảm vào message properties để tiện lọc, nhưng metadata đó xuất hiện trong log broker và công cụ quản trị nhiều người có quyền đọc.
Một dịch vụ chuyển tải trạng thái thanh toán qua MapMessage, nhưng tên key của Map thay đổi sau release và consumer nhận null ở thuộc tính bắt buộc.
Một ứng dụng dùng BytesMessage cho file nhị phân, nhưng consumer mặc định kỳ vọng String nên MessageConverter không tạo được payload phù hợp.
Một nhóm dùng ObjectMessage để gửi entity Java giữa hai dịch vụ, nhưng hai phía dùng phiên bản class khác nhau và việc deserialize thất bại sau triển khai.
Một hệ thống chuyển sang JSON TextMessage để giảm phụ thuộc class, nhưng consumer chưa biết kiểu đích nên không dựng được DTO từ dữ liệu nhận.
Một dịch vụ cấu hình Jackson-based JMS MessageConverter yêu cầu type-id property, nhưng producer cũ không gửi property đó khiến @JmsListener không map được payload.
Một ứng dụng dùng cùng type-id string cho hai DTO sự kiện khác nhau, khiến converter tạo sai loại object và xử lý nghiệp vụ thất bại ở listener.
Một nhóm đổi tên trường JSON từ orderId sang purchaseId, nhưng listener vẫn dùng DTO cũ và bộ chuyển đổi tạo object thiếu mã đơn cần xử lý.
Một hệ thống thêm field bắt buộc trong payload mới nhưng còn consumer chạy version cũ, khiến quá trình rolling deployment có những message không được xử lý.
Một dịch vụ phát payload JSON chứa timestamp không có timezone, khiến hai listener ở các vùng khác nhau chuyển đổi thành thời gian nghiệp vụ khác nhau.
Một ứng dụng gửi số tiền dưới dạng floating-point trong JSON và nhận vào BigDecimal ở consumer, khiến sai số hoặc thay đổi kiểu dữ liệu xuất hiện ở bước đối soát.
Một nhóm cấu hình nhiều MessageConverter khác nhau cho JmsTemplate và listener factory, khiến producer ghi message mà consumer không chuyển đổi cùng một định dạng.
Một hệ thống có listener nhận payload DTO nhưng một publisher gửi raw TextMessage theo cấu trúc cũ, khiến chỉ sự kiện từ publisher đó gây MessagingException.
Một dịch vụ dùng @Header lấy mã tenant của message, nhưng publisher ngoài hệ thống không đặt property này nên handler không có dữ liệu định tuyến.
Một nhóm nhận toàn bộ javax.jms.Message từ thư viện cũ trong Spring phiên bản Jakarta, khiến method signature của listener không tương thích kiểu Message mà container cung cấp.
Một hệ thống định nghĩa nhiều phương thức @JmsListener nhưng quên bật @EnableJms trong cấu hình cần thiết, khiến bean được tạo mà không có listener endpoint hoạt động.
Một ứng dụng đặt @JmsListener lên phương thức của class tự khởi tạo bằng new ngoài Spring, khiến container không đăng ký consumer dù annotation tồn tại trong source code.
Một dịch vụ có nhiều JmsListenerContainerFactory với cấu hình queue và topic, nhưng một listener tham chiếu sai tên factory nên không nhận destination đúng kiểu.
Một nhóm thay đổi tên bean jmsListenerContainerFactory theo quy ước mới, nhưng @JmsListener không chỉ rõ containerFactory và endpoint không được khởi tạo như mong đợi.
Một hệ thống dùng @JmsListener cho queue giao dịch, nhưng một method có nhiều tham số mà payload và headers không đủ thông tin để Spring resolve arguments.
Một dịch vụ có @JmsListener nhận OrderCreatedEvent, nhưng producer gửi schema khác nên quá trình chuyển đổi lỗi trước khi method nghiệp vụ được gọi.
Một ứng dụng đặt concurrency cao cho listener đọc queue, nhưng nhiều consumer cùng xử lý cập nhật trên một customerId khiến thứ tự hoàn tất không còn ổn định.
Một nhóm gán số consumer tối đa lớn hơn tài nguyên kết nối broker cho một listener container, khiến container liên tục lỗi tạo Session khi tải tăng.
Một hệ thống có một @JmsListener xử lý lâu hơn timeout hạ tầng, khiến container còn đang xử lý message cũ khi broker có dấu hiệu consumer không đáp ứng.
Một ứng dụng gắn @JmsListener vào method chỉ dùng để log, nhưng method vô tình ném RuntimeException ở đoạn format và message bị xử lý lại theo chính sách container.
Một dịch vụ khai báo hai listener đọc cùng queue để chia nghiệp vụ theo loại event, nhưng không có selector nên mỗi message có thể đi tới handler không hỗ trợ nó.
Một nhóm tạo một listener cho mỗi tenant và khởi động tất cả cùng lúc, khiến số session và consumer broker tăng nhanh khi tenant mới được thêm liên tục.
Một hệ thống dùng chung một listener container factory cho các endpoint với yêu cầu transaction khác nhau, khiến một luồng xử lý cần rollback nhưng container lại acknowledge sớm.
Một ứng dụng kỳ vọng @JmsListener tự động chạy nhiều lần song song dù concurrency chưa được cấu hình, khiến backlog tăng khi số đơn hàng nhập tăng đột biến.
Một dịch vụ dùng concurrency nhiều worker nhưng logic nghiệp vụ giữ trạng thái trong field singleton của listener bean, khiến message của khách này làm thay đổi kết quả của khách khác.
Một nhóm đặt destination của @JmsListener qua placeholder cấu hình, nhưng property thiếu ở profile production nên endpoint không đăng ký được dù các bean khác chạy bình thường.
Một ứng dụng dùng listener topic không durable để nhận thông báo cấu hình, nhưng khi rolling restart một số instance bỏ lỡ sự kiện cập nhật quan trọng.
Một hệ thống tăng concurrency cho durable topic listener nhưng không xác minh shared subscription được hỗ trợ, khiến một số consumer không thể tạo subscription trên broker.
Một dịch vụ thay selector của @JmsListener từ mức độ ưu tiên cao sang trung bình, nhưng backlog của các message không còn khớp selector vẫn ở queue lâu ngày.
Một nhóm quản lý endpoint động bằng JmsListenerEndpointRegistry, nhưng sau khi dừng một endpoint không có consumer thay thế nên queue tương ứng tăng backlog.
Một ứng dụng tắt autoStartup ở listener container để chờ dữ liệu nền, nhưng sau deployment không có bước khởi động endpoint khiến producer vẫn gửi còn consumer không chạy.
Một hệ thống bật listener trước khi migration database hoàn tất, khiến message được nhận nhưng thao tác ghi theo schema mới thất bại hàng loạt.
Một dịch vụ dùng nhiều container factory và mỗi factory có ErrorHandler khác nhau, khiến cùng một RuntimeException được ghi nhận khác nhau theo endpoint.
Một ứng dụng đặt ErrorHandler cho listener container nhưng mong handler này tự sửa và gửi lại message, khiến chính sách xử lý lỗi không khớp cơ chế acknowledge thực tế.
Một nhóm thêm advice chain vào container listener để đo đạc, nhưng thời gian nhận và chuyển đổi message không được tính giống thời gian thực thi method nghiệp vụ.
Một hệ thống có @JmsListener trả về DTO nhưng chưa khai báo @SendTo và request đầu vào không có JMSReplyTo, khiến container không biết destination để gửi phản hồi.
Một ứng dụng thay đổi default reply destination cho listener có @SendTo, khiến service gọi trước nâng cấp tiếp tục chờ queue cũ và timeout.
Một nhóm mong @JmsListener tự bắt lại tất cả exception khi gọi service con, nhưng exception được chuyển về container và ảnh hưởng cách message được xác nhận.
Một dịch vụ dùng JMSXDeliveryCount để theo dõi số lần nhận lại, nhưng code không tính đến sự khác biệt hỗ trợ property này giữa các JMS provider đang dùng.
Một hệ thống có consumer ghi dữ liệu thành công rồi lỗi lúc gửi audit, khiến message được redeliver và lần xử lý kế tiếp có thể ghi trùng dữ liệu nghiệp vụ.
Một ứng dụng cấu hình listener không dùng session transaction và dùng cơ chế acknowledge tự động, nhưng nhóm phát triển giả định exception luôn làm message quay lại queue.
Một dịch vụ xử lý message trong transacted JMS Session, nhưng một exception bị bắt rồi trả về bình thường khiến container không biết nghiệp vụ đã thất bại để rollback.
Một hệ thống thực hiện listener transaction nhưng gọi API đối tác trước khi commit JMS, khiến message bị nhận lại và API bên ngoài có thể bị gọi hai lần.
Một nhóm dùng CLIENT_ACKNOWLEDGE trong listener nhưng không xác định cách container quản lý acknowledgement, khiến code gọi acknowledge thủ công không phù hợp vòng đời thực tế.
Một dịch vụ chọn DUPS_OK_ACKNOWLEDGE để tăng throughput, nhưng nghiệp vụ thanh toán lại mặc định mỗi message chỉ có một lần delivery nên không chuẩn bị xử lý lặp.
Một ứng dụng dùng Session.recover trong một đoạn xử lý thủ công rồi giả định mọi message đều được redeliver tức thì, khiến kết quả khác theo chế độ acknowledge và broker.
Một nhóm đặt sessionTransacted cho DefaultMessageListenerContainer, nhưng một đường ghi SQL không thuộc transaction JMS nên database vẫn lưu khi consumer rollback.
Một hệ thống dùng @Transactional với DataSourceTransactionManager trong method @JmsListener, nhưng team tin rằng commit JMS và database được bảo đảm nguyên tử mặc định.
Một dịch vụ định nghĩa JmsTransactionManager riêng nhưng một listener dùng transaction manager khác, khiến ranh giới xác nhận message và xử lý nghiệp vụ không trùng nhau.
Một ứng dụng kết hợp Spring JMS với một database trong workflow ghi đơn, nhưng khi database commit rồi broker bị gián đoạn thông điệp xác nhận không được phát ra.
Một nhóm dùng XA transaction cho JMS và database trong hệ thống legacy, nhưng môi trường mới chỉ cung cấp ConnectionFactory thường nên luồng nhiều tài nguyên không còn cùng bảo đảm commit.
Một hệ thống gửi message qua JmsTemplate ngay trong transaction database, nhưng message được consumer xử lý trước khi dữ liệu SQL liên quan xuất hiện với trạng thái đã commit.
Một dịch vụ ghi đơn rồi gửi event JMS nhưng lỗi xảy ra giữa hai bước, khiến database có đơn mới mà downstream không nhận được thông báo.
Một ứng dụng dùng session transaction để gửi nhiều message liên quan, nhưng một message gây lỗi ở bước cuối khiến team không biết nhóm message nào đã được commit.
Một nhóm tự tạo JMS Session ngoài Spring transaction context rồi gửi message từ method có @Transactional, khiến lệnh gửi không tham gia ranh giới transaction mà họ kỳ vọng.
Một hệ thống nhận message và gửi message phản hồi trong cùng một listener, nhưng một bước gửi lỗi khiến message gốc bị redeliver và phản hồi có nguy cơ bị phát lặp.
Một dịch vụ cần idempotency khi ghi payment, nhưng mỗi lần nhận lại message sinh transactionId ngẫu nhiên làm kho dữ liệu không thể nhận diện một nghiệp vụ trùng.
Một ứng dụng nhận message từ nhiều producer cùng sử dụng business ID, nhưng khóa chống trùng chỉ dựa trên JMSMessageID khiến các lần producer gửi lại vẫn được xử lý như mới.
Một hệ thống có producer retry sau lỗi mạng lúc gửi, nhưng không biết broker đã chấp nhận message đầu hay chưa và downstream thấy hai bản ghi giống nhau.
Một nhóm dùng JMSRedelivered để nhận biết retry, nhưng một message mới do producer gửi lại không được đánh dấu redelivery dù chứa cùng sự kiện nghiệp vụ.
Một dịch vụ có poison message với payload JSON sai cấu trúc, khiến mỗi lần listener nhận lại đều lỗi converter và queue không tiến triển như dự kiến.
Một ứng dụng thiết lập dead-letter queue bằng chính sách của broker, nhưng nhóm nghĩ chỉ gắn ErrorHandler trong Spring là đủ để message tự chuyển sang DLQ.
Một hệ thống có DLQ cho queue thanh toán nhưng thiếu thông tin nguyên nhân xử lý thất bại, khiến đội hỗ trợ không thể phân biệt schema lỗi với tài nguyên ngoài tạm hỏng.
Một dịch vụ phát lại message từ DLQ sau khi deploy bản sửa, nhưng khóa idempotency từ lần xử lý cũ khiến những message chưa hoàn tất bị bỏ qua.
Một nhóm cấu hình giới hạn số lần redelivery trên broker, nhưng không kiểm tra chính sách của destination mới khiến poison message ở queue mới được thử lại vô hạn.
Một hệ thống sử dụng backoff rất ngắn cho redelivery, khiến một database đang lỗi tiếp tục nhận hàng nghìn lần ghi thử lại và khó khôi phục.
Một ứng dụng nhận message hết hạn sau khi outage kéo dài, nhưng workflow không phân biệt sự kiện quá hạn với sự kiện còn hiệu lực và cập nhật đơn sai trạng thái.
Một dịch vụ đặt TTL ngắn cho lệnh xử lý bất đồng bộ, nhưng backlog lớn vào ngày khuyến mại làm message hết hạn trước khi listener có cơ hội xử lý.
Một nhóm đọc số message trong DLQ làm chỉ số thành công, nhưng có message lỗi đã được retry rồi xử lý xong nên dashboard không phân biệt trạng thái cuối.
Một hệ thống xử lý nhiều lần JMSRedelivered mà không ghi JMSMessageID và correlation ID trong log, khiến một nghiệp vụ bị lặp rất khó truy vết giữa các lần nhận.
Một ứng dụng chuyển message lỗi vào queue điều tra thủ công, nhưng việc publish message chẩn đoán thất bại lại xảy ra sau khi message gốc đã được xác nhận.
Một dịch vụ dùng retry trong method listener và broker redelivery cùng lúc, khiến một message có thể được thử rất nhiều lần và vượt giới hạn tải của đối tác.
Một nhóm bắt mọi lỗi khi nhận message rồi bỏ qua, khiến broker coi message đã được xử lý trong khi dữ liệu nghiệp vụ thực tế chưa được ghi.
Một hệ thống cần bảo đảm xử lý theo thứ tự của từng đơn, nhưng một message lỗi phải retry còn các message mới tiếp tục hoàn thành và trạng thái đơn bị đảo.
Một ứng dụng để consumer đọc queue theo thứ tự nhận, nhưng mức độ ưu tiên JMS và chính sách dispatch của provider khiến thứ tự thực tế không giống thời gian publish.
Một dịch vụ đặt prefetch lớn ở broker, nhưng nhiều consumer có tốc độ xử lý không đều khiến một worker giữ nhiều message trong khi worker khác rảnh.
Một nhóm tăng concurrency của listener để giảm backlog, nhưng kết nối database chỉ cho phép ít request nên số message đang xử lý tăng mà throughput không cải thiện.
Một hệ thống mở rộng nhiều Pod nhận cùng queue, nhưng business handler không an toàn cho xử lý đồng thời và nhiều message cập nhật cùng tài khoản bị ghi chồng.
Một ứng dụng triển khai nhiều consumer topic cho cùng loại event, nhưng mỗi subscription có backlog riêng khiến số message tổng trên broker tăng khi thêm service.
Một nhóm gộp listener có thời gian xử lý nhanh và chậm trong cùng pool, khiến message quan trọng bị giữ chờ sau những tác vụ báo cáo dài.
Một dịch vụ dùng queue chung cho thông báo khẩn và tác vụ nền, nhưng số lượng tác vụ nền lớn làm cảnh báo quan trọng không được xử lý trong thời hạn.
Một hệ thống gắn @JmsListener cho hàm gọi HTTP chậm, nhưng khi dependency ngoài bị treo số consumer hoạt động bị giữ và queue backlog liên tục tăng.
Một ứng dụng chuyển listener sang khởi động nhiều instance, nhưng broker giới hạn số consumer cho destination nên một số container không thể start thành công.
Một nhóm chỉ theo dõi số message đã nhận mà không đo thời gian xử lý mỗi listener, khiến endpoint xử lý chậm được hiểu nhầm là thiếu consumer.
Một dịch vụ đo độ trễ bằng thời điểm tạo message từ hệ thống gửi, nhưng producer và consumer có đồng hồ lệch nhau khiến metric latency xuất hiện giá trị âm.
Một hệ thống tạo metric theo JMSMessageID của từng message, khiến số time series tăng mạnh và backend quan sát bị quá tải khi lưu lượng tăng.
Một ứng dụng log toàn bộ payload message ở @JmsListener để debug, khiến thông tin cá nhân và nội dung thanh toán xuất hiện trong log tập trung.
Một nhóm dùng JMSCorrelationID để nối log producer–consumer, nhưng các luồng gửi lại không giữ cùng correlation ID nên một giao dịch có nhiều trace rời rạc.
Một dịch vụ bật distributed tracing cho HTTP nhưng không truyền trace context vào JMS properties, khiến thao tác xử lý bất đồng bộ mất liên kết với request tạo ra nó.
Một hệ thống có bộ chuyển đổi JMS message tự viết, nhưng không giữ thông tin correlation ID và tenant ở headers nên log của consumer không biết nguồn nghiệp vụ.
Một ứng dụng chỉ cảnh báo khi listener container đã dừng, nhưng trường hợp selector lọc hết message hoặc DB treo vẫn làm queue backlog tăng mà không có alert.
Một nhóm kiểm soát quyền publish theo queue nhưng mọi service vẫn dùng cùng tài khoản broker, khiến khi một service bị lộ credential ảnh hưởng tới nhiều destination.
Một hệ thống dùng temporary destination cho reply message nhưng không giới hạn người nhận phù hợp, khiến dữ liệu trả về có nguy cơ bị truy cập ngoài phạm vi dự kiến.
Một dịch vụ đặt các property JMS chứa mã khách hàng dễ nhận diện, nhưng những metadata này được lưu trong công cụ quản trị broker lâu hơn chính sách bảo mật.
Một ứng dụng triển khai message payload có version nhưng không kiểm version ở consumer, khiến sự kiện từ producer mới được ánh xạ sai ở worker chưa nâng cấp.
Một nhóm muốn tái xử lý sự kiện cũ từ broker sau thay đổi schema, nhưng MessageConverter chỉ hiểu DTO mới và không thể đọc payload đã lưu lâu ngày.
Một hệ thống có producer và consumer dùng múi giờ khác nhau, nhưng message chỉ ghi hạn xử lý dạng local date-time và một số đơn bị coi là hết hạn sai.
Một dịch vụ tích hợp khách hàng từ đối tác qua JMS, nhưng các message không có khóa idempotency nghiệp vụ khiến retry từ hệ thống đối tác tạo hồ sơ lặp.
Một ứng dụng khởi listener ngay khi Spring context refresh nhưng chưa tải xong bảng mã tham chiếu, khiến các message đầu tiên bị xử lý thiếu metadata.
Một nhóm tắt listener trong lúc nâng cấp database, nhưng producer vẫn gửi vào queue và thời gian sống message không đủ dài để vượt qua cửa sổ bảo trì.
Một hệ thống shutdown Pod ngay sau khi nhận tín hiệu dừng, khiến @JmsListener đang xử lý message dài không có thời gian hoàn tất và broker có thể redeliver sau restart.
Một dịch vụ bật listener container stop nhưng một producer nội bộ vẫn tiếp tục gửi message, khiến ứng dụng được đánh dấu ngừng mà queue còn phát sinh backlog.
Một ứng dụng chuyển config listener concurrency trong runtime nhưng các endpoint đang hoạt động chưa nhận thay đổi, khiến đội vận hành tưởng đã tăng consumer mà backlog không giảm.
Một nhóm chuyển provider JMS giữa các môi trường nhưng dựa vào chính sách mặc định prefetch và DLQ cũ, khiến hành vi retry của bản production khác hoàn toàn staging.
Một hệ thống nâng thư viện client JMS lên phiên bản Jakarta nhưng còn MessageConverter tùy biến import javax.jms, khiến bean được tạo nhưng lỗi chỉ xuất hiện khi chuyển đổi.
Một dịch vụ có nhiều @JmsListener cùng tên endpoint ID trong một ApplicationContext, khiến đăng ký endpoint thất bại sau khi thêm module mới.
Một nhóm triển khai listener bằng annotation ở lớp abstract nhưng bean thực tế là proxy theo interface, khiến việc tìm và đăng ký listener methods cần được xác minh sau refactor.
Một ứng dụng gửi @JmsListener message từ integration test nhưng test không chờ xử lý async hoàn tất, khiến assertion kiểm database thất bại không ổn định.
Một hệ thống dùng mock JmsTemplate trong unit test và thấy mọi send thành công, nhưng cấu hình destination resolver thực tế sai khiến integration test với broker thất bại.
Một nhóm dùng Testcontainers cho broker JMS trong CI nhưng không khởi tạo destination giống production, khiến các ca selector và quyền truy cập không được kiểm tra đúng.
Một dịch vụ kiểm thử listener với message String đơn giản, nhưng payload JSON sai type-id chỉ xuất hiện từ producer cũ nên nhánh lỗi converter không được đánh giá.
Một ứng dụng chỉ test @JmsListener với một consumer, khiến bug xử lý trùng do tăng concurrency không được phát hiện trước khi triển khai nhiều Pod.
Một nhóm kiểm thử listener container với AUTO_ACKNOWLEDGE nhưng production dùng session transacted, khiến kết quả thử lỗi và redelivery không phản ánh cấu hình vận hành.
Một hệ thống kiểm thử gửi vào queue và đọc ra ngay nhưng không mô phỏng broker restart, khiến các giả định về deliveryMode và mất message chưa được xác nhận.
Một dịch vụ có bài test request-reply chỉ một request mỗi lần, khiến lỗi correlation ID bị ghép nhầm khi chạy hàng trăm request đồng thời không được phát hiện.
Một nhóm dựng test cho durable subscription với một client ID cố định, khiến khi chạy song song nhiều test context chúng tranh chấp danh tính trên cùng broker.
Một ứng dụng test message selector bằng JMS properties tạo từ cùng service, nhưng không có fixture từ đối tác với khác biệt kiểu dữ liệu nên production lọc sai.
Một hệ thống kiểm thử kết nối broker ổn định nhưng không mô phỏng disconnect giữa transaction, khiến kết quả commit chưa rõ ràng và retry trùng không được đánh giá.
Một dịch vụ dùng mock listener trực tiếp thay vì listener container Spring, khiến annotation destination, conversion và acknowledgement không được chạy trong bài test.
Một nhóm chạy integration test JMS với container factory không bật transaction, nhưng luồng production dùng JmsTransactionManager nên assertion rollback trong test thiếu căn cứ.
Một hệ thống có DLQ cho message lỗi nhưng test không xác minh chính sách redelivery của broker, khiến poison message thực tế lặp lại lâu hơn thời gian giám sát.
Một ứng dụng chỉ kiểm HTTP response sau thao tác JmsTemplate.send, khiến suite không biết downstream listener có xử lý thành công hay chỉ nhận được message vào queue.
Một dịch vụ sử dụng chung broker namespace giữa các bộ test song song, khiến test này tiêu thụ message của test kia và kết quả CI không ổn định.
Một nhóm benchmark lượng message gửi bằng JmsTemplate nhưng không đo tốc độ xử lý của listener container, khiến đánh giá throughput chỉ phản ánh producer chứ không phải luồng toàn hệ thống.
Một hệ thống có chương trình replay DLQ để phục hồi dữ liệu, nhưng bài test không kiểm trường hợp sự kiện đã được xử lý một phần nên replay có thể tạo tác dụng phụ lặp.
