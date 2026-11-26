Một nền tảng bán lẻ dùng Spring Cloud Stream khai báo Supplier phát sự kiện giá mỗi phút; sau khi scale ứng dụng lên ba replica, mọi replica cùng phát dữ liệu cho một sản phẩm và consumer ghi nhận ba lần cập nhật.
Nhóm triển khai Supplier lấy dữ liệu từ database theo lịch poller; khi một đợt đọc mất lâu hơn chu kỳ polling, nhiều lần truy vấn chồng nhau và những sản phẩm vừa cập nhật bị phát lặp.
Một ứng dụng báo cáo dùng Supplier sinh thông điệp từ bộ nhớ đệm; khi không có dữ liệu mới, hàm phát giá trị không phù hợp khiến binder vẫn cố gửi sự kiện rỗng tới broker.
Đội phát triển chuyển Supplier đồng bộ sang nguồn reactive phát Flux; sau khi deploy, ứng dụng giữ một subscription dài hạn nhưng nhóm vận hành vẫn kỳ vọng poller kích hoạt từng lần như trước.
Một dịch vụ giỏ hàng có Function nhận sự kiện đặt hàng và tạo thông báo; khi thêm một hàm khác vào ứng dụng, cấu hình function definition thiếu rõ ràng làm binding đầu vào không gắn với hàm cần chạy.
Nhóm xử lý hóa đơn kết hợp hai Function chuyển đổi rồi kiểm tra nghiệp vụ; sau lần đổi thứ tự composition, sự kiện được gửi sang topic đích dù chưa trải qua kiểm tra hợp lệ.
Một ứng dụng có Consumer đọc sự kiện thanh toán và ghi vào database; Consumer bắt lỗi rồi kết thúc bình thường khiến binder coi thông điệp đã được xử lý dù giao dịch không được lưu.
Nhóm phát triển dùng Function chỉ để lọc sự kiện không liên quan; một nhánh trả kết quả rỗng khiến downstream không nhận thông điệp, nhưng dashboard lại tính mọi message đầu vào như đã được xuất ra.
Ứng dụng Spring Cloud Stream khai báo nhiều bean Consumer cho cùng loại event; khi không chỉ định tên hàm trong cấu hình, một consumer không tạo binding như đội phát triển mong đợi.
Đội vận hành thêm Function xử lý trạng thái đơn hàng vào cấu hình nhiều hàm; tên binding sinh tự động thay đổi nên cấu hình destination cũ không còn áp dụng.
Một microservice đặt tên input binding theo quy ước cũ của dự án; sau khi chuyển sang mô hình functional, thông điệp không đi vào Consumer mặc dù broker vẫn nhận dữ liệu.
Nhóm tích hợp áp dụng tên binding tùy biến cho một Function; cấu hình consumer group lại trỏ tới tên binding mặc định khiến các pod tham gia group ngoài dự định.
Ứng dụng chuyển đổi dữ liệu bằng Function nhưng method signature sử dụng kiểu payload khác schema broker; luồng được khởi tạo thành công nhưng ném lỗi khi nhận sự kiện đầu tiên.
Một Consumer xử lý Message có cả header và payload; khi refactor sang nhận đối tượng nghiệp vụ trực tiếp, mã định danh tương quan bị mất và không thể ghép log với sự kiện nguồn.
Dịch vụ thông báo sử dụng Function trả một message đã có header routing; sau khi thêm middleware, header điều hướng không được giữ và thông điệp đi sang destination mặc định.
Một ứng dụng kết hợp Function xác thực với Function biến đổi; đường đi lỗi tạo event không hợp lệ nhưng không có output binding dành cho sự kiện từ chối.
Nhóm dùng StreamBridge để phát sự kiện tới destination được chọn khi runtime; một tên destination được xây từ dữ liệu khách hàng làm phát sinh hàng trăm topic hoặc queue ngoài kế hoạch.
Dịch vụ xử lý giao dịch gọi StreamBridge ngay sau khi nhận HTTP request; khi broker tạm ngừng, API đã trả thành công nhưng event không được gửi và đơn hàng không đi tiếp được.
Một ứng dụng Spring Cloud Stream thêm output binding mới chỉ ở environment production; bộ test dùng cấu hình dev không phát hiện message bị gửi tới destination khác tên.
Nhóm cấu hình hai binder cùng loại Kafka cho hai cụm độc lập; một output binding lấy binder mặc định và gửi dữ liệu khách hàng thử nghiệm sang cụm production.
Một dịch vụ nhận thanh toán từ Kafka rồi phát thông báo qua RabbitMQ; cấu hình binder của output bị gắn nhầm sang Kafka khiến backend thông báo không nhận được message.
Đội phát triển dùng binder RabbitMQ cho các thông báo ưu tiên nhưng không nhận ra khác biệt về định tuyến của exchange và queue; Consumer đã khởi động mà không có sự kiện nào đến.
Một ứng dụng gửi event qua Pulsar binder đồng thời giữ Kafka binder để tương thích dịch vụ cũ; một binding được chỉ định sai binder khiến payload phát hành vào hệ thống không có consumer.
Nhóm vận hành thay destination của một binding từ topic v1 sang topic v2; một consumer group vẫn đọc v1 và báo không có dữ liệu dù publisher đã chuyển sang v2.
Ứng dụng có hai input binding cùng trỏ một topic nhưng dùng cùng consumer group; các message được phân phối giữa hai Consumer thay vì mỗi Consumer nhận đủ dữ liệu.
Đội phát triển cấu hình consumer group dạng tạm thời để thử nghiệm; khi restart ứng dụng, group mới đọc lại nhiều event mà nhóm tưởng đã được xử lý từ lần chạy trước.
Một hệ thống audit cần mỗi ứng dụng nhận đầy đủ sự kiện; hai ứng dụng vô tình dùng cùng group ID và chỉ một trong hai lưu được từng message.
Nhóm triển khai ba replica của một Consumer Kafka nhưng topic chỉ có hai partition; replica thứ ba không được phân message dù pod báo readiness thành công.
Ứng dụng phân tích hành vi có một consumer group bị tăng số instance đột ngột; mỗi lần scale Kafka rebalance và thời gian xử lý tạm dừng khiến độ trễ sự kiện tăng.
Một dịch vụ nhận event trạng thái đơn hàng cần giữ thứ tự theo orderId; producer không dùng khóa ổn định nên các cập nhật của cùng đơn đi vào nhiều partition và bị xử lý sai trình tự.
Nhóm phát triển thay partition key từ customerId sang orderId; các sự kiện trong giai đoạn chuyển tiếp vẫn nằm ở partition cũ và thứ tự nghiệp vụ không còn được duy trì.
Một publisher dùng partition count trong cấu hình khác số partition thực tế ở Kafka; sau khi nâng số partition tại broker, phân bố message thay đổi và nhóm khó so sánh tải giữa consumer.
Đội vận hành cấu hình partitionKeyExpression dựa trên trường order.id; một loại sự kiện mới không có trường này khiến các message bị từ chối hoặc đi vào partition ngoài dự kiến.
Ứng dụng phân vùng message theo mã khách hàng nhưng mã có ký tự Unicode với cách chuẩn hóa khác nhau; các sự kiện cùng khách hàng có thể nhận khóa phân vùng khác khi phát từ hai hệ thống.
Một dịch vụ Kafka yêu cầu xử lý tuần tự các thay đổi tồn kho; consumer được tăng concurrency vượt số partition và phần tăng không cải thiện throughput như kỳ vọng.
Nhóm phát triển áp dụng partitioned consumer trong RabbitMQ binder; phương án phân phối hàng đợi khác Kafka khiến dữ liệu theo một khách hàng không giữ thứ tự như thiết kế ban đầu.
Một ứng dụng dùng Pulsar subscription kiểu Shared để tăng song song; hai sự kiện cập nhật trạng thái cùng đơn có thể đến các consumer khác nhau và bị xử lý ngược thứ tự.
Đội chuyển Pulsar subscription sang Key_Shared cho dữ liệu đơn hàng; khóa message bị thiếu ở một số publisher khiến việc phân phối theo khóa không hoạt động như mong muốn.
Một Consumer RabbitMQ dùng group định danh rõ ràng; khi đổi tên group trong bản release, queue mới được tạo và backlog của queue cũ không còn được ứng dụng nhận.
Ứng dụng Kafka có auto offset reset đặt theo cấu hình thử nghiệm; khi tạo consumer group mới ở production, nhiều sự kiện lịch sử bị bỏ qua ngoài dự kiến.
Nhóm xử lý sự kiện tài chính restart sau sự cố, nhưng offset đã được commit trước khi transaction database hoàn tất; một khoản thanh toán không còn được phát lại.
Một Consumer ghi dữ liệu thành công rồi crash trước khi xác nhận message; khi được giao lại, cùng event được áp dụng hai lần và tổng tiền bị cộng trùng.
Đội dùng acknowledgment thủ công cho một xử lý Kafka dài; code xác nhận trước khi hoàn tất API đối tác khiến những bản ghi lỗi mất cơ hội được giao lại.
Một ứng dụng RabbitMQ bật manual ack nhưng trong nhánh xử lý lỗi không ack hoặc nack; số message unacked tăng liên tục và queue ngừng cấp thêm việc.
Nhóm dùng Pulsar consumer nhận message bằng subscription riêng; một worker đóng đột ngột khi chưa ack khiến sự kiện được gửi lại và side effect đã thực hiện bị nhân đôi.
Một microservice kỳ vọng giao nhận at-least-once (ít nhất một lần) cho các event; sau khi nâng binder, nhóm vận hành thấy duplicate tăng nhưng không có event ID để xác định thông điệp lặp.
Ứng dụng ghi đơn hàng và phát sự kiện trong cùng API; database commit thành công nhưng producer không gửi được message vì broker mất kết nối ngay sau đó.
Nhóm tích hợp dùng outbox event trong bảng dữ liệu nghiệp vụ; worker phát sự kiện thành công rồi chết trước khi đánh dấu outbox đã gửi khiến message xuất hiện lại sau restart.
Đội phát triển dựa vào Kafka transaction để khẳng định tính exactly-once; Consumer còn gọi HTTP API ngoài transaction và đối tác vẫn nhận hai lệnh khi message bị phát lại.
Một pipeline đọc Kafka và ghi Kafka khác bật transaction; metadata của hệ thống quan sát cho thấy output đúng một lần nhưng việc cập nhật database bổ sung vẫn có thể bị lặp.
Ứng dụng xử lý event có eventId để chống trùng; key idempotency bị xóa khỏi database trước khi broker hết thời gian giữ message nên replay dài ngày áp dụng lại tác động cũ.
Nhóm chuyển consumer từ Kafka sang RabbitMQ mà giữ nguyên giả định về thứ tự và cơ chế ack; một số bản ghi bị xử lý lại ngoài trình tự khi worker gặp lỗi.
Một dịch vụ gửi 100.000 event trong đợt chốt sổ; producer timeout và retry cùng batch khiến số event trong topic lớn hơn số bản ghi nguồn dù hệ thống báo đã phát đủ.
Đội sử dụng message conversion tự động giữa JSON và đối tượng Java; publisher đổi tên field nhưng Consumer vẫn khởi động được và chỉ báo lỗi khi dữ liệu thực xuất hiện.
Ứng dụng khai báo contentType application/json cho input binding; một producer cũ gửi dữ liệu dạng chuỗi thuần khiến converter không thể deserialize các message tồn từ trước.
Một producer gửi payload Avro qua Kafka binder nhưng downstream kỳ vọng JSON; bản kiểm thử chỉ dùng object Java nội bộ nên không nhận ra khác biệt trên wire format.
Nhóm tích hợp thêm schema registry cho Avro event; bản producer mới tham chiếu schema ID mà consumer production chưa truy cập được và các sự kiện bị lỗi giải mã.
Một hệ thống chọn chiến lược schema evolution cho event OrderCreated; producer bỏ trường bắt buộc cũ và consumer ở vùng khác không thể giải mã khi rolling deployment.
Ứng dụng nhận sự kiện có schema version trong header; một binder không giữ header như dự kiến khiến consumer dùng version mặc định và đọc sai dữ liệu.
Đội phát triển thay kiểu price từ integer sang decimal; consumer cũ parse thành số không phù hợp, làm sai tổng tiền dù cấu trúc message nhìn vẫn hợp lệ.
Một sự kiện có trường timestamp không kèm timezone; các consumer ở hai region diễn giải thời gian khác nhau và đưa đơn vào hai kỳ tổng hợp.
Nhóm dùng CloudEvents để thống nhất format; producer mới đổi trường type và source, trong khi các consumer vẫn lọc theo header type cũ nên bỏ qua sự kiện.
Ứng dụng Kafka nhận tombstone record có value null trong topic compacted; converter của Spring Cloud Stream cố ánh xạ thành DTO và ném lỗi liên tục.
Một dịch vụ RabbitMQ nhận message chứa emoji và tiếng Việt; cấu hình charset không đồng nhất giữa hai ứng dụng khiến nội dung thông báo được lưu sai ký tự.
Đội dùng Pulsar schema JSON cho nhiều loại sự kiện; một publisher gửi kiểu dữ liệu mới không tương thích và broker từ chối message dù lớp nghiệp vụ đã xử lý thành công.
Ứng dụng di chuyển một event từ cấu trúc phẳng sang object lồng nhau; các Consumer được deploy không cùng lúc khiến một nhóm message phải được xử lý bởi phiên bản cũ.
Nhóm đưa dữ liệu cá nhân vào trường mở rộng của event cho mục đích gỡ lỗi; payload mới được gửi tới nhiều consumer không có quyền truy cập thông tin đó.
Dịch vụ bảo hiểm phát message có header tenantId và userId; khi chuyển nội dung từ Kafka sang RabbitMQ, một phần header không được bảo toàn và downstream truy cập nhầm dữ liệu.
Một event dùng correlation ID trong header để nối HTTP request với luồng xử lý bất đồng bộ; custom Function tạo Message mới nhưng đánh mất correlation ID ở output.
Nhóm truyền traceparent qua các binding; sau khi chèn một Function lọc dữ liệu, trace của các bước processing bị tách và không thể điều tra latency end-to-end.
Ứng dụng chuyển đổi dữ liệu phải ghi nhận source topic và offset để audit; Function chỉ giữ payload khiến đội vận hành không xác định được event đến từ nguồn nào.
Một Consumer tự động retry khi gọi database timeout; retry được cấu hình quá nhanh khiến hàng nghìn message cùng tạo áp lực vào database đang quá tải.
Nhóm cấu hình maxAttempts cho Consumer nhưng giả định áp dụng giống nhau trên Kafka và RabbitMQ; khi chuyển binder, số lần giao lại thực tế khác kỳ vọng của SLA.
Một event có dữ liệu vi phạm quy tắc nghiệp vụ không thể phục hồi; Consumer thử lại nhiều lần và chặn tiến trình xử lý các event hợp lệ phía sau.
Ứng dụng có RetryTemplate dùng backoff nhưng một lỗi ngoại lệ không được phân loại; message không hợp lệ bị thử lại tới giới hạn rồi vẫn không có dấu vết từ chối.
Đội vận hành bật DLQ cho binding Kafka; khi một message gây poison pill, payload được chuyển đi nhưng không có thông tin nguồn đủ để tái phát sau khi sửa lỗi.
Một Consumer RabbitMQ có DLQ được tạo tự động; chính sách expiration trên queue lỗi khiến các event chưa được xử lý bị xóa trước khi đội hỗ trợ điều tra.
Nhóm cho phép replay message từ DLQ về topic chính; cùng bản ghi thiếu trường bắt buộc bị lặp vòng vô hạn giữa luồng chính và luồng lỗi.
Một dịch vụ nhận thông điệp thanh toán quan trọng; worker chuyển message lỗi sang DLQ nhưng dashboard chỉ theo dõi queue chính nên nhóm vận hành không biết số giao dịch chưa hoàn tất.
Đội xử lý dữ liệu khách hàng tạo DLQ chung cho nhiều input binding; khi replay, không còn thông tin destination gốc và một số message được đẩy nhầm vào pipeline khác.
Ứng dụng Pulsar dùng dead-letter policy cho message thất bại; broker redelivery theo cơ chế riêng và báo retry count không khớp số lần gọi downstream trong log.
Một Consumer Kafka có native decoding lỗi ngay khi deserialize; xử lý lỗi của Function không được kích hoạt và message không tới luồng DLQ như đội phát triển mong đợi.
Nhóm xử lý RabbitMQ dùng requeue cho mọi exception; một message malformed liên tục quay lại đầu queue và làm các message khác bị đói xử lý.
Một dịch vụ nhận message có địa chỉ email sai định dạng; chính sách skip cho phép đi tiếp nhưng phần mềm báo mọi event đều thành công dù thiếu kết quả gửi thông báo.
Đội phát triển thay cấu hình consumer concurrency khi có backlog; một số message chưa ack bị redeliver và kết quả đếm thành công lớn hơn số giao dịch đầu vào.
Một nghiệp vụ hoàn tiền yêu cầu quy trình bù trừ khi downstream không khả dụng; consumer kết thúc sau retry và gửi DLQ nhưng hệ thống đặt hàng vẫn chờ kết quả vô thời hạn.
Nhóm vận hành cần phân biệt lỗi tạm thời với lỗi dữ liệu cố định; metrics đang gộp mọi exception của Consumer vào một loại nên không xác định được tỷ lệ retry hữu ích.
Ứng dụng dùng Kafka Streams binder để tổng hợp tổng tiền theo khách hàng; sau khi đổi khóa input từ userId sang accountId, kết quả stateful aggregation bị chia thành nhiều nhóm ngoài dự kiến.
Một pipeline Kafka Streams biến đổi KStream thành KTable để giữ trạng thái đơn hàng mới nhất; dữ liệu phát tới topic không có key nên các bản cập nhật không được lưu đúng thực thể.
Nhóm dùng KTable để tra cứu bảng giá từ một compacted topic; một producer gửi tombstone sai key làm thông tin giá của nhiều đơn biến mất khỏi state store.
Ứng dụng join KStream với KTable để bổ sung thông tin sản phẩm; sự kiện mua hàng đến trước bản cập nhật danh mục và kết quả join thiếu dữ liệu dù hai message đều có trên Kafka.
Đội dùng GlobalKTable cho dữ liệu tham chiếu trên nhiều instance; sau khi dataset tăng gấp mười lần, thời gian khởi động và dung lượng lưu state ở mỗi pod tăng đột biến.
Một hệ thống tổng hợp click theo time window; thiết bị di động gửi event muộn do mất mạng, khiến số lượt truy cập của một cửa sổ đã đóng không phản ánh giao dịch thực tế.
Nhóm Kafka Streams dùng event-time timestamp extractor nhưng nguồn dữ liệu đổi format timestamp; các sự kiện bị gắn thời điểm sai và rơi vào cửa sổ tổng hợp không đúng.
Ứng dụng dùng hopping window để tính doanh số theo từng năm phút; một giao dịch xuất hiện trong nhiều kết quả và báo cáo tổng cuối ngày cộng chồng sai.
Một pipeline đặt grace period cho late arrivals quá ngắn; event phát lại sau sự cố mạng không còn cập nhật kết quả tổng hợp và chênh lệch khó được phát hiện.
Đội phân tích xem kết quả aggregation theo cửa sổ thời gian; sau khi bật suppress, dashboard không có cập nhật tạm thời và nhân viên tưởng pipeline bị ngừng.
Một Kafka Streams processor thực hiện join hai KStream có dữ liệu đến lệch vài phút; kết quả bị thiếu khi window join không bao phủ độ trễ thực tế.
Nhóm sử dụng state store RocksDB cho một bộ tổng hợp lớn; sau khi tăng số partition, một pod mới cần khôi phục state từ changelog rất lâu mới sẵn sàng.
Một ứng dụng Kafka Streams đổi tên state store trong bản phát hành; các instance mới không đọc đúng trạng thái cũ và kết quả aggregate bắt đầu tính lại ngoài dự kiến.
Đội vận hành thấy changelog topic bị giảm retention theo chính sách chung; khi stateful processor restart, dữ liệu cần để khôi phục state không còn đầy đủ.
Một topology Kafka Streams có bước groupBy làm phát sinh repartition; số lượng topic nội bộ và lưu lượng broker tăng mạnh sau khi thay đổi khóa tổng hợp.
Nhóm phát triển dùng application.id chung cho hai ứng dụng Kafka Streams độc lập; các task của hai topology bị điều phối cùng nhóm gây hành vi không mong muốn.
Ứng dụng stateful stream processing scale từ hai lên sáu instance; trong giai đoạn rebalance, nhiều task di chuyển và request đọc trạng thái tạm thời không có dữ liệu.
Một dịch vụ cung cấp interactive query tới state store cục bộ; sau khi partition được gán cho pod khác, một endpoint vẫn trả dữ liệu cũ thay vì trạng thái mới nhất.
Nhóm dùng Kafka Streams để tính số dư tài khoản theo event; khi replay lịch sử từ đầu, output tổng hợp được phát lại và hệ thống downstream cập nhật dư thừa.
Ứng dụng chuyển topology Kafka Streams sang exactly_once_v2 để hạn chế duplicate; một sink ngoài Kafka vẫn nhận nhiều cập nhật khi task bị restart giữa các bước.
Đội QA thay serializer của state store nhưng giữ lại dữ liệu cũ trên local disk; ứng dụng Kafka Streams khởi động lỗi khi cố đọc giá trị của phiên bản trước.
Một stateful stream processor dùng TTL trong dữ liệu nghiệp vụ; các record không có event mới tiếp tục nằm trong state store và kích thước đĩa tăng dù đã hết hiệu lực.
Nhóm vận hành thay cấu hình cache Kafka Streams để tăng throughput; kết quả intermediate được xuất ít thường xuyên hơn và dashboard báo dữ liệu chậm cập nhật.
Ứng dụng cần join dòng đơn hàng với kho sản phẩm; dữ liệu trạng thái phải đồng bộ từ nhiều partition, nhưng nhóm QA chỉ kiểm trường hợp hai event đến theo thứ tự lý tưởng.
Một topology xử lý payment event theo khóa userId; một khách hàng tạo lượng giao dịch rất lớn khiến một partition trở thành điểm nóng và các partition khác nhàn rỗi.
Đội thực hiện rolling deployment cho Kafka Streams topology có thay đổi state schema; một số pod cũ và mới sử dụng cùng state store format không tương thích trong lúc chuyển phiên bản.
Ứng dụng dùng nhiều broker binder trong cùng sản phẩm; cấu hình security cho Kafka production bị áp sang Kafka test khiến producer báo lỗi SASL khi đưa lên staging.
Một hệ thống RabbitMQ yêu cầu kết nối TLS với chứng chỉ riêng; sau khi rotate certificate của broker, chỉ một nhóm replica Spring Cloud Stream mất kết nối vì truststore chưa đồng nhất.
Nhóm cấu hình Pulsar authentication token qua secret mount trong Kubernetes; token được xoay khi ứng dụng vẫn chạy nhưng một binder client tiếp tục dùng credential hết hạn.
Đội vận hành cho phép auto-create topic trên môi trường dev; khi deploy production không có quyền tạo topic, Consumer khởi động lỗi vì destination chưa tồn tại.
Ứng dụng sản xuất event chứa dữ liệu tenant trong cùng một Kafka cluster; ACL cho phép consumer group không liên quan đọc topic vì quyền được cấp quá rộng.
Nhóm bảo mật chặn log payload của các giao dịch nhạy cảm; một error handler vẫn ghi toàn bộ message thất bại vào log tập trung khi retry hết lượt.
Ứng dụng xử lý message từ đối tác bên ngoài; một sự kiện bất thường có payload hàng chục MB làm bộ converter giữ nhiều object và pod bị OOM.
Đội triển khai giới hạn kích thước message ở Kafka broker nhỏ hơn producer; API gốc trả thành công nhưng event lớn bị từ chối tại bước gửi nên downstream không nhận dữ liệu.
Một ứng dụng dùng RabbitMQ binder với prefetch cao; khi Consumer xử lý từng tác vụ lâu, nhiều message bị giữ ở cùng pod và các replica khác không chia tải hiệu quả.
Nhóm Pulsar bật batching ở producer để cải thiện throughput; thời gian phát sự kiện đơn lẻ tăng và người dùng thấy thông báo trạng thái đơn hàng đến muộn.
Dịch vụ Kafka producer bật compression cho payload lớn; CPU tăng mạnh dưới tải cao dù băng thông giảm, khiến timeout phát event xuất hiện ở giờ cao điểm.
Đội vận hành quan sát lag Kafka consumer group tăng nhưng số request HTTP vẫn ổn định; họ không biết liệu nghẽn nằm ở binder, Function xử lý hay database đích.
Ứng dụng xuất metrics chỉ theo tên destination; khi một topic có nhiều consumer group, dashboard không phân biệt nhóm nào đang chậm hoặc mất message.
Nhóm ghi nhãn messageId và orderId vào mọi metrics; lượng time series tăng nhanh theo số giao dịch và làm hệ thống monitoring tiêu tốn nhiều bộ nhớ.
Một luồng xử lý từ HTTP tới RabbitMQ rồi Kafka mất correlation ID tại Function chuyển đổi; trace bị đứt nên nhóm hỗ trợ không xác định được vị trí tăng latency.
Đội vận hành chỉ kiểm health của ứng dụng Spring Boot; binder mất kết nối broker nhưng API liveness vẫn UP và queue message tồn đọng nhiều giờ.
Ứng dụng có readiness phụ thuộc kết nối Kafka; một sự cố broker ngắn làm toàn bộ pod bị loại khỏi dịch vụ HTTP dù endpoint đọc dữ liệu không dùng Kafka.
Nhóm deploy nhiều Consumer Kafka cùng lúc khi thêm partition; rebalance liên tiếp khiến tiến độ xử lý event bị ngắt quãng và thời gian hoàn thành batch tăng.
Ứng dụng chạy trong Kubernetes nhận SIGTERM khi rolling update; worker vẫn đang xử lý message nhưng chưa ack, khiến bản ghi được giao lại sau khi pod mới khởi động.
Đội đặt termination grace period ngắn hơn thời gian xử lý một message lớn; khi scale down, tiến trình bị kill giữa giao dịch và hệ thống downstream nhận nhiều side effect lặp.
Một publisher RabbitMQ ngừng cùng ứng dụng trước khi buffer gửi được flush; một số thông báo đã rời HTTP endpoint nhưng không có mặt trong queue sau shutdown.
Nhóm thực hiện disaster recovery chuyển consumer group sang Kafka cluster dự phòng; offset của cluster mới không tương ứng dữ liệu đã xử lý ở cluster cũ và nhiều event bị bỏ qua hoặc phát lại.
Ứng dụng Kafka Streams khôi phục sau sự cố node bằng changelog; readiness bật quá sớm khi state store chưa restore xong và API truy vấn trả số dư sai.
Đội kiểm thử Function bằng dữ liệu object trực tiếp trong unit test; khi nhận message JSON qua binder thật, lỗi contentType và mapping header chỉ xuất hiện ở production.
Một bộ integration test sử dụng Spring Cloud Stream Test Binder; test chứng minh Function biến đổi đúng payload nhưng không phát hiện cấu hình destination và group sai ở Kafka thật.
Nhóm QA dùng Testcontainers Kafka để kiểm consumer group; bộ test chỉ chạy một instance nên không phát hiện sự cố rebalance và cạnh tranh khi production scale.
Ứng dụng có RabbitMQ binder dùng exchange riêng; bộ test in-memory không mô phỏng routing key nên sự kiện thực tế bị chuyển vào queue không có Consumer.
Đội kiểm thử Pulsar binder với subscription mẫu; các kịch bản redelivery, ack timeout và DLQ không được chạy nên lỗi chỉ xuất hiện khi broker thật mất kết nối.
Nhóm chạy contract test cho event schema nhưng chỉ dùng dữ liệu hợp lệ; một field mới bị thiếu trong message cũ làm Consumer lỗi sau khi triển khai producer mới.
Một test end-to-end xác minh dữ liệu cuối cùng ở database sau khi phát event; bộ test không kiểm số lần ghi nên duplicate từ retry không bị phát hiện.
Đội phát triển mô phỏng Kafka Streams topology bằng TopologyTestDriver; tập test có thứ tự event lý tưởng nhưng bỏ qua event đến muộn và lỗi timestamp.
Một pipeline CI đổi version Spring Cloud Stream và Kafka binder; unit test vẫn xanh nhưng lỗi tương thích serializer chỉ xuất hiện khi consumer đọc backlog do phiên bản trước ghi.
Nhóm cho phép Kafka topic retention thấp để tiết kiệm chi phí; một consumer group ngừng nhiều ngày không thể replay đủ event và báo cáo cuối tháng thiếu dữ liệu.
Ứng dụng kiểm toán cần lưu đầy đủ message trong một thời hạn dài; RabbitMQ queue bị xóa cùng vòng đời consumer tạm thời khiến các sự kiện không còn để đối chiếu.
Nhóm chuyển một workflow từ xử lý đồng bộ sang sự kiện; API phản hồi trước khi transaction phía Consumer hoàn tất, nhưng hợp đồng của client vẫn giả định dữ liệu đã sẵn sàng ngay.
Đội vận hành rollback một consumer sau khi đổi schema; phiên bản cũ không đọc được event do producer mới gửi trong thời gian canary và backlog tăng liên tục.
Một dịch vụ quản lý kho dùng cùng Function cho cả Kafka và RabbitMQ; cách xử lý message lỗi, thời điểm ack và thứ tự redelivery khác nhau làm kết quả cuối không nhất quán giữa môi trường.
Nhóm triển khai StreamBridge để gửi sự kiện từ một tác vụ batch có nhiều luồng; cùng payload chứa bộ nhớ mutable bị thay đổi trước khi gửi xong và event tại broker sai với dữ liệu nguồn.
Một Kafka Streams aggregation xuất kết quả về topic compacted; một publisher khác gửi tombstone có cùng key làm trạng thái downstream biến mất dù tổng hợp nội bộ vẫn đúng.
Đội kỹ thuật muốn chuyển một input binding Kafka từ consumer group cũ sang group mới không mất dữ liệu; nhóm thấy hai group cùng đọc trong giai đoạn chuyển tiếp và một số kết quả được ghi trùng.
Một hệ thống có Function lọc gian lận trước khi phát sự kiện chuyển tiền; khi rule engine lỗi và Function chuyển sang fallback, dashboard chỉ cho thấy số message xuất ra mà không phân biệt các giao dịch chưa đánh giá.
Nhóm cung cấp sự kiện cho đối tác yêu cầu phiên bản hóa schema; producer thay đổi giá trị enum nhưng giữ nguyên schema version và các Consumer cũ chuyển message không nhận diện sang DLQ.
Ứng dụng gửi thông báo lịch sử giao dịch bằng Pulsar với subscription Failover; khi consumer chính mất kết nối, consumer dự phòng bắt đầu nhận lại sự kiện cuối và ghi thông báo trùng cho người dùng.
Đội vận hành khôi phục một database từ snapshot cũ nhưng Kafka consumer offset đã tiến xa; một số thay đổi sau snapshot không được áp dụng lại và dữ liệu của hai hệ thống bị lệch.
