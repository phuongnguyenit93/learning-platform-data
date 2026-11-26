Trong những bài toán tích hợp nào bạn sẽ lựa chọn ActiveMQ để truyền thông điệp bất đồng bộ?
Bạn đánh giá các tiêu chí nào khi chọn broker thay cho lời gọi HTTP đồng bộ giữa các dịch vụ?
Bạn phân biệt trách nhiệm của producer, broker và consumer trong một luồng thông điệp như thế nào?
Bạn mô tả đường đi của một thông điệp từ ứng dụng Java gửi đến lúc được xử lý thành công ra sao?
Bạn lựa chọn ActiveMQ Classic hay ActiveMQ Artemis dựa trên yêu cầu kiến trúc và vận hành nào?
Bạn phân tích những khác biệt kiến trúc quan trọng giữa ActiveMQ Classic và Artemis như thế nào?
Bạn lập kế hoạch đánh giá di chuyển từ Classic sang Artemis cho một hệ thống đang hoạt động ra sao?
Bạn xác định nhu cầu tương thích giao thức khi lựa chọn broker cho nhiều nền tảng ứng dụng như thế nào?
Bạn phân biệt vai trò của JMS API và giao thức kết nối thực tế với broker ra sao?
Bạn mô tả các giới hạn của JMS khi nhiều ứng dụng không viết bằng Java cùng trao đổi dữ liệu như thế nào?
Bạn phân biệt mô hình point-to-point và publish-subscribe trong ActiveMQ ra sao?
Bạn lựa chọn queue hay topic để truyền lệnh nghiệp vụ dựa trên những tiêu chí nào?
Bạn sử dụng topic để phát sự kiện cho nhiều dịch vụ độc lập như thế nào?
Bạn phân tích ảnh hưởng của việc tăng số consumer trên cùng một queue đối với phân phối thông điệp ra sao?
Vì sao một topic với nhiều subscriber có hành vi khác queue với nhiều consumer?
Bạn xác định cách đặt tên destination để các nhóm dịch vụ dễ quản lý và tránh xung đột ra sao?
Bạn tổ chức namespace cho các queue và topic theo miền nghiệp vụ như thế nào?
Bạn lựa chọn tạo destination bằng mã ứng dụng hay khai báo trước trên broker dựa trên tiêu chí nào?
Bạn quản lý vòng đời destination khi một dịch vụ không còn sử dụng nó như thế nào?
Bạn xác định quy ước hợp đồng thông điệp để producer và consumer có thể phát triển độc lập ra sao?
Bạn lựa chọn schema JSON, Avro hay Protobuf cho payload ActiveMQ theo nhu cầu nào?
Bạn thiết kế message envelope gồm các trường nào để hỗ trợ truy vết và tương thích phiên bản?
Bạn phân biệt message ID do broker gán với định danh sự kiện nghiệp vụ như thế nào?
Bạn quản lý thay đổi schema thông điệp khi consumer cũ và mới chạy song song ra sao?
Bạn xử lý consumer nhận loại sự kiện chưa được hỗ trợ mà không làm nghẽn queue như thế nào?
Bạn mô tả ranh giới giữa hợp đồng message và logic xử lý nghiệp vụ trong consumer ra sao?
Bạn đánh giá các rủi ro khi nhiều dịch vụ cùng dùng một Java class làm hợp đồng message như thế nào?
Bạn phân biệt một sự kiện đã phát sinh với một lệnh yêu cầu thực hiện hành động qua ví dụ nào?
Bạn thiết kế quy ước metadata cho correlation ID, event time và source service ra sao?
Bạn xác định những trường dữ liệu nhạy cảm không được đưa vào payload hoặc message properties như thế nào?
Bạn mô tả chức năng của ConnectionFactory, Connection, Session, Destination, Producer và Consumer trong JMS ra sao?
Bạn thiết lập kết nối JMS từ ứng dụng Java đến ActiveMQ theo từng môi trường như thế nào?
Bạn lựa chọn tạo JMSContext hay sử dụng Connection và Session theo kiểu truyền thống dựa trên yếu tố nào?
Bạn tổ chức vòng đời JMS Connection và Session để tránh rò rỉ tài nguyên như thế nào?
Bạn xử lý giới hạn thread-safety của JMS Session khi triển khai nhiều worker Java ra sao?
Bạn đánh giá cách dùng connection pooling để giảm chi phí thiết lập kết nối như thế nào?
Bạn quyết định số lượng connection, session và consumer theo năng lực xử lý của ứng dụng ra sao?
Bạn tạo queue và topic bằng JMS API trong trường hợp nào?
Bạn tạo MessageProducer và gửi message đến destination trong Java như thế nào?
Bạn phân biệt TextMessage, BytesMessage, MapMessage và ObjectMessage về khả năng tương thích và bảo mật ra sao?
Bạn lựa chọn định dạng serialization thay cho ObjectMessage khi các dịch vụ khác phiên bản hoặc ngôn ngữ như thế nào?
Bạn bổ sung JMS properties vào message để phục vụ định tuyến và lọc ra sao?
Bạn sử dụng JMSCorrelationID và JMSReplyTo để xây dựng luồng request-reply như thế nào?
Bạn thiết kế timeout khi chờ phản hồi JMS request-reply để không giữ tài nguyên vô hạn ra sao?
Bạn quản lý temporary queue hoặc temporary topic trong mô hình request-reply như thế nào?
Bạn lựa chọn synchronous receive hay MessageListener bất đồng bộ theo đặc điểm tải nào?
Bạn triển khai MessageListener để tách nhận message và thực thi nghiệp vụ như thế nào?
Bạn xử lý ngoại lệ trong callback JMS consumer để message không bị xác nhận nhầm ra sao?
Bạn tổ chức consumer Java có thể dừng an toàn khi vẫn còn message đang xử lý như thế nào?
Bạn chọn thời điểm start và stop của JMS Connection để kiểm soát nhận message ra sao?
Bạn thiết kế cơ chế tái kết nối khi ActiveMQ broker tạm thời mất liên lạc như thế nào?
Bạn kiểm soát việc các instance consumer đồng loạt kết nối lại sau một sự cố broker ra sao?
Bạn phân biệt JMS headers chuẩn với application properties trong hợp đồng message như thế nào?
Bạn sử dụng JMSDeliveryMode để lựa chọn thông điệp persistent và non-persistent trong tình huống nào?
Bạn giải thích những điều kiện ảnh hưởng đến độ bền của persistent message qua một lần broker restart như thế nào?
Bạn lựa chọn JMSPriority dựa trên yêu cầu xử lý ưu tiên và giới hạn thực tế của broker ra sao?
Bạn cấu hình thời hạn sống message và xử lý message hết hạn như thế nào?
Bạn so sánh JMSExpiration với thời hạn còn hiệu lực của một hành động nghiệp vụ như thế nào?
Bạn phân biệt JMSRedelivered với bằng chứng message đã từng được xử lý nghiệp vụ như thế nào?
Bạn sử dụng JMSXDeliveryCount để quyết định cách xử lý redelivery theo những lưu ý nào?
Bạn thiết kế message selector để mỗi consumer nhận đúng loại message như thế nào?
Bạn đánh giá chi phí của selector khi một queue hoặc topic có số lượng message lớn ra sao?
Bạn phân biệt lọc thông điệp bằng JMS selector và tách riêng destination theo chủ đề như thế nào?
Bạn tổ chức durable subscription cho một topic khi subscriber có thể offline ra sao?
Bạn phân tích sự khác nhau giữa durable và non-durable topic subscription về lưu trữ message như thế nào?
Bạn quản lý client ID và subscription name để tránh xung đột durable subscriber ra sao?
Bạn quyết định sử dụng shared subscription trong JMS khi cần mở rộng xử lý một topic như thế nào?
Bạn đánh giá những giới hạn về ordering khi nhiều consumer cùng nhận từ một shared subscription ra sao?
Bạn lựa chọn cách xóa durable subscription khi ứng dụng ngừng hoạt động vĩnh viễn như thế nào?
Bạn xác định hành vi khi một durable subscriber offline quá lâu và backlog tăng mạnh ra sao?
Bạn tổ chức message grouping để các message cùng một thực thể được xử lý có thứ tự như thế nào?
Bạn sử dụng JMSXGroupID và quản lý việc chuyển quyền xử lý nhóm giữa các consumer ra sao?
Bạn phân biệt tính thứ tự trong một queue với thứ tự hoàn tất xử lý ở nhiều consumer như thế nào?
Bạn nhận diện các điều kiện redelivery làm thay đổi thứ tự message như thế nào?
Bạn thiết kế consumer có khả năng idempotent khi broker có thể giao lại message ra sao?
Bạn lựa chọn khóa deduplication theo event ID, message ID hoặc business key dựa trên tiêu chí nào?
Bạn xử lý trường hợp hai bản sao consumer nhận message trùng nhau gần như đồng thời bằng cách nào?
Bạn phân biệt chế độ AUTO_ACKNOWLEDGE và CLIENT_ACKNOWLEDGE về thời điểm xác nhận ra sao?
Bạn sử dụng DUPS_OK_ACKNOWLEDGE trong trường hợp nào và đánh đổi độ tin cậy như thế nào?
Bạn giải thích ảnh hưởng của CLIENT_ACKNOWLEDGE đến các message đã được tiêu thụ trong cùng session ra sao?
Bạn quyết định khi nào sử dụng session transacted thay cho chế độ acknowledgment thông thường?
Bạn phân tích tình huống consumer ghi database thành công nhưng chết trước khi acknowledgment như thế nào?
Bạn xử lý message có cùng event ID nhưng payload mâu thuẫn với lần nhận trước như thế nào?
Bạn xử lý trường hợp consumer ack thành công nhưng tác dụng phụ bên ngoài chưa hoàn tất như thế nào?
Bạn sử dụng Session.recover để khôi phục luồng message trong trường hợp lỗi nào?
Bạn lựa chọn rollback một JMS transaction khi xử lý message thất bại ra sao?
Bạn giải thích cách commit của JMS transacted session tác động đến việc gửi và nhận message như thế nào?
Bạn so sánh local JMS transaction với transaction của database trong một giao dịch tích hợp ra sao?
Bạn đánh giá rủi ro khi commit database và xác nhận JMS message trong hai bước riêng biệt như thế nào?
Bạn sử dụng transactional outbox để tránh mất sự kiện giữa ghi database và gửi message ra sao?
Bạn thiết kế inbox table để theo dõi và loại bỏ việc xử lý trùng message như thế nào?
Bạn quyết định khi nào cần XA hoặc JTA distributed transaction và những đánh đổi liên quan ra sao?
Bạn xử lý recovery của giao dịch phân tán khi coordinator hoặc broker gặp sự cố như thế nào?
Bạn giải thích ý nghĩa thực tế của at-most-once và at-least-once delivery trong JMS ra sao?
Bạn đánh giá tuyên bố exactly-once processing khi consumer gọi một dịch vụ bên ngoài như thế nào?
Bạn xây dựng chiến lược xử lý một message đã thực hiện một phần nghiệp vụ trước khi lỗi ra sao?
Bạn xử lý tác vụ có side effect không thể rollback bằng các cơ chế bù trừ như thế nào?
Bạn thiết kế producer retry khi không biết broker đã nhận message trước khi mất kết nối hay chưa ra sao?
Bạn phân biệt bảo đảm gửi thành công của producer với bảo đảm consumer xử lý thành công như thế nào?
Bạn quyết định cách đo và đối soát số message đã phát với số tác vụ nghiệp vụ đã hoàn tất ra sao?
Bạn lựa chọn đồng bộ hoặc bất đồng bộ khi producer gửi message theo yêu cầu throughput như thế nào?
Bạn xử lý callback gửi bất đồng bộ để nhận biết thành công hoặc lỗi publish như thế nào?
Bạn giới hạn số message đang chờ xác nhận khi producer gửi với tốc độ cao ra sao?
Bạn áp dụng cơ chế backpressure khi upstream tạo sự kiện nhanh hơn broker tiếp nhận như thế nào?
Bạn xác định giới hạn kích thước message để tránh làm nghẽn kết nối và bộ nhớ broker ra sao?
Bạn lựa chọn nén dữ liệu, chia message hay gửi tham chiếu đến object storage trong tình huống nào?
Bạn thiết kế retry policy của consumer dựa trên lỗi tạm thời và lỗi dữ liệu không thể xử lý như thế nào?
Bạn phân biệt redelivery tại broker với retry ngay bên trong tiến trình consumer ra sao?
Bạn thiết lập số lần redelivery tối đa để tránh poison message chiếm tài nguyên như thế nào?
Bạn dùng delay và exponential backoff cho redelivery để giảm áp lực lên hệ thống downstream ra sao?
Bạn dựa trên những điều kiện nào để chuyển một message sang dead-letter queue?
Bạn phân biệt dead-letter queue với queue lưu message hết hạn trong thiết kế vận hành ra sao?
Bạn cấu hình và kiểm tra dead-letter behavior của ActiveMQ Classic theo broker policy như thế nào?
Bạn cấu hình dead-letter address và dead-letter queue trong Artemis ra sao?
Bạn lựa chọn cách đặt tên và phân vùng DLQ theo queue gốc hoặc nhóm ứng dụng như thế nào?
Bạn lưu những metadata nào khi message chuyển vào DLQ để hỗ trợ điều tra và replay?
Bạn kiểm tra số lần redelivery và nguyên nhân lỗi khi phân tích một message trong DLQ ra sao?
Bạn ngăn vòng lặp xử lý lại giữa queue chính và DLQ bằng cơ chế nào?
Bạn thiết kế quy trình replay message từ DLQ mà không tạo tác dụng phụ trùng lặp như thế nào?
Bạn xác định những bước xác minh cần làm trước khi replay hàng loạt message lỗi ra sao?
Bạn quản lý quyền thực hiện replay, purge và move message trong công cụ vận hành như thế nào?
Bạn xác định thời hạn lưu giữ message chưa xử lý và message trong DLQ dựa trên yêu cầu nào?
Bạn xử lý message hết hạn trước khi consumer bắt đầu xử lý nghiệp vụ như thế nào?
Bạn kiểm soát tác động của delayed delivery và scheduled messages đến thứ tự xử lý ra sao?
Bạn dùng các cơ chế scheduled delivery được hỗ trợ theo từng broker để trì hoãn message như thế nào?
Bạn phân biệt cấu hình redelivery ở phía client và phía broker trong Classic và Artemis ra sao?
Bạn đánh giá tác động của việc tăng retry count đối với độ trễ hoàn tất nghiệp vụ như thế nào?
Bạn giám sát tỷ lệ redelivery và số message vào DLQ để phát hiện lỗi ứng dụng như thế nào?
Bạn phân tích cách một lỗi deserialize lặp lại có thể làm nghẽn pipeline message ra sao?
Bạn thiết kế chính sách xử lý message có schema không tương thích sau khi triển khai phiên bản mới như thế nào?
Bạn giải thích mô hình address, routing type và queue của ActiveMQ Artemis như thế nào?
Bạn phân biệt anycast và multicast routing trong Artemis qua ví dụ queue và publish-subscribe ra sao?
Bạn thiết kế address với nhiều queue và routing type khác nhau trong Artemis như thế nào?
Bạn sử dụng fully qualified queue name của Artemis khi cần truy cập queue cụ thể ra sao?
Bạn quyết định thời điểm khai báo address và queue tường minh thay vì cho phép auto-create như thế nào?
Bạn xử lý việc client tạo destination mới không nằm trong chính sách broker như thế nào?
Bạn phân tích vai trò của address settings trong quản lý queue, expiry và DLQ của Artemis ra sao?
Bạn giải thích cơ chế paging của Artemis khi tổng dung lượng message vượt giới hạn bộ nhớ như thế nào?
Bạn lựa chọn address-full-policy trong Artemis dựa trên yêu cầu bảo vệ tài nguyên và tránh mất dữ liệu nào?
Bạn kiểm tra journal storage của Artemis để đánh giá độ bền và throughput ra sao?
Bạn phân tích ảnh hưởng của journal, paging và large-message storage đối với hiệu năng Artemis như thế nào?
Bạn cấu hình redistribution hoặc message balancing trong Artemis cluster để cải thiện chia tải ra sao?
Bạn phân biệt core protocol của Artemis với JMS API được ứng dụng Java sử dụng như thế nào?
Bạn đánh giá tương thích AMQP, STOMP và các giao thức khác khi cấu hình acceptor của Artemis ra sao?
Bạn thiết kế các connector và acceptor của Artemis để phân tách traffic và vùng bảo mật như thế nào?
Bạn sử dụng broker plugin hoặc interceptor của Artemis khi cần một quy tắc xử lý dùng chung ra sao?
Bạn phân tích cách Artemis xử lý consumer chậm khi queue backlog tăng như thế nào?
Bạn lập kế hoạch backup và phục hồi dữ liệu broker Artemis với yêu cầu RPO, RTO như thế nào?
Bạn giải thích vai trò của transport OpenWire trong kết nối ứng dụng với ActiveMQ Classic ra sao?
Bạn thiết kế Virtual Topic trong ActiveMQ Classic để nhiều consumer group nhận cùng sự kiện như thế nào?
Bạn phân biệt Virtual Topic với durable topic subscription trong Classic về routing và cách chia tải như thế nào?
Bạn cấu hình destination policy của Classic để kiểm soát prefetch, memory và dead-letter routing ra sao?
Bạn xác định tác động của KahaDB đến độ bền và hiệu năng ActiveMQ Classic như thế nào?
Bạn đánh giá cách cấu hình broker persistence adapter của Classic theo yêu cầu lưu trữ như thế nào?
Bạn phát hiện memory limit hoặc store limit trên Classic đang gây flow control bằng cách nào?
Bạn tổ chức wildcard destinations và selectors trong Classic để tránh subscription quá rộng ra sao?
Bạn kiểm tra phiên bản giao thức và thư viện client khi di chuyển ứng dụng từ Classic sang Artemis như thế nào?
Bạn xác định những cấu hình và tính năng đặc thù Classic cần được thay thế khi chuyển sang Artemis ra sao?
Bạn xây dựng phép thử so sánh hành vi queue, topic và redelivery giữa Classic và Artemis như thế nào?
Bạn xử lý khác biệt trong tên destination và auto-creation khi chuyển từ Classic sang Artemis ra sao?
Bạn xác định các cam kết về backward compatibility trước khi thay đổi broker mà không đổi mã consumer ra sao?
Bạn chọn cách triển khai một broker độc lập hay một cụm theo mục tiêu chịu lỗi như thế nào?
Bạn phân biệt high availability, failover và load balancing của hệ thống ActiveMQ ra sao?
Bạn thiết kế cơ chế failover của Java client để chuyển sang broker khả dụng như thế nào?
Bạn kiểm tra điều gì để tránh gửi message trùng khi client kết nối lại sau khi broker chuyển vai trò?
Bạn lựa chọn replication hay shared-store cho cấu hình HA Artemis dựa trên hạ tầng nào?
Bạn phân tích điều kiện kích hoạt failover của Artemis khi node primary gặp sự cố như thế nào?
Bạn đánh giá khả năng mất dữ liệu khi vùng lưu trữ của broker bị hỏng hoặc bị mất kết nối ra sao?
Bạn xây dựng kịch bản chuyển đổi broker trong giờ cao điểm để đo tác động tới producer và consumer như thế nào?
Bạn thiết kế topology cluster và network bridges dựa trên phạm vi kết nối của các ứng dụng như thế nào?
Bạn phân biệt cluster connection của Artemis với network of brokers trong Classic như thế nào?
Bạn quản lý tình huống chia cắt mạng để tránh các node đưa ra quyết định mâu thuẫn ra sao?
Bạn tính toán dung lượng cần dự phòng khi một node trong cụm ngừng hoạt động như thế nào?
Bạn xác định chiến lược nâng cấp từng node ActiveMQ mà không gián đoạn message flow ra sao?
Bạn kiểm tra tương thích client, broker và định dạng lưu trữ trước khi nâng cấp như thế nào?
Bạn thiết kế quy trình rollback sau khi nâng cấp broker có thay đổi dữ liệu persisted ra sao?
Bạn lập phương án phục hồi khi toàn bộ broker cluster không thể khởi động như thế nào?
Bạn đánh giá lựa chọn kết nối giữa nhiều data center về độ trễ, băng thông và độ tin cậy ra sao?
Bạn kiểm soát thứ tự xử lý và nguy cơ trùng message trong quá trình failover như thế nào?
Bạn xây dựng kế hoạch kiểm thử thảm họa cho hệ thống ActiveMQ dựa trên RTO và RPO như thế nào?
Bạn lựa chọn các cơ chế xác thực broker phù hợp với Java clients và chính sách tổ chức như thế nào?
Bạn thiết kế người dùng, role và quyền truy cập queue/topic theo nguyên tắc ít quyền nhất ra sao?
Bạn phân biệt quyền tạo destination, gửi và tiêu thụ message trong mô hình phân quyền của broker như thế nào?
Bạn cấu hình TLS cho kết nối ActiveMQ và xác minh danh tính server như thế nào?
Bạn triển khai xác thực hai chiều bằng client certificate trong trường hợp nào?
Bạn quản lý keystore, truststore và quy trình gia hạn chứng chỉ khi nhiều ứng dụng cùng kết nối ra sao?
Bạn lưu trữ và xoay vòng thông tin đăng nhập producer và consumer mà không ghi secret vào cấu hình công khai như thế nào?
Bạn phân tách quyền quản trị broker với quyền của ứng dụng gửi và nhận message ra sao?
Bạn giới hạn truy cập Web Console và cổng quản trị JMX để giảm bề mặt tấn công như thế nào?
Bạn bảo vệ payload chứa dữ liệu cá nhân trong quá trình truyền và lưu trên broker như thế nào?
Bạn phân tích những rủi ro deserialization khi consumer nhận ObjectMessage từ nguồn không tin cậy ra sao?
Bạn áp dụng allowlist kiểu dữ liệu hoặc định dạng thông điệp an toàn để giảm rủi ro thực thi mã như thế nào?
Bạn kiểm soát quyền truy cập DLQ chứa message có dữ liệu nhạy cảm như thế nào?
Bạn thiết kế cơ chế audit thay đổi broker configuration và quyền truy cập như thế nào?
Bạn xử lý việc thu hồi credential của một producer bị nghi ngờ xâm nhập mà vẫn duy trì các ứng dụng khác ra sao?
Bạn xác định những thông số nào cần theo dõi cho queue depth, enqueue rate và dequeue rate?
Bạn sử dụng số message đang chờ, message đã giao và message bị redelivery để đánh giá sức khỏe consumer ra sao?
Bạn phân biệt message backlog với sự cố publisher không thể gửi vào broker như thế nào?
Bạn đo end-to-end latency từ thời điểm publish đến khi nghiệp vụ hoàn tất bằng cách nào?
Bạn đánh giá tác động của prefetch đối với công bằng chia tải và tốc độ xử lý như thế nào?
Bạn lựa chọn prefetch phù hợp khi consumer xử lý các message có thời gian chạy khác nhau ra sao?
Bạn xử lý consumer chậm giữ nhiều message đã prefetch nhưng chưa xử lý như thế nào?
Bạn xác định bottleneck do CPU, ổ đĩa, network hay consumer bằng những metric nào?
Bạn quan sát memory usage, disk usage và paging của broker để phát hiện nguy cơ quá tải ra sao?
Bạn thiết kế cảnh báo khi DLQ tăng bất thường sau một bản phát hành như thế nào?
Bạn phân tích tỷ lệ persistent message và non-persistent message ảnh hưởng tới throughput ra sao?
Bạn thử nghiệm ảnh hưởng của message size và batching đến độ trễ gửi nhận như thế nào?
Bạn lựa chọn số lượng queue, topic và connection hợp lý để tránh tăng chi phí tài nguyên broker ra sao?
Bạn kiểm soát cardinality của metric khi nhiều tenant tạo destination động như thế nào?
Bạn sử dụng JMX, management API hoặc công cụ giám sát Artemis để quan sát broker như thế nào?
Bạn thiết kế dashboard so sánh tốc độ tạo backlog với tốc độ xử lý consumer ra sao?
Bạn dự báo thời gian xử lý hết backlog sau khi một dịch vụ downstream phục hồi như thế nào?
Bạn dùng distributed tracing và correlation ID để lần theo một message qua nhiều dịch vụ ra sao?
Bạn xác định chính sách logging để hỗ trợ điều tra nhưng không lưu payload nhạy cảm như thế nào?
Bạn thiết kế runbook phản ứng khi broker kích hoạt flow control hoặc hết dung lượng lưu trữ ra sao?
Bạn cấu hình Spring JMS với ConnectionFactory cho ActiveMQ Classic hoặc Artemis như thế nào?
Bạn sử dụng JmsTemplate để gửi message và quản lý conversion trong Spring như thế nào?
Bạn triển khai @JmsListener để xử lý message và chuyển quyền điều khiển sang service nghiệp vụ ra sao?
Bạn chọn concurrency và acknowledge mode của listener container dựa trên yêu cầu nào?
Bạn cấu hình giao dịch cho JMS listener trong Spring để xử lý lỗi nhất quán như thế nào?
Bạn phối hợp Spring transaction với thao tác database và JMS như thế nào?
Bạn xử lý retry và message đi vào DLQ khi @JmsListener ném exception ra sao?
Bạn triển khai MessageConverter để chuyển giữa DTO và JMS message đúng hợp đồng như thế nào?
Bạn ngăn Java consumer Spring xử lý lại sự kiện đã ghi nhận bằng một kho idempotency như thế nào?
Bạn tổ chức graceful shutdown của listener container trong lúc còn message đang thực thi ra sao?
Bạn viết integration test JMS producer và consumer với broker ActiveMQ thực như thế nào?
Bạn tạo fixture cho Classic hoặc Artemis để kiểm tra hành vi broker cụ thể ra sao?
Bạn kiểm thử AUTO_ACKNOWLEDGE và CLIENT_ACKNOWLEDGE khi consumer cố ý ném lỗi như thế nào?
Bạn mô phỏng consumer chết ngay sau khi commit database nhưng trước khi ack để kiểm tra idempotency ra sao?
Bạn kiểm tra JMS transaction rollback khiến message được giao lại như thế nào?
Bạn viết test cho durable topic subscription khi subscriber offline rồi kết nối lại ra sao?
Bạn kiểm thử selector để phát hiện message bị chuyển sai destination hoặc sai consumer như thế nào?
Bạn mô phỏng poison message và xác minh cơ chế giới hạn redelivery rồi chuyển DLQ ra sao?
Bạn kiểm thử replay DLQ mà không lặp lại các tác dụng phụ nghiệp vụ bằng cách nào?
Bạn đo thông lượng và p95 latency của Classic so với Artemis trong cùng bộ traffic như thế nào?
Bạn xây dựng load test với nhiều producer, consumer và các kích thước message khác nhau ra sao?
Bạn tạo test mất kết nối broker trong lúc producer đang gửi message như thế nào?
Bạn kiểm thử failover khi primary Artemis bị tắt đột ngột và xác minh message không bị bỏ sót ra sao?
Bạn thực hiện test broker restart khi còn nhiều persistent message chưa tiêu thụ như thế nào?
Bạn kiểm thử độ ổn định ordering khi có nhiều consumer và xảy ra redelivery như thế nào?
Bạn mô phỏng chậm disk I/O hoặc broker paging để kiểm tra backpressure của producer ra sao?
Bạn kiểm thử TLS, xác thực và phân quyền cho ứng dụng producer và consumer như thế nào?
Bạn thiết kế tiêu chí pass/fail cho một bài kiểm thử độ tin cậy ActiveMQ như thế nào?
Nếu queue tăng liên tục dù consumer còn kết nối, bạn sẽ điều tra những nguyên nhân nào theo thứ tự?
Nếu producer báo gửi thành công nhưng consumer không thấy message, bạn sẽ kiểm tra destination và transaction ra sao?
Nếu một message bị xử lý hai lần sau khi consumer restart, bạn sẽ xác định nguyên nhân và biện pháp khắc phục như thế nào?
Nếu topic subscriber mất kết nối nhiều giờ rồi trở lại, bạn sẽ xác nhận việc nhận bù message bằng cách nào?
Nếu một consumer giữ quá nhiều message vì prefetch cao, bạn sẽ điều chỉnh để chia tải công bằng ra sao?
Nếu một payload không deserialize được và liên tục quay lại queue, bạn sẽ cô lập và sửa luồng xử lý như thế nào?
Nếu broker chuyển sang trạng thái flow control trong giờ cao điểm, bạn sẽ xác định nguyên nhân nghẽn ở đâu?
Nếu DLQ tăng nhanh sau khi cập nhật schema sự kiện, bạn sẽ điều tra tương thích producer-consumer ra sao?
Nếu giao dịch database đã commit nhưng JMS transaction rollback, bạn sẽ bảo vệ dữ liệu khỏi tác dụng phụ trùng như thế nào?
Nếu cluster Artemis mất node primary, bạn sẽ đối soát message tồn đọng sau failover ra sao?
Nếu Classic dùng Virtual Topic được chuyển sang Artemis, bạn sẽ kiểm chứng routing và consumer group như thế nào?
Nếu một queue cần bảo đảm thứ tự theo customer ID nhưng vẫn mở rộng nhiều consumer, bạn sẽ thiết kế lại phân phối ra sao?
Nếu một tenant tạo hàng nghìn queue làm broker thiếu tài nguyên, bạn sẽ đặt giới hạn và xử lý thế nào?
Nếu management console bị truy cập trái phép, bạn sẽ thu hồi quyền và kiểm tra ảnh hưởng tới broker ra sao?
Nếu ổ đĩa broker gần đầy trong lúc queue còn rất nhiều message quan trọng, bạn sẽ ưu tiên hành động nào?
Nếu producer và consumer sử dụng phiên bản JMS khác nhau, bạn sẽ kiểm tra khả năng tương thích bằng cách nào?
Nếu hệ thống cần khôi phục sau nhiều giờ broker gián đoạn, bạn sẽ sắp xếp thứ tự phục hồi publisher, broker và consumer ra sao?
Bạn thiết kế một checklist vận hành trước khi phát hành thay đổi lớn trên ActiveMQ như thế nào?
